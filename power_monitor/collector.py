"""The always-on collector.

- One websocket to Tibber for the Pulse (a reading every 10 s). Each reading is pushed to
  Grafana Cloud; readings are aggregated per minute into Postgres.
- Spot prices every 15 minutes, recent hourly consumption every hour, Elvia's tariff every
  6 hours, a CSV backup of the database every night.
"""

import asyncio
import gzip
import json
import random
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import websockets

from . import db, weather
from .capacity import Step, hour_limit, project_hour, step_for, top3_average, with_hour
from .config import Config
from .elvia import Elvia
from .grafana import Grafana, line
from .tibber import BAN_WAIT, LIVE, LIVE_SUBSCRIPTION, USER_AGENT, Tibber

OSLO = ZoneInfo("Europe/Oslo")
BACKUP_DIR = Path("/data/backups")
BACKUP_DAYS = 14
NO_DATA_TIMEOUT = 120  # seconds without a reading before reconnecting


def _day(ts: datetime) -> str:
    return ts.astimezone(OSLO).date().isoformat()


class Collector:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.tibber = Tibber(cfg.tibber_token, cfg.tibber_home_id)
        self.elvia = Elvia(cfg.elvia_api_key, cfg.metering_point_id)
        self.grafana = Grafana(cfg.grafana_influx_url, cfg.grafana_metrics_user, cfg.grafana_metrics_token)
        self.prices: dict[datetime, float] = {}       # quarter-hour start -> NOK/kWh incl. VAT
        self.grid: dict[datetime, float] = {}         # hour start -> grid energy charge
        self.steps: list[Step] = []
        self.daily_peaks: dict[str, float] = {}       # this month, ended hours only
        self.minute: list[dict] = []                  # readings in the current minute
        self.pending_rows: list[tuple[str, dict]] = []  # Postgres writes waiting for a retry
        self.last: dict | None = None                 # previous reading

    # --- Postgres -------------------------------------------------------------------------

    def _write(self, table: str, rows: list[dict]) -> None:
        """Queue rows and try to write everything queued. Kept for retry if Postgres is down."""
        self.pending_rows.extend((table, r) for r in rows)
        try:
            with db.connect(self.cfg.database_url) as conn:
                for t in dict.fromkeys(t for t, _ in self.pending_rows):
                    db.upsert(conn, t, [r for tt, r in self.pending_rows if tt == t])
            self.pending_rows.clear()
        except Exception as e:
            print(f"postgres write failed, {len(self.pending_rows)} rows kept: {e}", flush=True)

    async def write(self, table: str, rows: list[dict]) -> None:
        await asyncio.to_thread(self._write, table, rows)

    # --- Live readings --------------------------------------------------------------------

    async def live(self) -> None:
        attempt = 0
        while True:
            try:
                async with websockets.connect(LIVE, subprotocols=["graphql-transport-ws"],
                                              user_agent_header=USER_AGENT) as ws:
                    await ws.send(json.dumps({"type": "connection_init", "payload": {"token": self.cfg.tibber_token}}))
                    # Subscribing before the ack gets the socket closed with 4401 Unauthorized.
                    ack = json.loads(await asyncio.wait_for(ws.recv(), 30))
                    if ack["type"] != "connection_ack":
                        raise RuntimeError(f"Tibber refused the connection: {ack}")
                    await ws.send(json.dumps({"id": "live", "type": "subscribe", "payload": {
                        "query": LIVE_SUBSCRIPTION, "variables": {"home": self.cfg.tibber_home_id}}}))
                    while True:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), NO_DATA_TIMEOUT))
                        if msg["type"] == "ping":
                            await ws.send(json.dumps({"type": "pong"}))
                        elif msg["type"] == "next":
                            await self.on_reading(msg["payload"]["data"]["liveMeasurement"])
                            attempt = 0
                        elif msg["type"] in ("error", "complete"):
                            raise RuntimeError(f"Tibber ended the subscription: {msg}")
            except Exception as e:
                # Back off with jitter so reconnects don't hammer Tibber. A 429 means the IP is
                # banned for a few minutes, and retrying during the ban extends it.
                attempt += 1
                banned = getattr(getattr(e, "response", None), "status_code", None) == 429
                delay = (BAN_WAIT if banned else min(300, 15 * 2 ** (attempt - 1))) + random.uniform(0, 15)
                print(f"live connection lost ({e!r}); reconnecting in {delay:.0f} s", flush=True)
                await asyncio.sleep(delay)

    async def on_reading(self, r: dict) -> None:
        ts = datetime.fromisoformat(r["timestamp"])
        prev = self.last
        self.last = {**r, "ts": ts}

        if prev and prev["ts"].replace(minute=0, second=0) != ts.replace(minute=0, second=0):
            await self.hour_ended(prev)
        if self.minute and self.minute[0]["ts"].replace(second=0) != ts.replace(second=0):
            await self.minute_ended()
        self.minute.append(self.last)

        await self.grafana.push(self.metrics(r, ts))

    async def hour_ended(self, last_of_hour: dict) -> None:
        hour = last_of_hour["ts"].replace(minute=0, second=0, microsecond=0)
        kwh = last_of_hour["accumulatedConsumptionLastHour"]
        self.daily_peaks = with_hour(self.daily_peaks, _day(hour), kwh)
        await self.write("consumption_live", [{"ts": hour, "kwh": kwh}])

    async def minute_ended(self) -> None:
        rs, self.minute = self.minute, []
        powers = [r["power"] for r in rs]

        def avg(key):
            values = [r[key] for r in rs if r.get(key) is not None]
            return sum(values) / len(values) if values else None

        def peak(key):
            values = [r[key] for r in rs if r.get(key) is not None]
            return max(values) if values else None

        voltages = [v for r in rs for v in (r["voltagePhase1"], r["voltagePhase2"], r["voltagePhase3"]) if v]
        energy = rs[-1]["accumulatedConsumption"] - rs[0]["accumulatedConsumption"] if len(rs) > 1 else None
        await self.write("reading_1m", [{
            "ts": rs[0]["ts"].replace(second=0, microsecond=0),
            "samples": len(rs),
            "power_avg_w": sum(powers) / len(powers),
            "power_min_w": min(powers),
            "power_max_w": max(powers),
            "energy_kwh": energy if energy is None or energy >= 0 else None,  # counter resets at midnight
            "voltage_l1_v": avg("voltagePhase1"),
            "voltage_l2_v": avg("voltagePhase2"),
            "voltage_l3_v": avg("voltagePhase3"),
            "voltage_min_v": min(voltages) if voltages else None,
            "current_l1_max_a": peak("currentL1"),
            "current_l2_max_a": peak("currentL2"),
            "current_l3_max_a": peak("currentL3"),
            "power_factor": avg("powerFactor"),
        }])

    def metrics(self, r: dict, ts: datetime) -> list[str | None]:
        ns = int(ts.timestamp() * 1e9)
        hour_start = ts.replace(minute=0, second=0, microsecond=0)
        seconds_left = 3600 - (ts - hour_start).total_seconds()
        projected = project_hour(r["accumulatedConsumptionLastHour"] or 0, r["power"], seconds_left)

        now_avg = top3_average(self.daily_peaks)
        projected_avg = top3_average(with_hour(self.daily_peaks, _day(ts), projected))
        step_now = step_for(self.steps, now_avg)
        step_projected = step_for(self.steps, projected_avg)

        limit = hour_limit(self.daily_peaks, _day(ts), step_now.max_kwh if step_now else None)

        quarter = ts.replace(minute=ts.minute - ts.minute % 15, second=0, microsecond=0)
        spot = self.prices.get(quarter)
        grid = self.grid.get(hour_start)
        ahead = [p for start, p in self.prices.items() if quarter < start <= quarter + timedelta(hours=3)]

        lines = [line({
            "power_w": r["power"],
            "power_production_w": r["powerProduction"],
            "power_factor": r["powerFactor"],
            "energy_today_kwh": r["accumulatedConsumption"],
            "cost_today_nok": r["accumulatedCost"],
            "energy_hour_kwh": r["accumulatedConsumptionLastHour"],
            "hour_projected_kwh": projected,
            "capacity_avg_kwh": now_avg,
            "capacity_projected_avg_kwh": projected_avg,
            "capacity_step_max_kwh": step_now.max_kwh if step_now else None,
            "capacity_step_nok": step_now.monthly_nok if step_now else None,
            "capacity_projected_step_nok": step_projected.monthly_nok if step_projected else None,
            # Most this hour may end at before the month moves up a step, and what's left of it.
            "hour_limit_kwh": limit,
            "hour_headroom_kwh": limit - projected if limit is not None else None,
            "spot_price_nok": spot,
            "grid_energy_nok": grid,
            "price_total_nok": spot + grid if spot is not None and grid is not None else None,
            "spot_price_next3h_max_nok": max(ahead) if ahead else None,
            "main_fuse_amps": self.cfg.main_fuse_amps or None,
        }, ts_ns=ns)]
        for phase, (v, a) in {"L1": ("voltagePhase1", "currentL1"), "L2": ("voltagePhase2", "currentL2"),
                              "L3": ("voltagePhase3", "currentL3")}.items():
            lines.append(line({"voltage_v": r[v], "current_a": r[a]}, {"phase": phase}, ns))
        return lines

    # --- Periodic jobs --------------------------------------------------------------------

    async def every(self, seconds: int, job) -> None:
        while True:
            try:
                await job()
            except Exception as e:
                print(f"{job.__name__} failed: {e!r}", flush=True)
            await asyncio.sleep(seconds)

    async def refresh_prices(self) -> None:
        for resolution, minutes in (("QUARTER_HOURLY", 15), ("HOURLY", 60)):
            nodes = await asyncio.to_thread(self.tibber.prices_today_tomorrow, resolution)
            await self.write("spot_price", [
                {"source": "tibber", "area": self.cfg.price_area, "ts": n["startsAt"], "resolution_min": minutes,
                 "currency": n["currency"], "energy": n["energy"], "tax": n["tax"], "total": n["total"],
                 "level": n["level"]} for n in nodes])
            if minutes == 15:
                self.prices = {datetime.fromisoformat(n["startsAt"]): n["total"] for n in nodes}

    async def refresh_consumption(self) -> None:
        nodes = await asyncio.to_thread(self.tibber.recent_consumption, 48)
        await self.write("consumption_hourly", [
            {"ts": n["from"], "kwh": n["consumption"], "cost_nok": n["cost"], "unit_price": n["unitPrice"]}
            for n in nodes if n["consumption"] is not None])
        with db.connect(self.cfg.database_url) as conn:
            self.daily_peaks = db.daily_peaks_this_month(conn)

    async def refresh_tariff(self) -> None:
        today = datetime.combine(date.today(), datetime.min.time(), OSLO)
        tariff = await asyncio.to_thread(self.elvia.tariff, today, today + timedelta(days=2))
        if tariff is None:
            return
        key = tariff["tariff_key"]
        self.grid = {datetime.fromisoformat(h["startTime"]): h["energyPrice"]["total"] for h in tariff["hours"]}
        levels = tariff["fixed_prices"][0]["priceLevels"] if tariff["fixed_prices"] else []
        self.steps = [Step(l["valueMin"], l.get("valueMax"), l["monthlyTotal"]) for l in levels]
        await self.write("grid_tariff_hourly", [
            {"ts": h["startTime"], "tariff_key": key, "energy_nok": h["energyPrice"]["total"],
             "energy_ex_vat": h["energyPrice"]["totalExVat"]} for h in tariff["hours"]])
        await self.write("capacity_step", [
            {"valid_from": f["startDate"][:10], "tariff_key": key, "min_kwh": l["valueMin"],
             "max_kwh": l.get("valueMax"), "monthly_nok": l["monthlyTotal"]}
            for f in tariff["fixed_prices"] for l in f["priceLevels"]])

    async def refresh_weather(self) -> None:
        if self.cfg.latitude is None or self.cfg.longitude is None:
            return
        now_hour = datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:00")
        rows = await asyncio.to_thread(weather.recent_and_forecast, self.cfg.latitude, self.cfg.longitude, now_hour)
        await self.write("weather_hourly", rows)

    async def backup(self) -> None:
        """Nightly CSV export of every table to the Fly volume, which Fly snapshots daily."""
        while True:
            now = datetime.now(OSLO)
            next_run = (now + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
            if now.hour < 3:
                next_run -= timedelta(days=1)
            await asyncio.sleep((next_run - now).total_seconds())
            try:
                await asyncio.to_thread(self._backup, next_run.date())
            except Exception as e:
                print(f"backup failed: {e!r}", flush=True)

    def _backup(self, day: date) -> None:
        target = BACKUP_DIR / day.isoformat()
        target.mkdir(parents=True, exist_ok=True)
        with db.connect(self.cfg.database_url) as conn:
            for table in db.BACKUP_TABLES:
                with gzip.open(target / f"{table}.csv.gz", "wb") as out:
                    db.export_csv(conn, table, out)
        for old in sorted(BACKUP_DIR.iterdir())[:-BACKUP_DAYS]:
            shutil.rmtree(old)
        print(f"backup written to {target}", flush=True)

    async def run(self) -> None:
        # Prices, tariff and this month's peaks first, so the first readings have context.
        for job in (self.refresh_prices, self.refresh_tariff, self.refresh_consumption, self.refresh_weather):
            try:
                await job()
            except Exception as e:
                print(f"startup {job.__name__} failed: {e!r}", flush=True)
        jobs = [
            self.live(),
            self.every(15 * 60, self.refresh_prices),
            self.every(60 * 60, self.refresh_consumption),
            self.every(6 * 60 * 60, self.refresh_tariff),
            self.every(60 * 60, self.refresh_weather),
        ]
        if BACKUP_DIR.parent.exists():
            jobs.append(self.backup())
        await asyncio.gather(*jobs)


def main() -> None:
    cfg = Config.from_env()
    if not (cfg.grafana_influx_url and cfg.grafana_metrics_user and cfg.grafana_metrics_token):
        raise SystemExit("GRAFANA_INFLUX_URL, GRAFANA_METRICS_USER and GRAFANA_METRICS_TOKEN are required")
    print("power-monitor collector starting", flush=True)
    asyncio.run(Collector(cfg).run())


if __name__ == "__main__":
    main()

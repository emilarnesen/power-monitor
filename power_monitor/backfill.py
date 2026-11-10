"""Copy history into Postgres once: Tibber consumption and prices, Elvia grid tariffs.

Safe to re-run: every write is an upsert. Usage: power-backfill [tibber|elvia ...]
"""

import base64
import sys
from datetime import date, datetime, time, timedelta
from time import sleep
from zoneinfo import ZoneInfo

from . import db, weather
from .config import Config
from .elvia import Elvia
from .tibber import Tibber

OSLO = ZoneInfo("Europe/Oslo")
# The current grid tariff model (with capacity steps) started here; Elvia has nothing earlier.
ELVIA_FIRST_MONTH = date(2022, 7, 1)
# The day-ahead market moved to 15-minute prices here. Earlier quarter-hour prices from Tibber
# are just the hourly price repeated, so they aren't stored.
QUARTER_HOUR_FROM = datetime(2025, 10, 1, tzinfo=OSLO)
# Weather from the year before the first consumption data, for comparisons.
WEATHER_FIRST_YEAR = 2020


def backfill_tibber(cfg: Config, conn) -> None:
    tibber = Tibber(cfg.tibber_token, cfg.tibber_home_id)

    total = 0
    for page in tibber.consumption_hourly():
        total += db.upsert(conn, "consumption_hourly", [
            {"ts": n["from"], "kwh": n["consumption"], "cost_nok": n["cost"], "unit_price": n["unitPrice"]}
            for n in page
        ])
        print(f"consumption: {total} hours (to {page[-1]['from'][:10]})", flush=True)

    # Tibber's cursor is the base64 of the last timestamp seen (undocumented), so quarter hours
    # can start at the switch instead of paging through years of repeated hourly prices.
    switch = base64.b64encode((QUARTER_HOUR_FROM - timedelta(minutes=15)).isoformat(timespec="milliseconds").encode()).decode()
    for resolution, minutes, after in (("HOURLY", 60, None), ("QUARTER_HOURLY", 15, switch)):
        total = 0
        for page in tibber.prices(resolution, after):
            rows = [
                {"source": "tibber", "area": cfg.price_area, "ts": n["startsAt"], "resolution_min": minutes,
                 "currency": n["currency"], "energy": n["energy"], "tax": n["tax"], "total": n["total"],
                 "level": n["level"]}
                for n in page
                if minutes == 60 or datetime.fromisoformat(n["startsAt"]) >= QUARTER_HOUR_FROM
            ]
            total += db.upsert(conn, "spot_price", rows)
            print(f"prices {resolution.lower()}: {total} rows (to {page[-1]['startsAt'][:10]})", flush=True)


def _months(first: date, last: date):
    month = first
    while month <= last:
        following = date(month.year + month.month // 12, month.month % 12 + 1, 1)
        yield month, following
        month = following


def backfill_elvia(cfg: Config, conn) -> None:
    elvia = Elvia(cfg.elvia_api_key, cfg.metering_point_id)
    hours = steps = 0
    # Through next month, so tomorrow's tariff is included near a month end.
    for start, end in _months(ELVIA_FIRST_MONTH, date.today().replace(day=28)):
        tariff = elvia.tariff(datetime.combine(start, time(), OSLO), datetime.combine(end, time(), OSLO))
        if tariff is None:
            print(f"elvia {start:%Y-%m}: no prices", flush=True)
            continue
        key = tariff["tariff_key"]
        hours += db.upsert(conn, "grid_tariff_hourly", [
            {"ts": h["startTime"], "tariff_key": key, "energy_nok": h["energyPrice"]["total"],
             "energy_ex_vat": h["energyPrice"]["totalExVat"]}
            for h in tariff["hours"]
        ])
        steps += db.upsert(conn, "capacity_step", [
            {"valid_from": fixed["startDate"][:10], "tariff_key": key, "min_kwh": level["valueMin"],
             "max_kwh": level.get("valueMax"), "monthly_nok": level["monthlyTotal"]}
            for fixed in tariff["fixed_prices"]
            for level in fixed["priceLevels"]
        ])
        print(f"elvia {start:%Y-%m}: {hours} hours, {steps} capacity step rows", flush=True)
        # Stay well under Elvia's rate limit.
        sleep(20)


def backfill_weather(cfg: Config, conn) -> None:
    if cfg.latitude is None or cfg.longitude is None:
        raise SystemExit("LATITUDE and LONGITUDE are needed for weather")
    # The archive lags a few days; the collector fills recent hours from the forecast API.
    for year in range(WEATHER_FIRST_YEAR, date.today().year + 1):
        end = min(date(year, 12, 31), date.today() - timedelta(days=2))
        rows = weather.history(cfg.latitude, cfg.longitude, date(year, 1, 1), end)
        print(f"weather {year}: {db.upsert(conn, 'weather_hourly', rows)} hours", flush=True)


def main() -> None:
    cfg = Config.from_env()
    which = sys.argv[1:] or ["tibber", "elvia", "weather"]
    with db.connect(cfg.database_url) as conn:
        if "tibber" in which:
            backfill_tibber(cfg, conn)
        if "elvia" in which:
            backfill_elvia(cfg, conn)
        if "weather" in which:
            backfill_weather(cfg, conn)


if __name__ == "__main__":
    main()

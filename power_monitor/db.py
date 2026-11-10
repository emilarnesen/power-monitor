"""Writes to the Postgres "power" schema. Every write is an upsert, so re-running is safe."""

import psycopg

UPSERTS = {
    "consumption_hourly": """
        insert into power.consumption_hourly (ts, kwh, cost_nok, unit_price)
        values (%(ts)s, %(kwh)s, %(cost_nok)s, %(unit_price)s)
        on conflict (ts) do update set kwh = excluded.kwh, cost_nok = excluded.cost_nok,
            unit_price = excluded.unit_price""",
    "spot_price": """
        insert into power.spot_price (source, area, ts, resolution_min, currency, energy, tax, total, level)
        values (%(source)s, %(area)s, %(ts)s, %(resolution_min)s, %(currency)s, %(energy)s, %(tax)s,
                %(total)s, %(level)s)
        on conflict (source, area, ts, resolution_min) do update set currency = excluded.currency,
            energy = excluded.energy, tax = excluded.tax, total = excluded.total, level = excluded.level""",
    "grid_tariff_hourly": """
        insert into power.grid_tariff_hourly (ts, tariff_key, energy_nok, energy_ex_vat)
        values (%(ts)s, %(tariff_key)s, %(energy_nok)s, %(energy_ex_vat)s)
        on conflict (ts) do update set tariff_key = excluded.tariff_key,
            energy_nok = excluded.energy_nok, energy_ex_vat = excluded.energy_ex_vat""",
    # The collector's own figure for an hour that just ended. Tibber's hourly data arrives later
    # with cost and replaces it (consumption_hourly above).
    "consumption_live": """
        insert into power.consumption_hourly (ts, kwh) values (%(ts)s, %(kwh)s)
        on conflict (ts) do nothing""",
    "reading_1m": """
        insert into power.reading_1m (ts, samples, power_avg_w, power_min_w, power_max_w, energy_kwh,
            voltage_l1_v, voltage_l2_v, voltage_l3_v, voltage_min_v, current_l1_max_a, current_l2_max_a,
            current_l3_max_a, power_factor)
        values (%(ts)s, %(samples)s, %(power_avg_w)s, %(power_min_w)s, %(power_max_w)s, %(energy_kwh)s,
            %(voltage_l1_v)s, %(voltage_l2_v)s, %(voltage_l3_v)s, %(voltage_min_v)s, %(current_l1_max_a)s,
            %(current_l2_max_a)s, %(current_l3_max_a)s, %(power_factor)s)
        on conflict (ts) do update set samples = excluded.samples, power_avg_w = excluded.power_avg_w,
            power_min_w = excluded.power_min_w, power_max_w = excluded.power_max_w,
            energy_kwh = excluded.energy_kwh, voltage_l1_v = excluded.voltage_l1_v,
            voltage_l2_v = excluded.voltage_l2_v, voltage_l3_v = excluded.voltage_l3_v,
            voltage_min_v = excluded.voltage_min_v, current_l1_max_a = excluded.current_l1_max_a,
            current_l2_max_a = excluded.current_l2_max_a, current_l3_max_a = excluded.current_l3_max_a,
            power_factor = excluded.power_factor""",
    "weather_hourly": """
        insert into power.weather_hourly (ts, temperature_c, forecast)
        values (%(ts)s, %(temperature_c)s, %(forecast)s)
        on conflict (ts) do update set temperature_c = excluded.temperature_c, forecast = excluded.forecast""",
    "capacity_step": """
        insert into power.capacity_step (valid_from, tariff_key, min_kwh, max_kwh, monthly_nok)
        values (%(valid_from)s, %(tariff_key)s, %(min_kwh)s, %(max_kwh)s, %(monthly_nok)s)
        on conflict (valid_from, tariff_key, min_kwh) do update set max_kwh = excluded.max_kwh,
            monthly_nok = excluded.monthly_nok""",
}


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, autocommit=True)


def upsert(conn: psycopg.Connection, table: str, rows: list[dict]) -> int:
    if rows:
        with conn.cursor() as cur:
            cur.executemany(UPSERTS[table], rows)
    return len(rows)


def daily_peaks_this_month(conn: psycopg.Connection) -> dict[str, float]:
    """Highest hourly kWh per day so far this month (Norwegian days), keyed by ISO date."""
    rows = conn.execute("""
        select (ts at time zone 'Europe/Oslo')::date::text, max(kwh)
        from power.consumption_hourly
        where kwh is not null
          and ts >= date_trunc('month', now() at time zone 'Europe/Oslo') at time zone 'Europe/Oslo'
        group by 1""").fetchall()
    return {day: peak for day, peak in rows}


BACKUP_TABLES = ["reading_1m", "consumption_hourly", "spot_price", "grid_tariff_hourly", "capacity_step", "event",
                 "weather_hourly"]


def export_csv(conn: psycopg.Connection, table: str, out) -> None:
    """Write one table as CSV with a header. Restore with COPY ... FROM after the migrations."""
    with conn.cursor().copy(f"copy power.{table} to stdout (format csv, header)") as copy:
        for chunk in copy:
            out.write(chunk)

# Architecture

## Data flow

1. **Meter → Tibber.** The smart meter publishes readings on its HAN port. The Tibber Pulse
   reads them and sends them to Tibber every 10 s.
2. **Tibber → collector.** The collector on Fly.io holds **one** websocket subscription
   (`liveMeasurement`) open: power, voltage per phase, current per phase, energy so far this
   hour and today.
3. **Prices and tariffs.** The collector fetches:
   - spot prices from Tibber every 15 minutes (prices are per quarter hour since 1 Oct 2025)
   - the grid tariff and capacity steps from Elvia once a day (they rarely change)
4. **Derived values.** The collector computes:
   - **projected kWh for the current hour:** energy so far plus current power until the hour ends
   - **this month's capacity threshold:** the 3rd highest daily peak hour so far. Elvia's
     capacity charge is the average of the three highest hours on different days in the month.
5. **Two writes.**
   - Every reading goes to **Grafana Cloud Prometheus** as Influx line protocol over HTTPS.
   - 1-minute aggregates, prices and tariffs go to **Supabase Postgres**.
   - If either target is down, the collector buffers writes and retries.
6. **Grafana Cloud.**
   - Alerts and live dashboards use Prometheus (PromQL).
   - History and year-over-year dashboards use Postgres (SQL).
   - Policy changes (strømstøtte, Norgespris) are shown as annotations.
7. **Backup.** At 03:00 the collector exports every table as gzipped CSV to the Fly volume
   (`/data/backups/<date>/`, 14 days kept), and Fly snapshots the volume daily (30 days kept).
   CSV via `COPY` needs no `pg_dump` matching the server version. To restore, run the
   migrations, then `COPY power.<table> FROM` each file.

## What goes where

| | Grafana Cloud Prometheus | Supabase Postgres |
|---|---|---|
| Retention | 14 days (free tier) | Years (500 MB free tier, about 8–10 years at this volume) |
| Pulse readings | Every 10 s | 1-minute avg / min / max |
| Spot prices | Now, next hours, tomorrow | All quarter hours / hours; NO1 back to 2015 via ENTSO-E |
| Grid tariff | Now, and this month's threshold | Every tariff since July 2022 |
| Capacity steps | Projection and threshold | Top 3 hours per month |
| Used for | Alerts, live dashboards | Trends, year-over-year comparisons |

Alerts never query Postgres. That keeps Supabase load at a few writes a minute and keeps
alerting working if Supabase is down.

## Historical data

| Data | Source | From |
|---|---|---|
| Household consumption and cost, hourly | Tibber API | When the home became a Tibber customer |
| Spot price incl. supplier markup, hourly | Tibber API | Same |
| Grid tariff, capacity steps | Elvia GridTariff API | July 2022, when the current tariff model started |
| NO1 day-ahead price | ENTSO-E Transparency Platform | About 2015 |

Tibber doesn't document how long it keeps history, so the backfill copies everything once.

## Metrics (Prometheus)

Pushed with every Pulse reading (every 10 s) from [`collector.py`](../power_monitor/collector.py).
They carry no personal labels.

| Metric | Meaning |
|---|---|
| `power_monitor_power_w` | Power now |
| `power_monitor_power_production_w` | Power exported (solar), 0 without production |
| `power_monitor_power_factor` | Power factor |
| `power_monitor_voltage_v{phase}` | Voltage per phase |
| `power_monitor_current_a{phase}` | Current per phase (L2 missing on an IT grid) |
| `power_monitor_energy_today_kwh`, `_cost_today_nok` | So far today (Tibber's figures) |
| `power_monitor_energy_hour_kwh` | So far this hour |
| `power_monitor_hour_projected_kwh` | Where this hour ends if power stays as now |
| `power_monitor_capacity_avg_kwh` | Average of this month's top 3 daily peaks (ended hours) |
| `power_monitor_capacity_projected_avg_kwh` | The same, if this hour ends as projected |
| `power_monitor_capacity_step_max_kwh` | Upper bound of the current capacity step |
| `power_monitor_capacity_step_nok`, `_capacity_projected_step_nok` | Monthly price of the current / projected step |
| `power_monitor_spot_price_nok` | Price this quarter hour from Tibber (incl. VAT and markup) |
| `power_monitor_grid_energy_nok` | Grid energy charge this hour |
| `power_monitor_price_total_nok` | Spot + grid energy charge |
| `power_monitor_spot_price_next3h_max_nok` | Highest quarter-hour price in the next 3 hours |
| `power_monitor_main_fuse_amps` | Main fuse, for alert thresholds |

## Tables (Postgres)

Defined in [`supabase/migrations/`](../supabase/migrations/). They live in the `power` schema,
which the Supabase Data API doesn't expose. The collector writes with one role and Grafana reads
with a read-only role.

## Alerts

| Alert | Condition |
|---|---|
| Capacity step | Projected kWh this hour is above this month's threshold |
| Expensive hours ahead | The next hours are above a set price |
| Cheapest hours tomorrow | Summary when tomorrow's prices are published (about 13:00) |
| Phase current | L1 or L3 is near the main fuse for over a minute (the threshold comes from `MAIN_FUSE_AMPS`) |
| Low voltage | A phase is below 207 V (230 V − 10 %) |
| No data | No Pulse reading for 5 minutes |

## Meter notes

The home is on a 230 V IT grid. The meter reports current on L1 and L3 only, so L2 is always
empty, and that is expected. All three phase voltages are reported.

## Dashboards

Defined in [`grafana/dashboards/`](../grafana/dashboards/) and uploaded with
`scripts/grafana-sync.py` (the repo wins over edits in the UI). All in the Grafana folder "Strøm".

| Dashboard | For | Shared without login |
|---|---|---|
| **Strøm – hverdag** (`power-hverdag`) | The household, phone first. A traffic light for "can we use power now", what's left this hour, the capacity step per day with the step limits as red lines, price now, tomorrow's coldest hour, this month so far, and habits | Yes |
| **Strøm – over tid** (`power-over-tid`) | Long-term statistics: this year against last, monthly use per year, what the power cost, Norgespris against spot price, capacity step per month, use against outdoor temperature, base load, spot price history. Policy events are annotations | Yes |
| **Strøm – teknisk** (`power-live`) | Phases, voltage, fuse, raw live numbers | No |

The two family dashboards are Grafana "shared dashboards": anyone with the link can view them,
and they reveal the household's consumption pattern. Keep the links private; turn sharing off
under Dashboard → Share → Share externally to revoke a link.

Shared dashboards don't support per-panel time overrides, and instant queries are evaluated at
the end of the dashboard's time range, so that range must end at `now`.

## Price model

The household has **Norgespris** (fixed 50 øre/kWh incl. VAT, settled on the grid bill). The
spot price therefore doesn't change what the household pays; the grid energy charge (15 øre
cheaper 22–06 and at weekends) and the capacity step do. `power.monthly_price_schemes` compares
Norgespris with spot price minus strømstøtte for every month since 2021 (a "what if" before
October 2025). The strømstøtte rules are in `power.support_scheme`.

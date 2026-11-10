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
7. **Backup.** The collector runs `pg_dump` nightly to a Fly volume, which Fly snapshots daily.

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

Defined with the collector code. All carry no personal labels.

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

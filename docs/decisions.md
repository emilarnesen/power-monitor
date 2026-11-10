# Decisions

## 1. Nothing runs at home

The Mac mini at home has no availability guarantee, and a VM brings an OS to patch. The collector
runs as a small container on Fly.io instead.

## 2. Fly.io container, not serverless

The Pulse only streams over a websocket. Serverless functions and scale-to-zero containers
(Azure Functions, Logic Apps, Cloud Run) don't hold a connection open.

Cloudflare Workers with a per-minute cron that stays connected for about 55 s is free and gives
10 s data with small gaps, but it means about 1,440 reconnects a day to Tibber.

An always-on Fly container keeps one connection, has no gaps, and runs plain Python that can move
anywhere. That is worth about 20 NOK/month.

The meter sends every 10 s, so no option gives finer data.

## 3. No Grafana Alloy

Alloy is an agent that has to run on a machine. Grafana Cloud accepts Influx line protocol over
plain HTTPS, so the collector pushes directly.

## 4. Two stores

- **Grafana Cloud Prometheus** (free, 14 days): fresh data, PromQL, alerts.
- **Supabase Postgres** (free, 500 MB): years of history; SQL suits year-over-year comparisons.

Alerts only read Prometheus, so Supabase stays lightly loaded and alerting doesn't depend on it.
Grafana Cloud Pro (13 months' retention, about 200 NOK/month) was rejected on cost.

## 5. Supabase over the alternatives

| Option | Why not |
|---|---|
| Neon Free | Compute suspends after 5 minutes idle. Writes every 10 s keep it on, which uses about 182 compute-hours a month against a 100-hour quota |
| InfluxDB Cloud Free | 30 days retention |
| Amazon Managed Prometheus | Max 3 years retention; SigV4 setup |
| CockroachDB Basic | Free with real backups, but Grafana's Postgres datasource only "may work" with it. Kept as plan B |
| Timescale, ClickHouse, Fly Postgres | 300–1,600 NOK/month |
| Turso, Cloudflare D1, MotherDuck | No usable Grafana Cloud datasource |

Supabase Free has no backups, so the collector dumps the database nightly to a Fly volume.
Prices and hourly consumption can be fetched again from the sources. The 1-minute Pulse
aggregates can't, and the dump covers them.

## 6. History stored by us, not read live

Tibber doesn't promise how long it keeps history, so we copy it into Postgres once. That also
removes the need for Grafana's Infinity datasource.

## 7. Prices back to 2015 from ENTSO-E

Tibber starts when the home became a customer, and hvakosterstrommen.no starts December 2021.
Nord Pool history is paid. ENTSO-E is the only free source for the years before the 2021–2023
price crisis.

## 8. Public repo, personal values as configuration

See [configuration](configuration.md). Tables live in the `power` schema, not `public`, so the
Supabase Data API doesn't expose them.

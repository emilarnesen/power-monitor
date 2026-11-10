# Services

Checked 2026-11-10. Prices and limits change; check before relying on them.

| Service | Role | Plan | Cost | Limits that matter |
|---|---|---|---|---|
| **Tibber** | Live data (Pulse), prices, consumption history | Customer API token | Free | Websocket: keep one long-lived connection; don't reconnect in a loop |
| **Elvia GridTariff API** | Grid tariff and capacity steps | Developer portal subscription "Grid Tariff" | Free | 200 calls/hour. Only your own metering points, only private smart-home use |
| **ENTSO-E Transparency Platform** | NO1 day-ahead prices back to about 2015 | API access by e-mail request | Free | XML responses |
| **Fly.io** | Runs the collector | Pay as you go | About 20 NOK/month (shared-cpu-1x, 256 MB) | Volume snapshots daily, kept 5 days by default (1–60 configurable) |
| **Grafana Cloud** | Prometheus, dashboards, alerts | Free | 0 | 14 days metric retention, 10k active series |
| **Supabase** | Postgres for long-term data | Free | 0 | 500 MB. **No backups on Free**, hence our own nightly dump. Pauses after a week without activity |
| **Open-Meteo** | Outdoor temperature, hourly, history and 2-day forecast | No account | 0 | Free for non-commercial use |
| **GitHub** | Code, docs, deploy to Fly via Actions | Free | 0 | |

## Endpoints

| Service | Endpoint |
|---|---|
| Tibber GraphQL | `https://api.tibber.com/v1-beta/gql` |
| Tibber live | `wss://websocket-api.tibber.com/v1-beta/gql/subscriptions` (subprotocol `graphql-transport-ws`) |
| Elvia | `POST https://elvia.azure-api.net/grid-tariff/digin/api/1/tariffquery/meteringpointsgridtariffs` |
| ENTSO-E | `https://web-api.tp.entsoe.eu/api` |
| Grafana Cloud metrics in | `https://influx-prod-39-prod-eu-north-0.grafana.net/api/v1/push/influx/write` |
| Grafana Cloud metrics query | `https://prometheus-prod-39-prod-eu-north-0.grafana.net/api/prom` |

## Ruled out

See [decisions](decisions.md).

# Configuration

The repo is public. Everything personal or secret is an environment variable, set as a Fly secret
in production and in a git-ignored `.env` locally. `fly.toml` holds only non-personal settings.
[`.env.example`](../.env.example) lists every variable with dummy values.

| Variable | Secret? | Personal? | Meaning |
|---|---|---|---|
| `TIBBER_TOKEN` | yes | | Tibber API token |
| `TIBBER_HOME_ID` | | yes | Which Tibber home to follow |
| `ELVIA_API_KEY` | yes | | Elvia GridTariff key |
| `METERING_POINT_ID` | | yes | 18-digit metering point (målepunkt-ID) |
| `MAIN_FUSE_AMPS` | | yes | Main fuse, e.g. `50`. Alert thresholds are derived from it |
| `GRID_VOLTAGE` | | yes | `230` for an IT grid, `400` for TN |
| `PRICE_AREA` | | | Bidding zone, e.g. `NO1` |
| `ENTSOE_TOKEN` | yes | | ENTSO-E API token |
| `GRAFANA_INFLUX_URL` | | | Grafana Cloud Influx write URL |
| `GRAFANA_METRICS_USER` | | | Grafana Cloud Prometheus instance id |
| `GRAFANA_METRICS_TOKEN` | yes | | Grafana Cloud token, `metrics:write` |
| `DATABASE_URL` | yes | | Postgres URL for `power_writer` |

The location is not used by the solution and is not stored anywhere.

## What never goes in the repo

- Any value marked secret or personal above.
- Screenshots of real dashboards (they show consumption). Use drawings or sample data.
- Exports of real data, including database dumps.

# Access

Who and what can reach each service, with which credential, and where that credential is kept.
No values are in this repo.

## Accounts

| Service | Account owner | Notes |
|---|---|---|
| Tibber | Household Tibber account | Token created at developer.tibber.com |
| Elvia developer portal | Owner's private e-mail | Product "Grid Tariff" only |
| ENTSO-E | Owner's private e-mail | API access requested by e-mail |
| Fly.io | Owner, personal org | Card on file |
| Grafana Cloud | Stack `emilarnesen`, region EU Sweden | |
| Supabase | Owner | Region eu-north-1 (Stockholm), next to Fly and Grafana Cloud. Connect through the session pooler (IPv4); pooler user names are `<role>.<project-ref>` |
| GitHub | `emilarnesen` | Public repo |

## Credentials

| Credential | Scope | Used by | Kept in |
|---|---|---|---|
| Tibber token | Read data + `write_access` (push notifications) | collector | Fly secret `TIBBER_TOKEN` |
| Elvia API key | Grid Tariff | collector | Fly secret `ELVIA_API_KEY` |
| ENTSO-E token | Read | backfill | Fly secret `ENTSOE_TOKEN` |
| Grafana access policy token `fly-power-collector` | `metrics:write` only | collector | Fly secret `GRAFANA_METRICS_TOKEN` |
| Grafana service account `claude-dashboards` | Admin (Editor cannot create datasources or folders) | Datasource, dashboard and alert sync | Owner's machine only |
| Postgres role `power_writer` | Insert/update in schema `power` | collector | Fly secret `DATABASE_URL` |
| Postgres role `power_reader` | Select in schema `power` | Grafana datasource | Grafana datasource config |
| Postgres `postgres` (owner) | Everything | Migrations only | Owner's machine only |
| Fly deploy token | Deploy this app only | GitHub Actions | GitHub secret `FLY_API_TOKEN` |

On the owner's machine, credentials live in `~/.config/<service>/` with mode 600.

## Rotating a credential

1. Create the new one in the service's console.
2. Update where it is kept: `fly secrets set NAME=...` (restarts the app), the Grafana
   datasource, or the GitHub secret.
3. Revoke the old one.

# Runbook

App: `emilarnesen-power-monitor` on Fly.io, region `arn`, one machine and one volume
(`power_data`, 1 GB, mounted at `/data`).

## Is it running?

```sh
fly status -a emilarnesen-power-monitor
fly logs -a emilarnesen-power-monitor
```

In Grafana, `time() - timestamp(power_monitor_power_w)` should stay under 30 s. The
"No data" alert fires after 5 minutes.

Normal log lines:
- `power-monitor collector starting`
- `backup written to /data/backups/<date>` around 03:00

## Common problems

| Log line | Meaning | Action |
|---|---|---|
| `live connection lost (... 429 ...)` | Tibber banned our IP for a few minutes | None. It waits 5 minutes. Don't restart repeatedly, which extends the ban |
| `live connection lost (... 4401 Unauthorized)` | Tibber token invalid | New token at developer.tibber.com, then `fly secrets set TIBBER_TOKEN=...` |
| `grafana push failed` | Grafana Cloud down or token revoked | Lines are kept (about a day) and sent later. Check the token if it persists |
| `postgres write failed` | Supabase down or paused | Rows are kept in memory and retried. A paused project is resumed in the Supabase dashboard |
| `refresh_tariff failed` / 429 from Elvia | Elvia rate limit | None. It waits as long as Elvia asks |

## Deploy

Push to `main` deploys through GitHub Actions (`.github/workflows/deploy.yml`). By hand:

```sh
fly deploy --remote-only -a emilarnesen-power-monitor
```

## Backfill history

Run from a machine with the keys (see [configuration](configuration.md)):

```sh
scripts/run-local.sh uv run power-backfill          # Tibber and Elvia
scripts/run-local.sh uv run power-backfill elvia    # only Elvia
```

It is safe to re-run (upserts). Tibber pages are spaced 3 s apart; a burst of about 200
calls gets the IP banned.

## Restore the database

1. Find a backup: `fly ssh console -a emilarnesen-power-monitor -C "ls /data/backups"`.
   If the volume is gone, restore a snapshot: `fly volumes snapshots list power_data`.
2. Copy it out: `fly ssh sftp get /data/backups/<date>/<table>.csv.gz`.
3. In a new or emptied database, run the migrations: `supabase db push --db-url ...`.
4. Load each table, for example:
   `gunzip -c spot_price.csv.gz | psql "$URL" -c "copy power.spot_price from stdin (format csv, header)"`.
5. Re-run the backfill to fill anything newer than the backup.

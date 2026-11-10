#!/bin/sh
# Run a command with the production environment, built from the owner's machine:
# personal values from .env (git-ignored), secrets from ~/.config/<service>/ (mode 600).
# Usage: scripts/run-local.sh uv run power-backfill
set -eu
cd "$(dirname "$0")/.."

set -a
. ./.env
set +a

secret() { cat "$HOME/.config/$1"; }
urlencode() { python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }

export TIBBER_TOKEN="$(secret tibber/token)"
export ELVIA_API_KEY="$(secret elvia/gridtariff-key)"
export GRAFANA_METRICS_TOKEN="$(secret grafana-cloud/metrics-write-token)"
[ -f "$HOME/.config/entsoe/token" ] && export ENTSOE_TOKEN="$(secret entsoe/token)"
DATABASE_URL="postgresql://power_writer.${SUPABASE_PROJECT_REF}:$(urlencode "$(secret supabase/power_writer-password)")@${SUPABASE_POOLER_HOST}:5432/postgres?sslmode=require"
export DATABASE_URL

exec "$@"

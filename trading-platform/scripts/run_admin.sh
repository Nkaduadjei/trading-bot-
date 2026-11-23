#!/usr/bin/env bash
# Starts the admin console on http://127.0.0.1:8004  (open it in your browser; local only)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || { echo "Run scripts/setup.sh first"; exit 1; }
[ -f .env ] || { echo "No .env found. Run scripts/setup.sh first"; exit 1; }
. .venv/bin/activate
set -a; . ./.env; set +a
cd services/admin-console
exec python -m uvicorn admin_console.main:app --host 127.0.0.1 --port 8004

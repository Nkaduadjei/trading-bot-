#!/usr/bin/env bash
# Starts the API gateway on http://127.0.0.1:8000  (the front door; interactive docs at /docs)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || { echo "Run scripts/setup.sh first"; exit 1; }
[ -f .env ] || { echo "No .env found. Run scripts/setup.sh first"; exit 1; }
. .venv/bin/activate
set -a; . ./.env; set +a
cd services/api-gateway
exec python -m uvicorn gateway.main:app --host 127.0.0.1 --port 8000

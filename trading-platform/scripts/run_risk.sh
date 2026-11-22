#!/usr/bin/env bash
# Starts the risk-manager service on http://127.0.0.1:8003  (local only; interactive docs at /docs)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || { echo "Run scripts/setup.sh first"; exit 1; }
[ -f .env ] || { echo "No .env found. Run scripts/setup.sh first"; exit 1; }
. .venv/bin/activate
set -a; . ./.env; set +a
cd services/risk-manager
exec python -m uvicorn risk_manager.main:app --host 127.0.0.1 --port 8003

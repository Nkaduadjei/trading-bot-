#!/usr/bin/env bash
# Starts the auth service on http://127.0.0.1:8001  (interactive docs at /docs)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || { echo "Run scripts/setup.sh first"; exit 1; }
[ -f .env ] || { echo "No .env found. Run scripts/setup.sh, then: python scripts/gen_secrets.py >> .env"; exit 1; }
. .venv/bin/activate
set -a; . ./.env; set +a
cd services/auth-service
exec python -m uvicorn auth_service.main:app --host 127.0.0.1 --port 8001

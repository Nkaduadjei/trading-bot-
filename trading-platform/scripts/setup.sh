#!/usr/bin/env bash
# One-time (and safe to repeat) setup. Creates ONE shared .venv for all services.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v python3 >/dev/null || {
  echo "python3 not found. On Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"; exit 1; }

if [ ! -d .venv ]; then
  python3 -m venv .venv || { rm -rf .venv
    echo "Could not create .venv. On Ubuntu/Debian: sudo apt install python3-venv"; exit 1; }
  echo "Created .venv"
else
  echo ".venv already exists, reusing it"
fi

. .venv/bin/activate
pip install -q -r requirements.txt
echo "Python packages are installed"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example (fill in real values later; it is never committed)"
fi
echo "Setup done. Next: scripts/test_all.sh"

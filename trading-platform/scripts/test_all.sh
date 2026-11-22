#!/usr/bin/env bash
# Runs the tests of every Python service and prints one line each.
set -uo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || { echo "Run scripts/setup.sh first"; exit 1; }
. .venv/bin/activate

fail=0
for d in services/*/; do
  [ -f "$d/pytest.ini" ] || continue
  out=$(cd "$d" && python -m pytest -q 2>&1); code=$?
  printf '%-18s %s\n' "$(basename "$d")" "$(echo "$out" | tail -1)"
  [ $code -eq 0 ] || { fail=1; echo "$out" | tail -25; }
done
[ $fail -eq 0 ] && echo "All tests passed" || echo "Some tests FAILED"
exit $fail

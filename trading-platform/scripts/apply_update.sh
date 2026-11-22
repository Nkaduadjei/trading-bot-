#!/usr/bin/env bash
# Apply a newer trading-platform.zip ON TOP of this project, in place.
#  - new files are added
#  - changed files are replaced, and your old copy is saved in .update-backup/<time>/
#  - identical files are left alone
#  - your .env, .venv and data/ are never touched
# Usage: scripts/apply_update.sh ~/Downloads/trading-platform.zip
set -euo pipefail
[ $# -eq 1 ] || { echo "Usage: scripts/apply_update.sh path/to/trading-platform.zip"; exit 1; }
zip=$(realpath "$1"); [ -f "$zip" ] || { echo "File not found: $zip"; exit 1; }
command -v unzip >/dev/null || { echo "Install unzip first: sudo apt install unzip"; exit 1; }
root=$(cd "$(dirname "$0")/.." && pwd)

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
unzip -q "$zip" -d "$tmp"
# The zip holds one top folder (trading-platform/). Use what is inside it, so nothing gets nested.
src="$tmp"
if [ "$(ls -A "$tmp" | wc -l)" -eq 1 ] && [ -d "$tmp/$(ls -A "$tmp")" ]; then src="$tmp/$(ls -A "$tmp")"; fi

stamp=$(date +%Y%m%d-%H%M%S); backup="$root/.update-backup/$stamp"
new=0; changed=0; same=0
while IFS= read -r -d '' f; do
  rel="${f#"$src"/}"
  case "$rel" in .env|*/.env|.venv/*|data/*|.update-backup/*|.git/*) continue;; esac
  dest="$root/$rel"
  if [ ! -e "$dest" ]; then
    mkdir -p "$(dirname "$dest")"; cp "$f" "$dest"; new=$((new+1)); echo "added:   $rel"
  elif cmp -s "$f" "$dest"; then
    same=$((same+1))
  else
    mkdir -p "$backup/$(dirname "$rel")"; cp "$dest" "$backup/$rel"; cp "$f" "$dest"
    changed=$((changed+1)); echo "updated: $rel"
  fi
done < <(find "$src" -type f -print0)

echo "Added: $new   Updated: $changed   Unchanged: $same"
[ $changed -eq 0 ] || echo "Your previous versions of updated files are in .update-backup/$stamp"
echo "Next: scripts/setup.sh (only needed if requirements changed), then scripts/test_all.sh"

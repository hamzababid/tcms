#!/usr/bin/env bash
# Copy the brand assets the platform serves from docs/brand (the single source) into frontend/public.
# `make brand` runs it; `make brand-check` (CI) fails when the copies differ from docs/brand.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/docs/brand"
PUB="$ROOT/frontend/public"

# source (relative to docs/brand) -> destination (relative to frontend/public)
MAP=(
  "favicon.ico:favicon.ico"
  "favicon.svg:favicon.svg"
  "png/assay-app-icon-180.png:apple-touch-icon.png"
  "png/assay-app-icon-192.png:brand/assay-app-icon-192.png"
  "png/assay-app-icon-512.png:brand/assay-app-icon-512.png"
  "assay-logo.svg:brand/assay-logo.svg"
  "assay-logo-on-dark.svg:brand/assay-logo-on-dark.svg"
  "assay-mark-on-dark.svg:brand/assay-mark-on-dark.svg"
  "png/assay-logo-64h.png:brand/assay-logo-64h.png"
)

mode="${1:-sync}"
status=0
for pair in "${MAP[@]}"; do
  src="$SRC/${pair%%:*}"
  dst="$PUB/${pair#*:}"
  if [ "$mode" = "check" ]; then
    if ! cmp -s "$src" "$dst"; then
      echo "brand drift: ${pair#*:} differs from docs/brand/${pair%%:*}"
      status=1
    fi
  else
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
  fi
done
if [ "$mode" = "check" ] && [ $status -ne 0 ]; then
  echo "run 'make brand' and commit the result"
fi
exit $status

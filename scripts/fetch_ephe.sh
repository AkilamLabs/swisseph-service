#!/usr/bin/env bash
# Fetch the Swiss Ephemeris data files needed by the service.
# Source: Astrodienst's official mirror (github.com/aloistr/swisseph, AGPL-3.0).
# semo_18.se1 (Moon) + sepl_18.se1 (planets) cover years 1800-2399.
set -euo pipefail

DEST="${1:-ephe}"
BASE="https://raw.githubusercontent.com/aloistr/swisseph/master/ephe"

mkdir -p "$DEST"
for f in semo_18.se1 sepl_18.se1; do
    if [ -s "$DEST/$f" ]; then
        echo "$DEST/$f already present, skipping"
    else
        echo "fetching $f ..."
        curl -fsSL "$BASE/$f" -o "$DEST/$f"
    fi
done
echo "ephemeris data ready in $DEST/"

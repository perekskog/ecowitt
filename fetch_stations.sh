#!/bin/bash
# Hämtar och bearbetar varje station separat så att deras rådata och
# mätvärden aldrig blandas ihop.
#
# Användning:
#   bash fetch_stations.sh <start_date> <end_date> <cycle_type> [utkatalog]

set -euo pipefail

if [ $# -lt 3 ]; then
  echo "Användning: $0 <start_date> <end_date> <cycle_type> [utkatalog]" >&2
  exit 1
fi

START_DATE="$1"
END_DATE="$2"
CYCLE_TYPE="$3"
OUTDIR="${4:-ecowitt_data}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

: "${ECOWITT_APPLICATION_KEY:?Sätt ECOWITT_APPLICATION_KEY (t.ex. via 'set -a; source .env; set +a')}"
: "${ECOWITT_API_KEY:?Sätt ECOWITT_API_KEY (t.ex. via 'set -a; source .env; set +a')}"
: "${ECOWITT_MAC:?Sätt ECOWITT_MAC till WS90-stationens MAC-adress}"
: "${ECOWITT_G3000_MAC:?Sätt ECOWITT_G3000_MAC till G3000-stationens MAC-adress}"

DEFAULT_CALL_BACK="outdoor,indoor,solar_and_uvi,rainfall_piezo,wind,pressure"

process_station() {
  local name="$1"
  local mac="$2"
  local call_back="$3"
  local station_dir="$OUTDIR/$name"

  echo "Bearbetar stationen $name ..." >&2
  ECOWITT_MAC="$mac" ECOWITT_CALL_BACK="$call_back" \
    bash "$SCRIPT_DIR/fetch_raw.sh" \
      "$START_DATE" "$END_DATE" "$CYCLE_TYPE" "$station_dir/raw"

  bash "$SCRIPT_DIR/flatten_csv.sh" \
    "$station_dir/raw" "$station_dir/ecowitt_${name}_long.csv"
  python3 "$SCRIPT_DIR/widen-json.py" \
    "$station_dir/ecowitt_${name}_long.csv" \
    "$station_dir/ecowitt_${name}_wide.json"
}

mkdir -p "$OUTDIR"
process_station "ws90" "$ECOWITT_MAC" \
  "${ECOWITT_WS90_CALL_BACK:-$DEFAULT_CALL_BACK}"
process_station "g3000" "$ECOWITT_G3000_MAC" \
  "${ECOWITT_G3000_CALL_BACK:-$DEFAULT_CALL_BACK}"

echo "Klart! Separata stationsfiler finns i $OUTDIR/ws90/ och $OUTDIR/g3000/" >&2

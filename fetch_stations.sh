#!/bin/bash
# Hämtar och bearbetar varje station separat så att deras rådata och
# mätvärden aldrig blandas ihop.
#
# Användning:
#   ./fetch_stations.sh 2026-10-16 2026-10-16 5min [utkatalog]
#   ./fetch_stations.sh "2026-10-16 06:00:00" "2026-10-16 18:00:00" 5min [utkatalog]

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
: "${ECOWITT_EASYWEATHERPRO_4F447C_MAC:?Sätt ECOWITT_EASYWEATHERPRO_4F447C_MAC till EasyWeatherPro-4F447C:s MAC-adress}"
: "${ECOWITT_GW3000A_WIFI1573_MAC:?Sätt ECOWITT_GW3000A_WIFI1573_MAC till GW3000A-WIFI1573:s MAC-adress}"

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
  uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/widen-json.py" \
    "$station_dir/ecowitt_${name}_long.csv" \
    "$station_dir/ecowitt_${name}_wide.json"
}

mkdir -p "$OUTDIR"
process_station "EasyWeatherPro-4F447C" "$ECOWITT_EASYWEATHERPRO_4F447C_MAC" \
  "${ECOWITT_EASYWEATHERPRO_4F447C_CALL_BACK:-$DEFAULT_CALL_BACK}"
process_station "GW3000A-WIFI1573" "$ECOWITT_GW3000A_WIFI1573_MAC" \
  "${ECOWITT_GW3000A_WIFI1573_CALL_BACK:-$DEFAULT_CALL_BACK}"

echo "Klart! Separata stationsfiler finns i $OUTDIR/EasyWeatherPro-4F447C/ och $OUTDIR/GW3000A-WIFI1573/" >&2

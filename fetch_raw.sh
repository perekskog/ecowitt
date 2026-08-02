#!/bin/bash
# Steg 1: Hämtar rådata från Ecowitt Cloud API i chunkar och sparar varje
# chunk som en egen JSON-fil, orörd, i en mapp. Ingen omformning här alls
# — det är hela poängen, rådatan ska gå att bygga om ifrån senare.
#
# Användning:
#   bash 1_hamta_raw.sh "2026-05-01 00:00:00" "2026-07-31 23:59:59" 5min [rawdir]

set -euo pipefail

if [ $# -lt 3 ]; then
  echo "Användning: $0 <start_date> <end_date> <cycle_type> [rawdir]" >&2
  exit 1
fi

START_DATE="$1"
END_DATE="$2"
CYCLE_TYPE="$3"
RAWDIR="${4:-raw}"

# Autentisering läses från miljövariabler (se .env.example) — läggs
# ALDRIG hårdkodat i skriptet, eftersom detta repo pushas publikt.
: "${ECOWITT_APPLICATION_KEY:?Sätt ECOWITT_APPLICATION_KEY (t.ex. via 'source .env')}"
: "${ECOWITT_API_KEY:?Sätt ECOWITT_API_KEY (t.ex. via 'source .env')}"
: "${ECOWITT_MAC:?Sätt ECOWITT_MAC (t.ex. via 'source .env')}"
APPLICATION_KEY="$ECOWITT_APPLICATION_KEY"
API_KEY="$ECOWITT_API_KEY"
MAC="$ECOWITT_MAC"

# soil_ch1-4 medvetet uteslutna tills vidare (läggs till när jordsensorerna är på plats)
CALL_BACK="outdoor,indoor,solar_and_uvi,rainfall_piezo,wind,pressure"

case "$CYCLE_TYPE" in
  5min)  CHUNK_DAYS=1 ;;
  30min) CHUNK_DAYS=7 ;;
  4hour) CHUNK_DAYS=30 ;;
  1day)  CHUNK_DAYS=365 ;;
  *)
    echo "Okänd cycle_type: $CYCLE_TYPE (använd 5min|30min|4hour|1day)" >&2
    exit 1
    ;;
esac

mkdir -p "$RAWDIR"

to_epoch() { jq -rn --arg d "$1" '$d | strptime("%Y-%m-%d %H:%M:%S") | mktime'; }
to_datestr() { jq -rn --argjson e "$1" '$e | gmtime | strftime("%Y-%m-%d %H:%M:%S")'; }
to_filedate() { jq -rn --argjson e "$1" '$e | gmtime | strftime("%Y-%m-%d")'; }

START_EPOCH=$(to_epoch "$START_DATE")
END_EPOCH=$(to_epoch "$END_DATE")
CHUNK_SECS=$((CHUNK_DAYS * 86400))

cur=$START_EPOCH
while [ "$cur" -le "$END_EPOCH" ]; do
  chunk_end=$((cur + CHUNK_SECS - 1))
  if [ "$chunk_end" -gt "$END_EPOCH" ]; then
    chunk_end=$END_EPOCH
  fi

  CHUNK_START_STR=$(to_datestr "$cur")
  CHUNK_END_STR=$(to_datestr "$chunk_end")
  OUTFILE="$RAWDIR/${CYCLE_TYPE}_$(to_filedate "$cur").json"

  if [ -f "$OUTFILE" ]; then
    echo "Hoppar över $OUTFILE (finns redan)" >&2
  else
    echo "Hämtar $CHUNK_START_STR till $CHUNK_END_STR -> $OUTFILE" >&2

    RESPONSE=$(curl -s -G "https://api.ecowitt.net/api/v3/device/history" \
      --data-urlencode "application_key=${APPLICATION_KEY}" \
      --data-urlencode "api_key=${API_KEY}" \
      --data-urlencode "mac=${MAC}" \
      --data-urlencode "start_date=${CHUNK_START_STR}" \
      --data-urlencode "end_date=${CHUNK_END_STR}" \
      --data-urlencode "cycle_type=${CYCLE_TYPE}" \
      --data-urlencode "call_back=${CALL_BACK}" \
      --data-urlencode "temp_unitid=1" \
      --data-urlencode "pressure_unitid=3" \
      --data-urlencode "wind_speed_unitid=6" \
      --data-urlencode "rainfall_unitid=12")

    CODE=$(echo "$RESPONSE" | jq -r '.code')
    if [ "$CODE" != "0" ]; then
      echo "Fel från Ecowitt API för $CHUNK_START_STR till $CHUNK_END_STR:" >&2
      echo "$RESPONSE" | jq . >&2
      exit 1
    fi

    echo "$RESPONSE" > "$OUTFILE"
    sleep 1.1
  fi

  cur=$((chunk_end + 1))
done

echo "Klart! Rådata sparad i $RAWDIR/"
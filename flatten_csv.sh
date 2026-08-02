#!/bin/bash
# Steg 2: Läser alla rå JSON-filer från steg 1 och plattar ut dem till
# långt CSV-format (en rad per mätvärde+tidpunkt). Okänsligt för att
# kolumner/sensorer tillkommer eller försvinner mellan körningar.
#
# Användning:
#   bash 2_till_lang_csv.sh [rawdir] [utfil.csv]

set -euo pipefail

RAWDIR="${1:-raw}"
OUTFILE="${2:-ecowitt_long.csv}"

if ! ls "$RAWDIR"/*.json >/dev/null 2>&1; then
  echo "Hittar inga JSON-filer i $RAWDIR/ (kör 1_hamta_raw.sh först)" >&2
  exit 1
fi

jq -rs '
  ["Tidsstämpel","mätvärde","värde"],
  ( [ .[] as $resp
      | $resp.data
      | to_entries[] as $grp
      | $grp.value
      | to_entries[] as $metric
      | $metric.value.list
      | to_entries[] as $point
      | {ts: ($point.key | tonumber), col: ($grp.key + "_" + $metric.key), val: $point.value}
    ]
    | sort_by(.ts)
    | .[]
    | [ (.ts | localtime | strftime("%Y-%m-%d %H:%M:%S")), .col, .val ]
  )
  | @csv
' "$RAWDIR"/*.json > "$OUTFILE"

echo "Klart! Skrev $(($(wc -l < "$OUTFILE") - 1)) rader (+ rubrik) till $OUTFILE"
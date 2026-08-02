#!/usr/bin/env python3
"""
Steg 3: Läser den långa CSV-filen från steg 2, pivoterar till brett
format med pandas, och sparar som JSON (records-orienterad — en lista
med ett dict per tidsstämpel). Tänkt som startpunkten för vidare
analys i pandas/Jupyter.

Användning:
    python 3_till_brett_json.py [in_csv] [ut_json]

Standard: ecowitt_long.csv -> ecowitt_wide.json
"""

import sys

import pandas as pd

IN_CSV = sys.argv[1] if len(sys.argv) > 1 else "ecowitt_long.csv"
OUT_JSON = sys.argv[2] if len(sys.argv) > 2 else "ecowitt_wide.json"

long_df = pd.read_csv(IN_CSV)

wide_df = long_df.pivot_table(
    index="Tidsstämpel",
    columns="mätvärde",
    values="värde",
    aggfunc="first",  # varje (tidsstämpel, mätvärde) ska bara finnas en gång
).reset_index()

wide_df = wide_df.sort_values("Tidsstämpel")

wide_df.to_json(OUT_JSON, orient="records", indent=2, force_ascii=False)

print(f"Klart! {len(wide_df)} rader, {len(wide_df.columns) - 1} mätvärden -> {OUT_JSON}")

# Snabb koll: samma data direkt i minnet för vidare jobb i t.ex. Jupyter
# ---------------------------------------------------------------------
# import pandas as pd
# df = pd.read_json("ecowitt_wide.json")
# df["Tidsstämpel"] = pd.to_datetime(df["Tidsstämpel"])
# df.set_index("Tidsstämpel", inplace=True)
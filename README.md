# Ecowitt weather data pipeline

Fetches historical weather data from a personal [Ecowitt](https://www.ecowitt.net/)
weather station via the Ecowitt Cloud API and turns it into a flat,
analysis-ready format for pandas/Jupyter. No charts or dashboards — this
repo stops at "clean data, ready to load."

Full design rationale, requirements, and API details:
[docs/description.md](docs/description.md) (kept up to date as
requirements evolve).

## Setup

1. Create two API keys under ecowitt.net → account icon → User Profile /
   Private Center → API Keys, and find your station's MAC address there or
   in WSView Plus.
2. Copy `.env.example` to `.env` and fill in your own
   `ECOWITT_APPLICATION_KEY`, `ECOWITT_API_KEY`, and `ECOWITT_MAC`.
   `.env` is gitignored — credentials are never committed.
3. Before running any script: `source .env`

## Usage

Three steps, each doing one job — see [docs/description.md](docs/description.md)
for what each one does and why:

```bash
bash fetch_raw.sh "2026-05-01 00:00:00" "2026-07-31 23:59:59" 5min raw
bash flatten_csv.sh raw ecowitt_long.csv
python3 widen-json.py ecowitt_long.csv ecowitt_wide.json
```

## Other files

- `ecowitt_historik.sh` / `ecowitt_historik.csv` — an earlier monolithic
  prototype and its sample output, kept for reference. The 3-step pipeline
  above is the preferred path going forward.

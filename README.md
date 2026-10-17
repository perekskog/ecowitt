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
   `ECOWITT_APPLICATION_KEY`, `ECOWITT_API_KEY`, `ECOWITT_MAC` (WS90), and
   `ECOWITT_G3000_MAC`.
   `.env` is gitignored — credentials are never committed.
3. Before running any script, export the values from `.env`:
   `set -a; source .env; set +a`

## Usage

To fetch both stations into separate folders, use:

```bash
set -a; source .env; set +a
bash fetch_stations.sh "2026-05-01 00:00:00" "2026-07-31 23:59:59" 5min
```

This writes independent raw JSON, long CSV, and wide JSON files under
`ecowitt_data/ws90/` and `ecowitt_data/g3000/`. The wide JSON files are
`ecowitt_ws90_wide.json` and `ecowitt_g3000_wide.json`. Set
`ECOWITT_WS90_CALL_BACK` and/or `ECOWITT_G3000_CALL_BACK` in `.env` if the
stations need different API callback groups. The original three-step commands
remain available for processing one station; see
[docs/description.md](docs/description.md) for details.

## Other files

- `ecowitt_historik.sh` / `ecowitt_historik.csv` — an earlier monolithic
  prototype and its sample output, kept for reference. The 3-step pipeline
  above is the preferred path going forward.

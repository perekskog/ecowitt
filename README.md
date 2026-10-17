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
   `ECOWITT_APPLICATION_KEY`, `ECOWITT_API_KEY`,
   `ECOWITT_EASYWEATHERPRO_4F447C_MAC`, and
   `ECOWITT_GW3000A_WIFI1573_MAC`.
   `.env` is gitignored — credentials are never committed.
3. Before running any script, export the values from `.env`:
   `set -a; source .env; set +a`
4. Install [uv](https://docs.astral.sh/uv/) if it is not already installed.
   The station script uses `uv` to create/manage the project environment and
   install pandas from `pyproject.toml` automatically on first run.

## Usage

To fetch both stations into separate folders, use:

```bash
set -a; source .env; set +a
bash fetch_stations.sh 2026-05-01 2026-07-31 5min
```

Dates may be given as `YYYY-MM-DD` (the full day is included) or as
`"YYYY-MM-DD HH:MM:SS"` for a specific time range.

This writes independent raw JSON, long CSV, and wide JSON files under
`ecowitt_data/EasyWeatherPro-4F447C/` and
`ecowitt_data/GW3000A-WIFI1573/`. The wide JSON files are
`ecowitt_EasyWeatherPro-4F447C_wide.json` and
`ecowitt_GW3000A-WIFI1573_wide.json`. Set
`ECOWITT_EASYWEATHERPRO_4F447C_CALL_BACK` and/or
`ECOWITT_GW3000A_WIFI1573_CALL_BACK` in `.env` if the stations need different
API callback groups. The original three-step commands remain available for
processing one station; older single-station scripts still use `ECOWITT_MAC`.
See [docs/description.md](docs/description.md) for details.

To run the JSON conversion step directly, use
`uv run python widen-json.py input.csv output.json`.

## Other files

- `ecowitt_historik.sh` / `ecowitt_historik.csv` — an earlier monolithic
  prototype and its sample output, kept for reference. The 3-step pipeline
  above is the preferred path going forward.

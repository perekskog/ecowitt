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
   `uv` creates and manages the project environment and installs the
   dependencies from `pyproject.toml` automatically on first run.

## Usage

To fetch both stations into separate folders, use:

```bash
set -a; source .env; set +a
uv run python fetch_stations.py 2026-05-01 2026-07-31 5min
```

Dates may be given as `YYYY-MM-DD` (the full day is included) or as
`"YYYY-MM-DD HH:MM:SS"` for a specific time range.

### Notebook: daily temperature range

Open [g3000_daily_temperature.ipynb](g3000_daily_temperature.ipynb) in VS Code
and select the `ecowitt` (`.venv`) Python kernel. The notebook plots daily
minimum and maximum outdoor temperatures from the G3000 wide JSON file.
Notebook support is included in the uv development dependencies; if needed,
sync the environment with `uv sync --group dev`.

### Call the history API directly with curl

After loading `.env`, choose the station's MAC variable and send a request.
This example fetches one day of 5-minute data from the G3000:

```bash
curl --silent --show-error --get \
  "https://api.ecowitt.net/api/v3/device/history" \
  --data-urlencode "application_key=${ECOWITT_APPLICATION_KEY}" \
  --data-urlencode "api_key=${ECOWITT_API_KEY}" \
  --data-urlencode "mac=${ECOWITT_GW3000A_WIFI1573_MAC}" \
  --data-urlencode "start_date=2026-10-16 00:00:00" \
  --data-urlencode "end_date=2026-10-16 23:59:59" \
  --data-urlencode "cycle_type=5min" \
  --data-urlencode "call_back=outdoor,indoor,solar_and_uvi,rainfall_piezo,wind,pressure" \
  --data-urlencode "temp_unitid=1" \
  --data-urlencode "pressure_unitid=3" \
  --data-urlencode "wind_speed_unitid=6" \
  --data-urlencode "rainfall_unitid=12"
```

For the other station, replace the `mac` value with
`${ECOWITT_EASYWEATHERPRO_4F447C_MAC}`. `--data-urlencode` safely encodes
spaces and commas in the query parameters. The API returns JSON; check
`code` for `0` to confirm success.

This writes independent raw JSON, long CSV, and wide JSON files under
`ecowitt_data/EasyWeatherPro-4F447C/` and
`ecowitt_data/GW3000A-WIFI1573/`. The wide JSON files are
`ecowitt_EasyWeatherPro-4F447C_wide.json` and
`ecowitt_GW3000A-WIFI1573_wide.json`. Set
`ECOWITT_EASYWEATHERPRO_4F447C_CALL_BACK` and/or
`ECOWITT_GW3000A_WIFI1573_CALL_BACK` in `.env` if the stations need different
API callback groups. Run `uv run python fetch_stations.py --help` for CLI
options. See [docs/description.md](docs/description.md) for details.

Run the focused tests with `uv run python -m unittest discover -s tests`.

## Other files

- `ecowitt_historik.sh` / `ecowitt_historik.csv` — an earlier shell
  prototype and its sample output, retained for reference.

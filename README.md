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

To rebuild the CSV and wide JSON exports from downloaded raw files, without
calling the API, run:

```bash
uv run python fetch_stations.py process data --station GW3000A-WIFI1573
```

This regenerates both the long CSV and wide JSON from that station's `raw/`
files. Any manual edits to the generated CSV will be overwritten; edit the raw
JSON if you want those changes preserved when processing again. Omit
`--station GW3000A-WIFI1573` to process both stations.

### File creation and manual edits

Each station has its own directory. The pipeline creates or updates files in
this order:

1. **Raw API JSON** — one file per requested time chunk, for example
   `data/GW3000A-WIFI1573/raw/5min_2026-09-10.json`. These contain the API
   response and are the source used to rebuild the exports. When fetching
   again, an existing raw chunk is skipped rather than downloaded again.
2. **Long CSV** — `ecowitt_GW3000A-WIFI1573_long.csv`, with one row per
   timestamp and metric (`timestamp,metric,value`). Raw JSON files are read,
   flattened, and sorted by timestamp to create this file.
3. **Wide JSON** — `ecowitt_GW3000A-WIFI1573_wide.json`, with one row per
   timestamp and a separate column for each metric. It is built from the long
   CSV; API `-` placeholders become missing values (`null`) here.

The same sequence applies to `EasyWeatherPro-4F447C`. Fetching data writes
new raw chunks first, then rebuilds the long CSV and wide JSON from all raw
chunks in that station's directory. The `process` command skips the API step
and rebuilds the two derived files from the raw JSON files already there.

For a manual correction that should survive reprocessing, edit the relevant
raw JSON and then run `process`. Editing the generated long CSV or wide JSON
directly is useful for a one-off analysis, but those edits are replaced the
next time the exports are rebuilt.

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

## To do

- Evaluate adding a derived combined series that fills missing shared
  measurements from the other station (for example, outdoor readings missing
  from one station while present on the other). Preserve both original station
  datasets, and define how to handle timestamp alignment and metric-specific
  differences before applying any fallback.

  Example from 2026-09-10: the GW3000 has missing outdoor temperature and
  humidity from 20:50 through 21:05, while EasyWeatherPro has readings:

  | Time | EasyWeatherPro temperature | GW3000 temperature | EasyWeatherPro humidity | GW3000 humidity |
  | --- | ---: | ---: | ---: | ---: |
  | 20:50 | 10.0°C | missing (`-`) | 92% | missing (`-`) |
  | 20:55 | 10.0°C | missing (`-`) | 92% | missing (`-`) |
  | 21:00 | 9.8°C | missing (`-`) | 93% | missing (`-`) |
  | 21:05 | 9.7°C | missing (`-`) | 93% | missing (`-`) |

  This is a case where a derived series could use the other station as a
  fallback without changing either station's original values.

## Other files

- `ecowitt_historik.sh` / `ecowitt_historik.csv` — an earlier shell
  prototype and its sample output, retained for reference.

# Ecowitt weather data pipeline

Fetches historical weather data from a personal [Ecowitt](https://www.ecowitt.net/)
weather station via the Ecowitt Cloud API and turns it into a flat,
analysis-ready format for pandas/Jupyter. No charts or dashboards — this
repo stops at "clean data, ready to load."

Full design rationale, requirements, and API details:
[docs/description.md](docs/description.md) (kept up to date as
requirements evolve).

## Setup

1. Create an Application Key and an API Key under ecowitt.net → account icon
   → User Profile / Private Center → API Keys.
2. Copy `.env.example` to `.env` and fill in `ECOWITT_APPLICATION_KEY` and
   `ECOWITT_API_KEY`. `.env` is gitignored, so credentials are not committed.
3. Copy `stations.example.json` to `stations.json`. For each station, set its
   `name` (descriptive label), `short_name` (used for its folder, output
   filenames, and CLI selection), and `mac` (found in the Ecowitt account or
   WSView Plus). Adjust `call_back` if that station needs different API
   callback groups. `stations.json` is gitignored because it contains your
   station identifiers.
4. In each new terminal session, load and export the API keys once:

   ```bash
   set -a; source .env; set +a
   ```

   Keep using that terminal for fetch commands; repeat this step in a new
   terminal session.
5. Install [uv](https://docs.astral.sh/uv/) if it is not already installed.
   `uv` creates and manages the project environment and installs the
   dependencies from `pyproject.toml` automatically on first run.

## Usage

### Step 1: download raw data

After loading `.env` in this terminal session as shown above, fetch both
stations into separate folders:

```bash
uv run python fetch_stations.py 2026-05-01 2026-07-31 5min
```

The default configuration file is `stations.json`. To use a file at another
path, add `--config path/to/stations.json`.

Dates may be given as `YYYY-MM-DD` (the full day is included) or as
`"YYYY-MM-DD HH:MM:SS"` for a specific time range.

By default, both stations are fetched. To fetch only one, add `--station` with
one of the short names `easyweather` or `gw3000`, or provide a unique part of
the full station name. Matching is case-insensitive. For example:

```bash
uv run python fetch_stations.py 2026-05-01 2026-07-31 5min --station gw3000
```

If the text matches both stations or neither, the command reports the problem
instead of selecting one.

### Step 2: build the CSV and JSON exports

**This step is required after downloading if the CSV and wide JSON files
should include the downloaded data.** Fetch only saves raw JSON; until you run
`process`, the CSV and wide JSON remain unchanged.

Build or refresh the exports for GW3000 with:

```bash
uv run python fetch_stations.py process data --station gw3000
```

This regenerates both the long CSV and wide JSON from that station's `raw/`
files, including all raw chunks saved for the station. Omit `--station gw3000`
to process all configured stations. Processing reads `stations.json` to map
station names to their output folders; it does not use the MAC addresses or
API keys. Any manual edits to the generated CSV or wide JSON are overwritten
when processing runs; edit the raw JSON if you want a correction to persist.

### File creation and manual edits

Each station has its own directory. The pipeline creates or updates files in
this order:

1. **Raw API JSON** — one file per requested time chunk, for example
   `data/gw3000/raw/5min_2026-09-10.json`. These contain the API response and
   are the source used to rebuild the exports. When fetching again, an
   existing raw chunk is skipped rather than downloaded again.
2. **Long CSV** — `gw3000_long.csv`, with one row per
   timestamp and metric (`timestamp,metric,value`). Run `process` to read,
   flatten, and sort all raw JSON files into this file.
3. **Wide JSON** — `gw3000_wide.json`, with one row per
   timestamp and a separate column for each metric. The same `process`
   command builds it from the long CSV; API `-` placeholders become missing
   values (`null`) here.

The same sequence applies to every station in `stations.json`. Fetch and
process are independent commands: fetch downloads raw chunks only, while
`process` skips the API step and rebuilds the derived files from raw JSON
already saved.

For a manual correction that should survive reprocessing, edit the relevant
raw JSON and then run `process`. Editing the generated long CSV or wide JSON
directly is useful for a one-off analysis, but those edits are replaced the
next time the exports are rebuilt.

### Step 3: analyze the processed data

Open [g3000_daily_temperature.ipynb](g3000_daily_temperature.ipynb) in VS Code
and select the `ecowitt` (`.venv`) Python kernel. It reads the processed wide
JSON and plots daily minimum and maximum outdoor temperatures.

Notebook support is included in the uv development dependencies; if needed,
sync the environment with `uv sync --group dev`.

You can also run the notebook outside VS Code in JupyterLab. From the project
folder, run:

```bash
uv run --with jupyterlab jupyter lab g3000_daily_temperature.ipynb
```

This runs JupyterLab with the project's uv environment without adding
JupyterLab to the project dependencies. Stop the local server with `Ctrl+C`
in the terminal when finished.

### Call the history API directly with curl

After loading `.env`, copy the station's MAC from `stations.json` into the
request. This example fetches one day of 5-minute data from the G3000:

```bash
curl --silent --show-error --get \
  "https://api.ecowitt.net/api/v3/device/history" \
  --data-urlencode "application_key=${ECOWITT_APPLICATION_KEY}" \
  --data-urlencode "api_key=${ECOWITT_API_KEY}" \
  --data-urlencode "mac=AA:BB:CC:DD:EE:FF" \
  --data-urlencode "start_date=2026-10-16 00:00:00" \
  --data-urlencode "end_date=2026-10-16 23:59:59" \
  --data-urlencode "cycle_type=5min" \
  --data-urlencode "call_back=outdoor,indoor,solar_and_uvi,rainfall_piezo,wind,pressure" \
  --data-urlencode "temp_unitid=1" \
  --data-urlencode "pressure_unitid=3" \
  --data-urlencode "wind_speed_unitid=6" \
  --data-urlencode "rainfall_unitid=12"
```

Replace the example MAC with the `mac` value for `gw3000` in `stations.json`;
use the other station's MAC for that station instead. `--data-urlencode`
safely encodes spaces and commas in the query parameters. The API returns
JSON; check `code` for `0` to confirm success.

The Python `fetch` command writes raw JSON under a station-specific folder,
for example `ecowitt_data/gw3000/raw/`. Run the separate `process` command to
create the long CSV and wide JSON files, such as `gw3000_long.csv` and
`gw3000_wide.json`. The station names, short names, MAC addresses, and
callback groups are read from `stations.json`. Add another object to its
`stations` list to configure another station. Run
`uv run python fetch_stations.py --help` for CLI options.
See [docs/description.md](docs/description.md) for details.

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

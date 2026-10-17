# Requirements: Ecowitt weather data pipeline

## Background

Ecowitt WS90 weather station (piezo rain gauge, wind, solar/UV) connected
to an HP2564 display/console. The goal is to get measurement data out for
local analysis, without charts or extra processing in the pipeline itself
— just a clean data flow through to a working format that's ready for
further analysis in pandas/Jupyter.

**Important constraint already investigated:** the HP2564's local HTTP API
(`get_livedata_info`) only provides current/live values, not historically
stored data. All history therefore has to be fetched via **Ecowitt's
cloud-based Cloud API** (requires the station to be linked to an
ecowitt.net account).

## Authentication

The Cloud API requires three values in every call:

- `application_key`
- `api_key`
- `mac` (the station's MAC address, found in the ecowitt.net account or in
  WSView Plus)

Both keys are created under ecowitt.net → account icon → User Profile /
Private Center → API Keys (an Application Key + an API Key, separate
values). The two stations use the same API keys but each has its own MAC
address.

## API endpoint and parameters

```
GET https://api.ecowitt.net/api/v3/device/history
```

| Parameter           | Value                         | Comment                                |
| ------------------- | ------------------------------ | ------------------------------------- |
| `application_key`   | your key                       |                                        |
| `api_key`           | your key                       |                                        |
| `mac`               | the station's MAC              |                                        |
| `start_date`        | `YYYY-MM-DD HH:MM:SS`          |                                        |
| `end_date`          | `YYYY-MM-DD HH:MM:SS`          |                                        |
| `cycle_type`        | see table below                |                                        |
| `call_back`         | comma-separated list, see below | `all` does NOT work — must be listed explicitly |
| `temp_unitid`       | `1`                             | Celsius                                |
| `pressure_unitid`   | `3`                             | hPa                                    |
| `wind_speed_unitid` | `6`                             | m/s                                    |
| `rainfall_unitid`   | `12`                            | mm                                     |

### call_back groups (for the current sensor setup)

```
outdoor,indoor,solar_and_uvi,rainfall_piezo,wind,pressure
```

- `rainfall_piezo`, **not** `rainfall` — the WS90 is piezo-based, not a
  tipping bucket.
- `soil_ch1`–`soil_ch4` (soil moisture sensors) are **deliberately excluded
  for now** — to be added once those sensors are in place. Note: raw JSON
  files already fetched (see step 1) do not automatically get updated
  once the group is added later; those days would need to be re-fetched
  manually if soil moisture history is wanted retroactively too.
- Extra channel sensors (e.g. a future roof-mounted wind sensor) will
  likely fall under the already-existing `wind` group and shouldn't
  require any change.
- The two-station runner supports separate optional
  `ECOWITT_EASYWEATHERPRO_4F447C_CALL_BACK` and
  `ECOWITT_GW3000A_WIFI1573_CALL_BACK` settings. If unset, both stations use
  the groups listed above. Only request groups supported by the relevant
  station and its connected sensors.

### cycle_type: resolution, history depth, and max span per call

| `cycle_type` | Resolution | How far back      | Max span/call |
| ------------ | ---------- | ------------------ | ------------- |
| `5min`       | 5 minutes  | ~90 days           | 1 day         |
| `30min`      | 30 minutes | ~1 year             | 1 week        |
| `4hour`      | 4 hours    | ~2 years            | 1 month       |
| `1day`       | 1 day      | since 2019-01-01    | 1 year        |

**Important note on what the values mean:** at `5min`, each point is an
instantaneous reading. At coarser resolutions (`30min`/`4hour`/`1day`),
three variants are returned per metric instead:

- the main value = **average** for the period (confirmed empirically)
- `..._high` = max during the period
- `..._low` = min during the period

**The 90-day limit is the practical constraint**: 5-minute data older than
~90 days can no longer be fetched retroactively — it must be collected
_before_ it ages out. The working approach is to fetch manually every so
often (not a scheduled job right now), as long as you don't wait longer
than ~90 days between fetches.

### Response format (JSON)

Nested by group and metric:

```json
{
  "code": 0,
  "data": {
    "outdoor": {
      "temperature": { "unit": "C", "list": { "<unix_ts>": "18.3", ... } },
      ...
    },
    "wind": { ... },
    ...
  }
}
```

Timestamps in `list` are unix seconds, UTC. `code != 0` means an error —
abort and show `msg`.

## Pipeline: three steps

Design principle: each step does one thing. Charts/visualization are
**explicitly out of scope** for these three steps — envisioned as a
possible separate step 4 later, which would just read step 3's output.

### Fetching multiple stations separately

`fetch_stations.sh` runs the three pipeline steps once per station. It uses
`ECOWITT_EASYWEATHERPRO_4F447C_MAC` for `EasyWeatherPro-4F447C` and
`ECOWITT_GW3000A_WIFI1573_MAC` for `GW3000A-WIFI1573`, and writes each
station's raw JSON, long CSV, and wide JSON under separate subfolders (by
default `ecowitt_data/EasyWeatherPro-4F447C/` and
`ecowitt_data/GW3000A-WIFI1573/`). This prevents same-date raw files from
colliding and keeps identical metric names from different stations out of the
same output.

The wrapper accepts the same date range and `cycle_type` as `fetch_raw.sh`,
plus an optional output directory. Callback groups may be set independently
with `ECOWITT_EASYWEATHERPRO_4F447C_CALL_BACK` (EasyWeatherPro-4F447C) and
`ECOWITT_GW3000A_WIFI1573_CALL_BACK` (GW3000A-WIFI1573); if omitted, each
uses the default groups listed above. Load `.env` with exported variables
before running it (`set -a; source .env; set +a`).
Dates can be passed as `YYYY-MM-DD`, which means midnight through 23:59:59
for that day, or as `YYYY-MM-DD HH:MM:SS` for explicit times.

### Step 1 (bash + curl + jq): fetch raw data

- Input: `start_date`, `end_date`, `cycle_type` as command-line arguments.
- Loops in chunks according to the max-span table above (e.g. one call per
  day for `5min`), with a pause between calls (rate limit: 1 call/sec with
  an API key).
- Saves **each chunk's raw, unmodified JSON response** as its own file in
  a `raw/` folder, named e.g. `<cycle_type>_<date>.json`.
- **Resumable**: skips chunks whose file already exists in `raw/`, so you
  can re-run with a wider interval and only new data gets fetched.
- Reason for keeping the raw data untouched: 5-minute data can't be
  fetched again after 90 days, so the raw data is the only permanent
  source — if the reshaping logic later turns out to need changes,
  everything can still be rebuilt from scratch.

### Step 2 (bash + jq): raw JSON → long CSV format

- Input: the `raw/` folder (all `.json` files).
- Flattens to **long format**: one row per `(timestamp, metric, value)`,
  not one column per metric.
- Columns: `timestamp,metric,value`. Timestamp converted to local time
  (not UTC).
- Why long format: insensitive to sensors being added/removed between
  runs (new sensors just become more rows, no new columns disrupting the
  existing structure). Can also be opened directly in Excel and pivoted
  manually (Insert → PivotTable) as an independent path, without Python.

### Step 3 (Python + pandas, managed with uv): long CSV → wide working format (JSON)

- Input: the long CSV file from step 2.
- Pivots with `pivot_table(index="timestamp", columns="metric",
  values="value", aggfunc="first")` into wide format (one column per
  metric).
- Writes out as **records-oriented JSON** (`orient="records"`): a list
  with one dict per timestamp, e.g.
  `[{"timestamp": "...", "outdoor_temperature": "18.3", ...}, ...]`.
  Chosen because it's directly readable with
  `pd.read_json(..., orient="records")` or `pd.DataFrame(json.load(...))`
  with no extra steps.
- Missing metrics for a given timestamp (e.g. a sensor not yet connected)
  become `null`; the row is not dropped.
- This is meant as the **starting point for further analysis**
  (Jupyter/pandas) — nothing more should really need to happen in the
  pipeline itself from here on.
- `pandas` is declared in `pyproject.toml`; run the conversion with
  `uv run python widen-json.py input.csv output.json`. The station runner
  invokes it through `uv run` and uv creates/synchronizes the project
  environment automatically.

## Already-built prototypes (starting point)

Three working script files already exist as a first implementation and
can be used as a base to build on / clean up:

- `fetch_raw.sh`
- `flatten_csv.sh`
- `widen-json.py`

## Known open points / future work (not part of the current task)

- Add `soil_ch1`–`soil_ch4` to `call_back` once the soil sensors arrive,
  plus decide whether old `raw/` files should be re-fetched.
- Possibly build in a warning in step 1 if an existing raw file is
  missing a group that's now being requested (instead of silently
  skipping it).
- Charts/visualization (separate step 4, reads step 3's output).
- Possible future direction: have the HP2564 send data directly to Azure
  (Blob Storage + Azure Functions, the same stack already used in another
  ongoing project) — either via the console's possible "Custom Server"
  mode, or a scheduled Azure Function doing the same job as step 1 but in
  the cloud. Not started.

#!/usr/bin/env python3
"""Fetch Ecowitt history and write station-specific raw JSON, CSV, and JSON."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

API_URL = "https://api.ecowitt.net/api/v3/device/history"
DEFAULT_CALLBACK = "outdoor,indoor,solar_and_uvi,rainfall_piezo,wind,pressure"
CHUNK_DAYS = {"5min": 1, "30min": 7, "4hour": 30, "1day": 365}
REQUEST_INTERVAL_SECONDS = 1.1


@dataclass(frozen=True)
class Station:
    name: str
    mac_env: str
    callback_env: str


STATIONS = (
    Station(
        "EasyWeatherPro-4F447C",
        "ECOWITT_EASYWEATHERPRO_4F447C_MAC",
        "ECOWITT_EASYWEATHERPRO_4F447C_CALL_BACK",
    ),
    Station(
        "GW3000A-WIFI1573",
        "ECOWITT_GW3000A_WIFI1573_MAC",
        "ECOWITT_GW3000A_WIFI1573_CALL_BACK",
    ),
)


def parse_datetime(value: str, *, end_of_day: bool = False) -> datetime:
    """Parse YYYY-MM-DD or YYYY-MM-DD HH:MM:SS as an API wall-clock time."""
    try:
        if len(value) == 10:
            parsed = datetime.strptime(value, "%Y-%m-%d")
            if end_of_day:
                return parsed.replace(hour=23, minute=59, second=59)
            return parsed
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError(
            f"Ogiltigt datum {value!r}; använd YYYY-MM-DD eller "
            "YYYY-MM-DD HH:MM:SS"
        ) from exc


def iter_chunks(
    start: datetime, end: datetime, cycle_type: str
) -> Iterator[tuple[datetime, datetime]]:
    if cycle_type not in CHUNK_DAYS:
        raise ValueError(
            f"Okänd cycle_type: {cycle_type} (använd "
            f"{'|'.join(CHUNK_DAYS)})"
        )
    if end < start:
        raise ValueError("Slutdatumet måste vara samma som eller senare än startdatumet.")

    chunk_length = timedelta(days=CHUNK_DAYS[cycle_type])
    current = start
    while current <= end:
        chunk_end = min(current + chunk_length - timedelta(seconds=1), end)
        yield current, chunk_end
        current = chunk_end + timedelta(seconds=1)


def required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Miljövariabeln {name} saknas eller är tom.")
    return value


def build_request_url(
    *,
    application_key: str,
    api_key: str,
    mac: str,
    start: datetime,
    end: datetime,
    cycle_type: str,
    callback: str,
) -> str:
    params = {
        "application_key": application_key,
        "api_key": api_key,
        "mac": mac,
        "start_date": start.strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": end.strftime("%Y-%m-%d %H:%M:%S"),
        "cycle_type": cycle_type,
        "call_back": callback,
        "temp_unitid": "1",
        "pressure_unitid": "3",
        "wind_speed_unitid": "6",
        "rainfall_unitid": "12",
    }
    return f"{API_URL}?{urlencode(params)}"


def fetch_response(url: str) -> str:
    request = Request(url, headers={"User-Agent": "ecowitt-data-pipeline/1.0"})
    try:
        with urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"Ecowitt API svarade med HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Kunde inte nå Ecowitt API: {exc}") from exc


def save_raw_response(path: Path, response_text: str) -> dict[str, Any]:
    try:
        response_data = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ecowitt API returnerade ogiltig JSON för {path}.") from exc

    if not isinstance(response_data, dict):
        raise RuntimeError(f"Ecowitt API returnerade ett oväntat svar för {path}.")
    if str(response_data.get("code")) != "0":
        message = response_data.get("msg", "okänt API-fel")
        raise RuntimeError(f"Ecowitt API rapporterade fel för {path}: {message}")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(response_text)
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return response_data


def fetch_station_history(
    station: Station,
    start: datetime,
    end: datetime,
    cycle_type: str,
    raw_dir: Path,
    application_key: str,
    api_key: str,
) -> None:
    mac = required_environment(station.mac_env)
    callback = os.environ.get(station.callback_env, DEFAULT_CALLBACK)
    raw_dir.mkdir(parents=True, exist_ok=True)

    for chunk_start, chunk_end in iter_chunks(start, end, cycle_type):
        raw_path = raw_dir / f"{cycle_type}_{chunk_start:%Y-%m-%d}.json"
        if raw_path.exists():
            print(f"Hoppar över {raw_path} (finns redan)")
            continue

        print(
            f"Hämtar {chunk_start:%Y-%m-%d %H:%M:%S} till "
            f"{chunk_end:%Y-%m-%d %H:%M:%S} -> {raw_path}"
        )
        url = build_request_url(
            application_key=application_key,
            api_key=api_key,
            mac=mac,
            start=chunk_start,
            end=chunk_end,
            cycle_type=cycle_type,
            callback=callback,
        )
        response_text = fetch_response(url)
        save_raw_response(raw_path, response_text)
        time.sleep(REQUEST_INTERVAL_SECONDS)


def flatten_raw_files(raw_dir: Path) -> list[tuple[float, str, Any]]:
    records: list[tuple[float, str, Any]] = []
    raw_files = sorted(raw_dir.glob("*.json"))
    if not raw_files:
        raise RuntimeError(f"Hittar inga JSON-filer i {raw_dir}.")

    for raw_path in raw_files:
        try:
            response_data = json.loads(raw_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Ogiltig JSON i {raw_path}.") from exc
        if not isinstance(response_data, dict):
            raise RuntimeError(f"Oväntat JSON-format i {raw_path}.")
        if str(response_data.get("code")) != "0":
            message = response_data.get("msg", "okänt API-fel")
            raise RuntimeError(f"API-fel i {raw_path}: {message}")

        groups = response_data.get("data") or {}
        if not isinstance(groups, dict):
            raise RuntimeError(f"Oväntat dataformat i {raw_path}.")
        for group_name, group in groups.items():
            if not isinstance(group, dict):
                raise RuntimeError(f"Oväntad mätvärdesgrupp i {raw_path}.")
            for metric_name, metric in group.items():
                if not isinstance(metric, dict):
                    raise RuntimeError(f"Oväntat mätvärde i {raw_path}.")
                points = metric.get("list", {})
                if not isinstance(points, dict):
                    raise RuntimeError(f"Oväntad tidsserie i {raw_path}.")
                for timestamp, value in points.items():
                    try:
                        epoch = float(timestamp)
                    except (TypeError, ValueError) as exc:
                        raise RuntimeError(
                            f"Ogiltig tidsstämpel {timestamp!r} i {raw_path}."
                        ) from exc
                    records.append(
                        (epoch, f"{group_name}_{metric_name}", value)
                    )

    records.sort(key=lambda record: record[0])
    return records


def write_station_outputs(station_dir: Path, station_name: str) -> None:
    records = flatten_raw_files(station_dir / "raw")
    long_csv_path = station_dir / f"ecowitt_{station_name}_long.csv"
    wide_json_path = station_dir / f"ecowitt_{station_name}_wide.json"

    with long_csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["timestamp", "metric", "value"])
        for epoch, metric, value in records:
            timestamp = datetime.fromtimestamp(epoch).astimezone()
            writer.writerow(
                [timestamp.strftime("%Y-%m-%d %H:%M:%S"), metric, value]
            )

    if records:
        long_df = pd.read_csv(long_csv_path, dtype={"value": "string"})
        long_df["value"] = pd.to_numeric(
            long_df["value"].replace("-", pd.NA),
            errors="raise",
        )
        wide_df = (
            long_df.pivot_table(
                index="timestamp",
                columns="metric",
                values="value",
                aggfunc="first",
            )
            .reset_index()
            .sort_values("timestamp")
        )
        wide_df.to_json(
            wide_json_path,
            orient="records",
            indent=2,
            force_ascii=False,
        )
        row_count = len(wide_df)
        metric_count = len(wide_df.columns) - 1
    else:
        wide_json_path.write_text("[]\n", encoding="utf-8")
        row_count = 0
        metric_count = 0

    print(
        f"Klart! {row_count} tidsrader, {metric_count} mätvärden -> "
        f"{wide_json_path}"
    )
    print(f"Skrev {len(records)} mätpunkter -> {long_csv_path}")


def process_station_outputs(output_dir: Path, station_name: str | None) -> None:
    stations = (
        [station for station in STATIONS if station.name == station_name]
        if station_name
        else STATIONS
    )
    for station in stations:
        print(f"Bearbetar stationen {station.name} ...")
        station_dir = output_dir / station.name
        write_station_outputs(station_dir, station.name)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in {"fetch", "process", "-h", "--help"}:
        argv.insert(0, "fetch")

    parser = argparse.ArgumentParser(
        description="Hämta och bearbeta Ecowitt-data separat per station."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    fetch_parser = commands.add_parser(
        "fetch", help="Hämta data och bygg stationernas exportfiler."
    )
    fetch_parser.add_argument(
        "start_date", help="YYYY-MM-DD eller YYYY-MM-DD HH:MM:SS"
    )
    fetch_parser.add_argument(
        "end_date", help="YYYY-MM-DD eller YYYY-MM-DD HH:MM:SS"
    )
    fetch_parser.add_argument("cycle_type", choices=CHUNK_DAYS)
    fetch_parser.add_argument("output_dir", nargs="?", default="ecowitt_data")

    process_parser = commands.add_parser(
        "process", help="Bygg exportfiler från redan hämtade raw JSON-filer."
    )
    process_parser.add_argument("output_dir", nargs="?", default="ecowitt_data")
    process_parser.add_argument(
        "--station",
        choices=[station.name for station in STATIONS],
        help="Bearbeta bara den angivna stationen (standard: båda).",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    try:
        if args.command == "process":
            process_station_outputs(Path(args.output_dir), args.station)
            return 0

        start = parse_datetime(args.start_date)
        end = parse_datetime(args.end_date, end_of_day=True)
        if end < start:
            raise ValueError(
                "Slutdatumet måste vara samma som eller senare än startdatumet."
            )
        application_key = required_environment("ECOWITT_APPLICATION_KEY")
        api_key = required_environment("ECOWITT_API_KEY")
        output_dir = Path(args.output_dir)

        for station in STATIONS:
            print(f"Bearbetar stationen {station.name} ...")
            station_dir = output_dir / station.name
            fetch_station_history(
                station,
                start,
                end,
                args.cycle_type,
                station_dir / "raw",
                application_key,
                api_key,
            )
            write_station_outputs(station_dir, station.name)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Fel: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

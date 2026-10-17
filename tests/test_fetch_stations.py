import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fetch_stations import (
    build_request_url,
    flatten_raw_files,
    iter_chunks,
    parse_datetime,
    parse_args,
    load_stations,
    process_station_outputs,
    select_stations,
    save_raw_response,
    write_station_outputs,
)


class DateParsingTests(unittest.TestCase):
    def test_date_only_start_and_end_cover_the_full_day(self):
        start = parse_datetime("2026-10-16")
        end = parse_datetime("2026-10-16", end_of_day=True)

        self.assertEqual(start, datetime(2026, 10, 16, 0, 0, 0))
        self.assertEqual(end, datetime(2026, 10, 16, 23, 59, 59))

    def test_explicit_times_are_preserved(self):
        value = parse_datetime("2026-10-16 12:34:56", end_of_day=True)

        self.assertEqual(value, datetime(2026, 10, 16, 12, 34, 56))

    def test_invalid_date_is_reported(self):
        with self.assertRaises(ValueError):
            parse_datetime("2026-02-30")


class ChunkingTests(unittest.TestCase):
    def test_five_minute_requests_are_split_at_one_day(self):
        start = datetime(2026, 10, 16)
        end = datetime(2026, 10, 17, 0, 0, 0)

        chunks = list(iter_chunks(start, end, "5min"))

        self.assertEqual(
            chunks,
            [
                (datetime(2026, 10, 16), datetime(2026, 10, 16, 23, 59, 59)),
                (datetime(2026, 10, 17), datetime(2026, 10, 17)),
            ],
        )

    def test_end_before_start_is_rejected(self):
        with self.assertRaises(ValueError):
            list(iter_chunks(datetime(2026, 10, 17), datetime(2026, 10, 16), "5min"))


class ApiHelpersTests(unittest.TestCase):
    def test_request_url_contains_api_parameters(self):
        url = build_request_url(
            application_key="app key",
            api_key="api key",
            mac="AA:BB",
            start=datetime(2026, 10, 16),
            end=datetime(2026, 10, 16, 23, 59, 59),
            cycle_type="5min",
            callback="outdoor,soil_ch1",
        )

        self.assertIn("application_key=app+key", url)
        self.assertIn("call_back=outdoor%2Csoil_ch1", url)
        self.assertIn("start_date=2026-10-16+00%3A00%3A00", url)

    def test_saves_successful_raw_response(self):
        response_text = '{"code":0,"data":{"outdoor":{}}}'
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "raw.json"

            parsed = save_raw_response(raw_path, response_text)

            self.assertEqual(parsed["code"], 0)
            self.assertEqual(raw_path.read_text(encoding="utf-8"), response_text)

    def test_does_not_save_api_error_response(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "raw.json"

            with self.assertRaisesRegex(RuntimeError, "API rapporterade fel"):
                save_raw_response(raw_path, '{"code":1,"msg":"bad request"}')
            self.assertFalse(raw_path.exists())


class StationConfigTests(unittest.TestCase):
    def test_loads_station_names_aliases_and_optional_callback(self):
        config = {
            "stations": [
                {
                    "name": "Weather Station",
                    "short_name": "weather",
                    "mac": "AA:BB:CC:DD:EE:FF",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "stations.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            stations = load_stations(config_path)

        self.assertEqual(len(stations), 1)
        self.assertEqual(stations[0].name, "Weather Station")
        self.assertEqual(stations[0].short_name, "weather")
        self.assertEqual(stations[0].mac, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(
            stations[0].callback,
            "outdoor,indoor,solar_and_uvi,rainfall_piezo,wind,pressure",
        )

    def test_rejects_duplicate_station_names(self):
        station = {
            "name": "Station",
            "short_name": "one",
            "mac": "AA:BB:CC:DD:EE:FF",
        }
        config = {"stations": [station, {**station, "short_name": "two"}]}
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "stations.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "måste vara unika"):
                load_stations(config_path)


class FlatteningTests(unittest.TestCase):
    def test_flattens_metrics_and_sorts_by_timestamp(self):
        payload = {
            "code": 0,
            "data": {
                "outdoor": {
                    "temperature": {
                        "list": {"1792195500": "12.3", "1792195200": "12.1"}
                    }
                },
                "soil_ch1": {
                    "soilmoisture": {"list": {"1792195200": "42"}}
                },
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "raw.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

            records = flatten_raw_files(Path(temp_dir))

        self.assertEqual(
            records,
            [
                (1792195200.0, "outdoor_temperature", "12.1"),
                (1792195200.0, "soil_ch1_soilmoisture", "42"),
                (1792195500.0, "outdoor_temperature", "12.3"),
            ],
        )

    def test_writes_long_csv_and_wide_json(self):
        payload = {
            "code": 0,
            "data": {
                "outdoor": {
                    "temperature": {
                        "list": {
                            "1792195200": "12.1",
                            "1792195500": "-",
                        }
                    }
                },
                "solar_and_uvi": {
                    "solar": {"list": {"1792195500": "500"}}
                },
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            station_dir = Path(temp_dir) / "station"
            raw_dir = station_dir / "raw"
            raw_dir.mkdir(parents=True)
            (raw_dir / "5min_2026-10-16.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

            write_station_outputs(station_dir, "test-station")

            long_csv = station_dir / "ecowitt_test-station_long.csv"
            wide_json = station_dir / "ecowitt_test-station_wide.json"
            self.assertIn("outdoor_temperature", long_csv.read_text(encoding="utf-8"))
            rows = json.loads(wide_json.read_text(encoding="utf-8"))
            self.assertEqual(rows[0]["outdoor_temperature"], 12.1)
            self.assertIsNone(rows[1]["outdoor_temperature"])
            self.assertEqual(rows[1]["solar_and_uvi_solar"], 500)


class CliTests(unittest.TestCase):
    def test_legacy_fetch_arguments_remain_supported(self):
        args = parse_args(["2026-10-01", "2026-10-02", "5min", "data"])

        self.assertEqual(args.command, "fetch")
        self.assertEqual(args.output_dir, "data")

    def test_fetch_command_accepts_short_station_name(self):
        args = parse_args(
            [
                "fetch",
                "2026-10-01",
                "2026-10-02",
                "5min",
                "data",
                "--station",
                "gw3000",
            ]
        )

        self.assertEqual(args.command, "fetch")
        self.assertEqual(args.station, "gw3000")

    def test_process_command_accepts_output_directory_and_station(self):
        args = parse_args(["process", "data", "--station", "gw3000"])

        self.assertEqual(args.command, "process")
        self.assertEqual(args.output_dir, "data")
        self.assertEqual(args.station, "gw3000")
        self.assertEqual(args.config, "stations.json")

    @patch("fetch_stations.write_station_outputs")
    def test_processes_only_selected_station_without_fetching(
        self, write_outputs
    ):
        stations = (
            load_stations(
                Path(__file__).resolve().parents[1] / "stations.example.json"
            )
        )
        process_station_outputs(Path("data"), "gw3000", stations)

        write_outputs.assert_called_once_with(
            Path("data/GW3000A-WIFI1573"),
            "GW3000A-WIFI1573",
        )

    def test_station_selection_accepts_case_insensitive_partial_name(self):
        configured = load_stations(
            Path(__file__).resolve().parents[1] / "stations.example.json"
        )
        stations = select_stations("EASY", configured)

        self.assertEqual([station.short_name for station in stations], ["easyweather"])

    def test_ambiguous_station_selection_is_reported(self):
        configured = load_stations(
            Path(__file__).resolve().parents[1] / "stations.example.json"
        )
        with self.assertRaisesRegex(ValueError, "tvetydig"):
            select_stations("a", configured)

    def test_unknown_station_selection_is_reported(self):
        configured = load_stations(
            Path(__file__).resolve().parents[1] / "stations.example.json"
        )
        with self.assertRaisesRegex(ValueError, "Ingen station matchar"):
            select_stations("unknown", configured)


if __name__ == "__main__":
    unittest.main()

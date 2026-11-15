import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from src.kosis import (KosisError, load_api_key, decode_response, parse_value,
                       normalize_records, request_api, collect_table, validate_table, load_tables)

def table():
    return dict(name="검증용 표", org_id="106", table_id="DT_TEST", year="2024",
                scope="테스트 범위", geography="테스트 지역", selection=dict(itmId="I1", objL1="ALL", objL2="ALL"))

def record():
    return dict(ORG_ID="106", TBL_ID="DT_TEST", PRD_DE="2024", ITM_ID="I1", ITM_NM="발생량", DT="1,234",
                UNIT_NM="톤/년", C1="01", C1_NM="폐지류", C1_OBJ_NM="구분", C2="01", C2_NM="발생량")

class KosisTests(unittest.TestCase):
    def test_api_error_is_not_table_and_never_echoes_key(self):
        secret = "fake-secret-for-test"
        for code in ("10", "11", "12", "30", "31", "40", "41", "42", "50"):
            with self.assertRaises(KosisError) as error:
                decode_response(json.dumps(dict(err=code, errMsg=secret)).encode())
            self.assertNotIn(secret, str(error.exception))
        with self.assertRaises(KosisError):
            decode_response(b"<html>login</html>")

    def test_missing_values_are_not_zero(self):
        for value in ("-", "...", "X", None, "NaN", "<0.1"):
            self.assertIsNone(parse_value(value)[0])
        self.assertEqual(parse_value("0"), (0.0, "수치"))
        self.assertEqual(parse_value("1,234.5")[0], 1234.5)

    def test_classifications_units_and_source_preserved(self):
        frame = normalize_records([record()], table(), "2026-11-15")
        self.assertEqual(frame.iloc[0].value, 1234)
        self.assertEqual(frame.iloc[0].class_1_id, "01")
        self.assertEqual(frame.iloc[0].unit, "톤/년")
        self.assertEqual(frame.iloc[0].geography, "테스트 지역")
        self.assertNotIn("apiKey", frame.iloc[0].source_url)
        bad = record(); bad["PRD_DE"] = "2023"
        with self.assertRaises(KosisError):
            normalize_records([bad], table(), "2026-11-15")

    def test_key_from_ignored_env_file(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(KosisError):
                load_api_key(folder)
            (Path(folder)/".env").write_text("KOSIS_API_KEY=fake-key\n", encoding="utf-8")
            self.assertEqual(load_api_key(folder), "fake-key")

    def test_collection_artifacts_exclude_key(self):
        rows = [record()]
        raw = json.dumps(rows).encode()
        with TemporaryDirectory() as folder, patch("src.kosis.request_api", return_value=(rows, raw)):
            collect_table(table(), "fake-secret", folder)
            manifest = next((Path(folder)/"data/raw/kosis").glob("*_manifest.json"))
            self.assertNotIn("fake-secret", manifest.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["rows"], 1)

    def test_query_rejects_key_and_unsupported_fields(self):
        sample = table(); sample["selection"]["apiKey"] = "secret"
        with self.assertRaises(KosisError):
            validate_table(sample)
        with self.assertRaises(KosisError):
            request_api("not-allowed", {}, "secret")
        validate_table(load_tables()[0])

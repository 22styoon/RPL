from pathlib import Path
import unittest
from src.kosis import KosisError
from src.kosis_public import prepare_public_summary
from src.model import ROOT

class PublicKosisTests(unittest.TestCase):
    def test_real_saved_response_reproduces_official_series(self):
        raw = (ROOT/"data/raw/kosis/public_waste_summary.json").read_bytes()
        frame = prepare_public_summary(raw, "2026-11-15")
        self.assertEqual(frame.value.tolist(), [17303386,16751315,16754168,16685207,17045141])
        self.assertEqual(frame.unit.unique().tolist(), ["톤/년"])
        self.assertEqual(frame.evidence_grade.unique().tolist(), ["A"])

    def test_invalid_response_is_not_turned_into_zero(self):
        with self.assertRaises(KosisError):
            prepare_public_summary(b'{"detailIxValList":[]}', "2026-11-15")

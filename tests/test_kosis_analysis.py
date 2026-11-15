import json
import unittest
import pandas as pd
from src.model import ROOT
from src.kosis import KosisError
from src.kosis_analysis import annotate_classifications, aggregate_materials, display_materials

class KosisAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata = json.loads((ROOT/"data/raw/kosis/DT_106N_29_2020005_metadata.json").read_text(encoding="utf-8"))
        cls.frame = pd.read_csv(ROOT/"data/processed/kosis/DT_106N_29_2020005_2024.csv", dtype={"reference_year":str})
        cls.detail, cls.combined = aggregate_materials(cls.frame, cls.metadata)

    def test_actual_hierarchy_and_observation_count(self):
        self.assertEqual(len(self.frame), 5292)
        self.assertEqual(self.frame.geography.nunique(), 18)
        self.assertEqual(len(self.detail), 144)
        self.assertEqual(len(self.combined), 72)
        national_total = self.frame.loc[(self.frame.class_1_id == "13102134417A.50002") & (self.frame.processing_method == "발생량"), "value"].iloc[0]
        self.assertAlmostEqual(national_total, 17045141.1)

    def test_national_matches_seventeen_regions_without_double_count(self):
        frame = self.frame.copy()
        frame["relative_path"] = frame.class_1_path.str.split(" > ", n=1).str[1]
        columns = ["relative_path", "processing_method"]
        national = frame.loc[frame.geography == "전국"].set_index(columns).value.sort_index()
        regions = frame.loc[frame.geography != "전국"].groupby(columns).value.sum().sort_index()
        self.assertEqual(len(national), 294)
        self.assertLess((national-regions).abs().max(), 1e-6)

    def test_material_totals_reproduce_selected_official_cells(self):
        expected = {
            "폐지류": (2949198.9, 1366556.7),
            "폐합성수지류": (3446829.9, 1230092.9),
            "폐금속류": (388151.0, 244991.7),
            "폐유리류": (484835.9, 288242.8),
        }
        national = self.combined.loc[self.combined.geography == "전국"].set_index("material")
        for material, (generated, recycled) in expected.items():
            self.assertAlmostEqual(national.loc[material, "generated_t"], generated)
            self.assertAlmostEqual(national.loc[material, "material_recycling_t"], recycled)
        self.assertNotIn("13102134417A.50045", national.loc["폐합성수지류", "source_codes"])

    def test_recycling_subtotal_is_not_all_processing(self):
        frame = self.frame.pivot(index="class_1_id", columns="processing_method", values="value")
        self.assertLessEqual((frame["재활용 소계(물질+에너지)"]-frame["물질재활용"]-frame["에너지회수"]).abs().max(), .400001)

    def test_observed_parent_does_not_double_count_children(self):
        child_codes = ["13102134417A.50028", "13102134417A.50029"]
        children = self.frame.loc[self.frame.class_1_id.isin(child_codes)]
        parent = children.groupby("class_2_id", sort=False).first().reset_index()
        parent["value"] = parent.class_2_id.map(children.groupby("class_2_id").value.sum())
        parent["class_1_id"] = "13102134417A.50027"
        augmented = pd.concat([self.frame, parent], ignore_index=True)
        _, result = aggregate_materials(augmented, self.metadata)
        row = result.loc[(result.geography == "전국") & (result.material == "폐지류")].iloc[0]
        self.assertAlmostEqual(row.generated_t, 2949198.9)
        self.assertNotIn(child_codes[0], row.source_codes)

    def test_missing_cell_is_not_replaced_with_zero(self):
        frame = self.frame.copy()
        frame.loc[(frame.class_1_id == "13102134417A.50028") & (frame.class_2_id == "13102134417T.10008"), "value"] = None
        _, result = aggregate_materials(frame, self.metadata)
        row = result.loc[(result.geography == "전국") & (result.material == "폐지류")].iloc[0]
        self.assertTrue(pd.isna(row.material_recycling_t))

    def test_unknown_parent_rejected_and_output_labels_korean(self):
        metadata = [dict(row) for row in self.metadata]
        row = next(r for r in metadata if r.get("ITM_ID") == "13102134417A.50028")
        row["UP_ITM_ID"] = "missing-parent"
        with self.assertRaises(KosisError):
            annotate_classifications(self.frame, metadata)
        self.assertIn("물질재활용 처리량(톤/년)", display_materials(self.combined).columns)

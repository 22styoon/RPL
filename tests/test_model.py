from copy import deepcopy
from io import StringIO
import unittest
import pandas as pd
from src.model import load_config, evaluate, compare, best, annuity, sensitivity, household_saving
from src.presentation import korean_table
from src.provenance import inputs_table

class ModelTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_observed_baseline_exactly_reproduced(self):
        row, flow = evaluate(self.config, self.config["scenarios"][0])
        self.assertAlmostEqual(row["sorted_t"], 7733)
        self.assertEqual(row["handled_t"], 13195)
        self.assertEqual(row["comparison_cost"], 11529161000)
        self.assertEqual(row["collection_budget"], 5383147000)
        self.assertEqual(row["sorting_budget"], 6146014000)
        self.assertAlmostEqual(row["recycled_t"], 7733 * .85)

    def test_mass_conservation(self):
        for scenario in self.config["scenarios"]:
            _, flow = evaluate(self.config, scenario)
            residual = flow.handled - flow.recycled - flow.sorting_loss - flow.processing_loss
            self.assertTrue((residual.abs() < 1e-8).all())

    def test_invalid_missing_units_and_rates(self):
        for value in (-0.1, 1.1, float("nan"), None, True):
            sample = deepcopy(self.config)
            sample["common"]["processing_yield"] = value
            with self.assertRaises(ValueError):
                compare(sample)
        self.config["units"]["mass"] = "kg/day"
        with self.assertRaises(ValueError):
            compare(self.config)

    def test_reprocessing_endpoints(self):
        for y in (0, 1):
            self.config["common"]["processing_yield"] = y
            row, _ = evaluate(self.config, self.config["scenarios"][0])
            self.assertAlmostEqual(row["recycled_t"], 7733 * y)

    def test_recycling_floor_and_infeasible_target(self):
        table = compare(self.config)
        self.assertFalse(bool(table.loc[table.id == "C", "recycling_ok"].iloc[0]))
        self.assertIsNone(best(compare(self.config, 1.0)))
        self.assertEqual(table.feasible.tolist(), compare(self.config, 0).feasible.tolist())
        self.assertEqual(best(compare(self.config, .53)), "B")
        self.assertEqual(best(compare(self.config, .55)), "D")

    def test_capacity_unknown_over_and_boundary(self):
        scenario = self.config["scenarios"][0]
        result, _ = evaluate(self.config, scenario)
        self.assertEqual(result["capacity_status"], "미확인")
        self.assertFalse(result["fully_verified"])
        scenario["capacity_t"] = 13195
        self.assertEqual(evaluate(self.config, scenario)[0]["capacity_status"], "충족")
        for s in self.config["scenarios"]:
            s["capacity_t"] = 13194
        self.assertIsNone(best(compare(self.config)))

    def test_missing_costs_preserved_in_csv(self):
        table = compare(self.config)
        for key in ("household_cost", "reprocessing_cost", "separate_disposal_cost"):
            self.assertTrue(table[key].isna().all())
        shown = korean_table(table)
        restored = pd.read_csv(StringIO(shown.to_csv(index=False)))
        self.assertTrue(restored["가계 총비용(미확인)"].isna().all())

    def test_transfer_not_included(self):
        scenario = self.config["scenarios"][0]
        before, _ = evaluate(self.config, scenario)
        scenario["epr_transfer"] = 999999999
        after, _ = evaluate(self.config, scenario)
        self.assertEqual(before["comparison_cost"], after["comparison_cost"])

    def test_dynamic_evidence(self):
        self.config["common"]["processing_yield"] = .9
        ledger = inputs_table(self.config).set_index("parameter_path")
        self.assertEqual(ledger.loc["common.processing_yield", "value"], "0.9")
        target_ledger = inputs_table(self.config, .53).set_index("parameter_path")
        self.assertEqual(target_ledger.loc["runtime.minimum_final_rate", "value"], "0.53")
        self.assertEqual(ledger.loc["scenarios.A.capacity_t", "value"], "미확인")
        self.assertEqual(ledger.loc["observations.handled_t", "evidence_grade"], "B")

    def test_household_unit_calculation(self):
        self.assertAlmostEqual(household_saving(1, 9860), 8545.333333333334)

    def test_annuity_and_reproducibility(self):
        self.assertEqual(annuity(100, 0, 10), 10)
        with self.assertRaises(ValueError):
            annuity(100, .03, 0)
        self.assertTrue(compare(self.config).equals(compare(self.config)))
        self.assertEqual(sensitivity(self.config).parameter.nunique(), 3)

    def test_unsupported_case_year(self):
        self.config["reference_year"] = 2023
        with self.assertRaises(ValueError):
            compare(self.config)

if __name__ == "__main__":
    unittest.main()

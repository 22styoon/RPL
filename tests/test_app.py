import unittest
from pathlib import Path
from unittest.mock import patch
from src.model import load_config
from streamlit.testing.v1 import AppTest

class DashboardTests(unittest.TestCase):
    def test_dashboard_and_infeasible_target(self):
        app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.sidebar.slider[0].value, 9860)
        selected = next(m for m in app.metric if m.label == "등록 대안 중 조건부 최소 포함비용안")
        self.assertEqual(selected.value, "A")
        app.sidebar.slider[1].set_value(100).run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        selected = next(m for m in app.metric if m.label == "등록 대안 중 조건부 최소 포함비용안")
        self.assertEqual(selected.value, "충족 대안 없음")
        self.assertTrue(any("비교 포함비용(원/년)" in frame.value.columns for frame in app.dataframe))


    def test_yaml_defaults_and_scenario_order_are_preserved(self):
        config = load_config()
        config["common"]["processing_yield"] = .90
        config["scenarios"][1]["sorting_budget_multiplier"] = 1.12
        config["scenarios"] = list(reversed(config["scenarios"]))
        with patch("src.model.load_config", return_value=config):
            app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.sidebar.slider[2].value, 90)
        self.assertAlmostEqual(app.sidebar.number_input[0].value, 12)

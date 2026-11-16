import unittest
from pathlib import Path
from unittest.mock import patch
from src.model import load_config
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"

def widget(items, key):
    return next(item for item in items if item.key == key)

def metric(app, label):
    return next(item for item in app.metric if item.label == label).value

class DashboardTests(unittest.TestCase):
    def ready(self):
        app = AppTest.from_file(APP).run(timeout=40)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 0)
        app.sidebar.radio[0].set_value("가정 기반 민감도 분석").run(timeout=40)
        return app

    def test_default_keeps_missing_costs_and_offers_report(self):
        app = self.ready()
        self.assertEqual(metric(app, "조건부 최소 비교비용 정책"), "비용 입력 후 순위 산정")
        self.assertEqual(metric(app, "필수 비용 입력완료"), "0 / 4개")
        app.sidebar.radio[0].set_value("국내 통계 현황").run(timeout=40)
        self.assertTrue(any("대화형 보고서" in item.proto.label for item in app.get("download_button")))
        app.sidebar.radio[0].set_value("가정 기반 민감도 분석").run(timeout=40)
        self.assertTrue(any("범위 내 비교비용(원/년)" in frame.value.columns for frame in app.dataframe))

    def test_national_cost_inputs_adoption_and_capacity_are_applied(self):
        app = self.ready()
        for name, value in (("collection_per_t",100),("material_processing_per_t",200),("other_treatment_per_t",300),("processing_residue_per_t",100)):
            widget(app.number_input, "national_policy_cost_"+name).set_value(float(value))
        widget(app.checkbox, "national_policy_scan_adoption").set_value(True)
        app.run(timeout=40)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 0)
        self.assertEqual(metric(app, "필수 비용 입력완료"), "13 / 13개")
        self.assertIn(metric(app,"조건부 최소 비교비용 정책"), ["A","B","B_25","B_50","B_75","D","D_25","D_50","D_75"])
        widget(app.number_input, "national_policy_material_capacity_t").set_value(0.0)
        app.run(timeout=40)
        self.assertEqual(metric(app,"조건부 최소 비교비용 정책"), "선정 없음")
        self.assertEqual(len(app.exception), 0)

    def test_facility_baseline_impossible_goal_and_custom_alternative(self):
        app = self.ready()
        widget(app.radio, "policy_mode").set_value("구로구 시설·예산").run(timeout=40)
        self.assertEqual(metric(app,"등록 대안 중 조건부 최소 포함비용안"), "A")
        widget(app.checkbox,"facility_add_e").set_value(True)
        widget(app.slider,"facility_minimum_target").set_value(100.0)
        app.run(timeout=40)
        self.assertEqual(metric(app,"등록 대안 중 조건부 최소 포함비용안"), "충족 대안 없음")
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 0)
        self.assertTrue(any("E" in frame.value.get("시나리오",[]).tolist() for frame in app.dataframe if "시나리오" in frame.value))

    def test_facility_yaml_defaults_and_scenario_order_preserved(self):
        config=load_config()
        config["common"]["processing_yield"]=.90
        config["scenarios"][1]["sorting_budget_multiplier"]=1.12
        config["scenarios"]=list(reversed(config["scenarios"]))
        with patch("src.model.load_config",return_value=config):
            app=AppTest.from_file(APP).run(timeout=40)
            app.sidebar.radio[0].set_value("가정 기반 민감도 분석").run(timeout=40)
            widget(app.radio,"policy_mode").set_value("구로구 시설·예산").run(timeout=40)
        self.assertEqual(len(app.exception),0)
        self.assertEqual(len(app.error),0)
        self.assertEqual(widget(app.slider,"facility_reference_yield").value,90.0)
        # The unedited B budget multiplier remains in the exported result table.
        self.assertTrue(any("대안 설명" in frame.value.columns for frame in app.dataframe))

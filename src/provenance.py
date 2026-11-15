"""실제 실행에 적용한 값과 출처를 함께 내보낸다."""
import pandas as pd
from src.model import ROOT, baseline

def inputs_table(config, target=None):
    ledger = pd.read_csv(ROOT / "data/input_evidence.csv", keep_default_na=False)
    obs = baseline(config)
    values = {"runtime.minimum_final_rate": 0.0 if target is None else target}
    for name, value in obs.items():
        values[f"observations.{name}"] = value
    for name, value in config["common"].items():
        values[f"common.{name}"] = value
    values["reference_year"] = config["reference_year"]
    for scenario in config["scenarios"]:
        for name, value in scenario.items():
            values[f"scenarios.{scenario['id']}.{name}"] = value
    for index, row in ledger.iterrows():
        value = values.get(row.parameter_path)
        ledger.loc[index, "value"] = "미확인" if value is None else str(value)
    return ledger

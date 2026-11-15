"""구로구의 관측 처리실적과 공개 예산에 근거한 조건부 비교 모형."""
from copy import deepcopy
from math import isfinite
from pathlib import Path
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]

def number(value, name, upper=None):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) or value < 0:
        raise ValueError(f"{name}: 0 이상의 유한한 숫자가 필요합니다.")
    if upper is not None and value > upper:
        raise ValueError(f"{name}: {upper} 이하여야 합니다.")
    return value

def load_config(path=None):
    with open(path or ROOT / "configs/scenarios.yaml", encoding="utf-8-sig") as stream:
        return yaml.safe_load(stream)

def load_observations():
    return pd.read_csv(ROOT / "data/processed/guro_recycling.csv")

def annuity(capital, rate, years):
    number(capital, "추가 투자비"); number(rate, "할인율"); number(years, "설비 수명")
    if years == 0:
        raise ValueError("설비 수명은 0보다 커야 합니다.")
    return capital / years if rate == 0 else capital * rate / (1 - (1 + rate) ** (-years))

def baseline(config):
    table = load_observations()
    rows = table.loc[table.reference_year == config["reference_year"]]
    if len(rows) != 1:
        raise ValueError("해당 연도의 관측 기준선이 정확히 하나여야 합니다.")
    row = rows.iloc[0].to_dict()
    for key in ("handled_t", "sorted_t", "residue_t", "collection_budget_krw", "sorting_budget_krw"):
        number(row[key], key)
    if row["handled_t"] <= 0 or abs(row["handled_t"] - row["sorted_t"] - row["residue_t"]) > 1e-6:
        raise ValueError("관측 자료의 물질수지가 일치하지 않습니다.")
    if row["collection_budget_krw"] + row["sorting_budget_krw"] != row["total_budget_krw"]:
        raise ValueError("관측 자료의 예산 합계가 일치하지 않습니다.")
    return row

def evaluate(config, scenario):
    if config["units"] != {"mass": "t/year", "cost": "KRW/year", "time": "hours/household/year"}:
        raise ValueError("지원하지 않는 단위입니다.")
    if config['reference_year'] != 2024:
        raise ValueError('현재 모형은 2024년 구로구 사례만 지원합니다.')
    obs = baseline(config)
    common = config["common"]
    y = number(common["processing_yield"], "최종 재처리 수율 가정", 1)
    for key in ("collection_budget_multiplier", "sorting_budget_multiplier", "additional_capital"):
        number(scenario[key], key)
    kind = scenario["sorting_target"]
    if kind == "baseline":
        sorting_rate = obs["sorted_t"] / obs["handled_t"]
    elif kind == "previous_year":
        prior_config = dict(config, reference_year=config["reference_year"] - 1)
        prior = baseline(prior_config)
        sorting_rate = prior["sorted_t"] / prior["handled_t"]
    else:
        sorting_rate = number(kind, "선별률 목표", 1)
    mass = obs["handled_t"]
    sorted_t = mass * sorting_rate
    recycled_t = sorted_t * y
    capacity = scenario.get("capacity_t")
    if capacity is not None:
        number(capacity, "연간 처리용량")
    capacity_status = "미확인" if capacity is None else ("충족" if mass <= capacity else "초과")
    costs = {
        "collection_budget": obs["collection_budget_krw"] * scenario["collection_budget_multiplier"],
        "sorting_budget": obs["sorting_budget_krw"] * scenario["sorting_budget_multiplier"],
        "additional_capital_annual": annuity(scenario["additional_capital"], common["discount_rate"], common["life_years"]),
    }
    # 가계·재처리·별도 처분비는 자료 부재/중복 우려 때문에 결측 상태를 유지한다.
    flows = pd.DataFrame([dict(material="혼합 재활용품 전체", handled=mass, sorted=sorted_t,
                               recycled=recycled_t, sorting_loss=mass-sorted_t,
                               processing_loss=sorted_t-recycled_t,
                               residue_total=mass-recycled_t)])
    result = dict(id=scenario["id"], name=scenario["name"], handled_t=mass,
                  sorting_rate=sorting_rate, sorted_t=sorted_t, processing_yield=y,
                  final_rate=recycled_t/mass, recycled_t=recycled_t,
                  residue_t=mass-recycled_t, comparison_cost=sum(costs.values()),
                  household_cost=None, reprocessing_cost=None, separate_disposal_cost=None,
                  capacity_status=capacity_status, fully_verified=False,
                  evidence_grade="공식자료(B)·가정(D) 혼합", **costs)
    return result, flows

def compare(config, target=None):
    table = pd.DataFrame([evaluate(config, s)[0] for s in config["scenarios"]])
    if table.id.duplicated().any() or (table.id == "A").sum() != 1:
        raise ValueError("기준선 A가 하나이고 시나리오 식별자가 중복되지 않아야 합니다.")
    row_a = table.loc[table.id == "A"].iloc[0]
    floor = row_a.final_rate if target is None else max(row_a.final_rate, number(target, "목표비율", 1))
    table["requested_target"] = 0.0 if target is None else target
    table["effective_target"] = floor
    table["recycling_ok"] = table.final_rate + 1e-12 >= floor
    table["feasible"] = table.recycling_ok & (table.capacity_status != "초과")
    table["savings_vs_a"] = row_a.comparison_cost - table.comparison_cost
    return table

def best(table):
    candidates = table.loc[table.feasible]
    return None if candidates.empty else candidates.loc[candidates.comparison_cost.idxmin(), "id"]

def sensitivity(config, target=None):
    rows = []
    for parameter, factors in (
        ("processing_yield", (0.70, 0.85, 0.95)),
        ("collection_budget_multiplier", (0.9, 1.0, 1.1)),
        ("sorting_budget_multiplier", (0.9, 1.0, 1.1)),
    ):
        for value in factors:
            sample = deepcopy(config)
            if parameter == "processing_yield":
                sample["common"][parameter] = value
            else:
                for scenario in sample["scenarios"]:
                    scenario[parameter] *= value
            table = compare(sample, target)
            for row in table.to_dict("records"):
                rows.append(dict(parameter=parameter, assumption_value=value, selected=best(table), **row))
    return pd.DataFrame(rows)

def household_saving(minutes_per_week, time_value):
    number(minutes_per_week, "주당 절약 시간"); number(time_value, "시간가치")
    return minutes_per_week * 52 / 60 * time_value

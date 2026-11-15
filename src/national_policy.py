"""KOSIS 동일 지역·4품목 실적에 근거한 명시적 외생가정 실험."""
from copy import deepcopy
from datetime import datetime
from io import BytesIO
import hashlib
import json
from math import isfinite
from pathlib import Path
import zipfile
from zoneinfo import ZoneInfo
import pandas as pd
import yaml
from src.model import ROOT, annuity, number

MATERIALS = ("폐지류", "폐합성수지류", "폐금속류", "폐유리류")
PRICE_LABELS = {
    "collection_per_t":"발생량당 수거 단가",
    "material_processing_per_t":"물질재활용 투입량당 처리 단가",
    "other_treatment_per_t":"물질재활용 외 경로 단가",
    "processing_residue_per_t":"재생공정 손실량당 처리 단가",
}
SCENARIO_FIELDS = ("collection_factor", "processing_factor", "other_factor", "capital",
                   "additional_capacity_t", "producer_real_per_t", "household_time_factor")

def load_policy_config(path=None):
    with open(path or ROOT/"configs/policy_experiment.yaml", encoding="utf-8-sig") as stream:
        return yaml.safe_load(stream)

def available_regions():
    frame = pd.read_csv(ROOT/"data/processed/kosis_materials_2024.csv")
    return ["전국"] + sorted(set(frame.geography) - {"전국"})

def signed_number(value, name, limit=1):
    if isinstance(value, bool) or not isinstance(value, (float,int)) or not isfinite(value) or abs(value) > limit:
        raise ValueError(f"{name}: -{limit}~{limit} 범위의 유한한 숫자가 필요합니다.")
    return value

def region_data(config):
    if config["reference_year"] != 2024:
        raise ValueError("현재 검증한 KOSIS 사례연도는 2024년입니다.")
    frame = pd.read_csv(ROOT/"data/processed/kosis_materials_2024.csv")
    region = frame.loc[frame.geography == config["region"]].copy()
    if len(region) != 4 or set(region.material) != set(MATERIALS) or region.material.duplicated().any():
        raise ValueError("선택 지역에 동일한 4품목 기준선이 필요합니다.")
    if set(region.unit) != {"톤/년"}:
        raise ValueError("기준선 단위가 톤/년이 아닙니다.")
    for row in region.to_dict("records"):
        for name in ("generated_t", "material_recycling_t"):
            number(row[name], name)
        if row["generated_t"] <= 0 or row["material_recycling_t"] > row["generated_t"]:
            raise ValueError("발생량과 물질재활용 처리량의 범위를 확인하세요.")
    return region

def validate_config(config):
    for material in MATERIALS:
        number(config["baseline_yields"][material], material+" 최종수율 가정", 1)
    for name in PRICE_LABELS:
        value = config["costs"][name]
        if value is not None:
            number(value, PRICE_LABELS[name])
    economics = config["economics"]
    for name in ("discount_rate", "life_years", "time_value"):
        number(economics[name], name)
    if economics["life_years"] == 0:
        raise ValueError("설비 수명은 0보다 커야 합니다.")
    for name in ("households", "baseline_minutes_per_week"):
        if economics[name] is not None:
            number(economics[name], name)
    for name in ("include_household",):
        if not isinstance(economics[name], bool):
            raise ValueError(name+"는 참/거짓이어야 합니다.")
    constraints = config["constraints"]
    number(constraints["minimum_final_rate"], "최소 재생원료 전환비율", 1)
    for name in ("annual_public_budget", "material_capacity_t"):
        if constraints[name] is not None:
            number(constraints[name], name)
    if not isinstance(constraints["require_known_capacity"], bool) or not isinstance(config["scan_adoption"], bool):
        raise ValueError("용량 검증·도입비중 탐색은 참/거짓 값이어야 합니다.")
    scenarios = config["scenarios"]
    ids = [s["id"] for s in scenarios]
    if not ids or len(ids) != len(set(ids)) or ids.count("A") != 1:
        raise ValueError("기준선 A가 하나이며 시나리오 식별자가 고유해야 합니다.")
    for scenario in scenarios:
        for name in ("treatment_change_pp", "yield_change_pp"):
            signed_number(scenario[name], name)
        for name in SCENARIO_FIELDS:
            number(scenario[name], name)
        if scenario["id"] == "A":
            if scenario["treatment_change_pp"] or scenario["yield_change_pp"]:
                raise ValueError("기준선 A의 처리실적·최종수율 효과를 바꿀 수 없습니다.")
            for name in SCENARIO_FIELDS:
                expected = 1 if name.endswith("_factor") else 0
                if scenario[name] != expected:
                    raise ValueError("기준선 A의 비용 배율·추가 투자 등을 바꿀 수 없습니다.")

def _evaluate(config, data, scenario, adoption):
    economics, prices = config["economics"], config["costs"]
    policy_id = scenario["id"] if adoption in (0,1) else f"{scenario['id']}_{int(adoption*100)}"
    flows = []
    for row in data.to_dict("records"):
        mass, observed = row["generated_t"], row["material_recycling_t"]
        raw_rate = observed/mass + scenario["treatment_change_pp"]*adoption
        raw_yield = config["baseline_yields"][row["material"]] + scenario["yield_change_pp"]*adoption
        treatment = mass * min(1, max(0, raw_rate))
        y = min(1, max(0, raw_yield))
        final = treatment*y
        flows.append(dict(policy_id=policy_id, material=row["material"], generated_t=mass,
                          observed_material_treatment_t=observed, modeled_material_treatment_t=treatment,
                          assumed_yield=y, final_t=final, other_pathways_t=mass-treatment,
                          processing_loss_t=treatment-final,
                          rate_clipped=not 0 <= raw_rate <= 1 or not 0 <= raw_yield <= 1,
                          observed_balance_error_t=mass-row["recycling_total_t"]-row["incinerated_t"]-row["landfilled_t"]-row["other_t"]))
    flow = pd.DataFrame(flows)
    mass, treatment, final, loss = [float(flow[c].sum()) for c in ("generated_t", "modeled_material_treatment_t", "final_t", "processing_loss_t")]
    collection_factor = 1 + adoption*(scenario["collection_factor"]-1)
    processing_factor = 1 + adoption*(scenario["processing_factor"]-1)
    other_factor = 1 + adoption*(scenario["other_factor"]-1)
    quantities = {"collection_per_t":mass*collection_factor, "material_processing_per_t":treatment*processing_factor,
                  "other_treatment_per_t":(mass-treatment)*other_factor, "processing_residue_per_t":loss}
    components = {name.replace("_per_t","_cost"): None if prices[name] is None else prices[name]*quantity for name,quantity in quantities.items()}
    missing = [PRICE_LABELS[name] for name in prices if name in PRICE_LABELS and prices[name] is None]
    annual_capital = annuity(scenario["capital"]*adoption, economics["discount_rate"], economics["life_years"])
    producer_cost = mass*scenario["producer_real_per_t"]*adoption
    household_cost = None
    if economics["include_household"]:
        if economics["households"] is None or economics["baseline_minutes_per_week"] is None:
            missing.append("가계 대상 가구 수·주당 시간")
        else:
            household_cost = economics["households"]*economics["baseline_minutes_per_week"]*52/60*economics["time_value"]*(1+adoption*(scenario["household_time_factor"]-1))
    public_complete = all(value is not None for value in components.values())
    public_cost = sum(components.values()) + annual_capital if public_complete else None
    cost_complete = public_complete and not missing
    comparison_cost = public_cost + producer_cost + (household_cost or 0) if cost_complete else None
    known_subtotal = sum(value for value in components.values() if value is not None) + annual_capital + producer_cost + (household_cost or 0)
    capacity = config["constraints"]["material_capacity_t"]
    capacity = None if capacity is None else capacity + scenario["additional_capacity_t"]*adoption
    capacity_status = "미확인" if capacity is None else ("충족" if treatment <= capacity+1e-7 else "초과")
    ceiling = config["constraints"]["annual_public_budget"]
    budget_status = "미설정" if ceiling is None else ("미평가" if public_cost is None else ("충족" if public_cost <= ceiling+1e-6 else "초과"))
    result = dict(policy_id=policy_id, scenario_id=scenario["id"], name=scenario["name"], adoption=adoption,
                  geography=config["region"], generated_t=mass, material_treatment_t=treatment, final_t=final,
                  final_rate=final/mass, comparison_cost=comparison_cost, known_cost_subtotal=known_subtotal,
                  public_cost=public_cost, household_cost=household_cost, producer_cost=producer_cost,
                  annual_capital=annual_capital, costs_complete=cost_complete,
                  capacity_status=capacity_status, budget_status=budget_status,
                  missing_costs="; ".join(missing), evidence_grade="관측 A·정책/수율/비용 가정 D", fully_verified=False, **components)
    return result, flow

def compare_policies(config):
    validate_config(config)
    data = region_data(config)
    records, flows = [], []
    for scenario in config["scenarios"]:
        levels = (0,) if scenario["id"] == "A" else ((.25,.5,.75,1.) if config["scan_adoption"] else (1.,))
        for adoption in levels:
            record, flow = _evaluate(config, data, scenario, adoption)
            records.append(record); flows.append(flow)
    table = pd.DataFrame(records)
    floor = max(float(table.loc[table.policy_id == "A", "final_rate"].iloc[0]), config["constraints"]["minimum_final_rate"])
    table["effective_target"] = floor
    table["recycling_ok"] = table.final_rate + 1e-12 >= floor
    reasons = []
    for row in table.to_dict("records"):
        failed = []
        if not row["recycling_ok"]:
            failed.append("재생원료 목표 미달")
        if row["capacity_status"] == "초과":
            failed.append("물질재활용 처리 용량 초과")
        if row["capacity_status"] == "미확인" and config["constraints"]["require_known_capacity"]:
            failed.append("처리 용량 미입력")
        if row["budget_status"] == "초과":
            failed.append("공공지출 상한 초과")
        if row["budget_status"] == "미평가":
            failed.append("공공지출 제약 미평가")
        reasons.append("; ".join(failed))
    table["rejection_reasons"] = reasons
    table["feasible"] = table.rejection_reasons == ""
    a_cost = table.loc[table.policy_id == "A", "comparison_cost"].iloc[0]
    table["savings_vs_a"] = None if pd.isna(a_cost) else a_cost-table.comparison_cost
    return table, pd.concat(flows, ignore_index=True)

def selected_policy(results):
    candidates = results.loc[results.feasible & results.costs_complete & results.comparison_cost.notna()]
    return None if candidates.empty else str(candidates.loc[candidates.comparison_cost.idxmin(), "policy_id"])

def target_curve(config, targets):
    rows = []
    for target in targets:
        number(target, "목표 전환비율", 1)
        sample = deepcopy(config)
        sample["constraints"]["minimum_final_rate"] = float(target)
        table, _ = compare_policies(sample)
        selected = selected_policy(table)
        rows.append(dict(requested_target=float(target), effective_target=float(table.effective_target.iloc[0]),
                         selected_id=selected, minimum_cost=None if selected is None else float(table.loc[table.policy_id == selected, "comparison_cost"].iloc[0]),
                         feasible_count=int(table.feasible.sum())))
    return pd.DataFrame(rows)

def sensitivity(config):
    rows = []
    experiments = []
    for value in (.70,.85,.95):
        sample = deepcopy(config); sample["baseline_yields"] = {m:value for m in MATERIALS}
        experiments.append(("최종 재처리 수율", value, sample))
    for value in (-.02,0,.02):
        sample = deepcopy(config)
        for scenario in sample["scenarios"]:
            if scenario["id"] != "A":
                scenario["treatment_change_pp"] = min(1, max(-1, scenario["treatment_change_pp"] + value))
        experiments.append(("대안 처리비율 효과 추가 변화(%p)", value*100, sample))
    for value in (.8,1.,1.2):
        sample = deepcopy(config)
        price = sample["costs"]["material_processing_per_t"]
        if price is not None:
            sample["costs"]["material_processing_per_t"] = price*value
        experiments.append(("물질재활용 처리 단가 배율", value, sample))
    for name, value, sample in experiments:
        table, _ = compare_policies(sample)
        selected = selected_policy(table)
        chosen = None if selected is None else table.loc[table.policy_id == selected].iloc[0]
        rows.append(dict(parameter=name, value=value, selected_id=selected,
                         minimum_cost=None if chosen is None else float(chosen.comparison_cost),
                         selected_final_rate=None if chosen is None else float(chosen.final_rate),
                         feasible_count=int(table.feasible.sum())))
    return pd.DataFrame(rows)

def input_snapshot(config):
    source = ROOT/"data/processed/kosis_materials_2024.csv"
    return dict(model_version="3.0", captured_at=datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
                configuration=deepcopy(config), source_file="data/processed/kosis_materials_2024.csv",
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                cost_scope="선택한 4개 처리단가·추가투자·생산자 추가실물비용·선택 시 가계시간; 관측 총사회비용 아님",
                unverified=["정책효과·최종수율의 인과적 타당성","법규·안전성","미입력 비용·시설용량"],
                material_scope="대응 4품목. 영농폐비닐·복합제품 재질 제외")

def default_curve_targets(config, results):
    targets = {value/20 for value in range(21)}
    targets.add(float(config["constraints"]["minimum_final_rate"]))
    for value in pd.to_numeric(results["final_rate"], errors="coerce").dropna():
        targets.add(float(value))
        if value < 1:
            targets.add(min(1., float(value)+1e-7))
    return sorted(targets)

def export_bundle(config, results=None, flows=None):
    if results is None or flows is None:
        results, flows = compare_policies(config)
    curve = target_curve(config, default_curve_targets(config, results))
    experiments = sensitivity(config)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, frame in (("policy_results.csv",results),("material_flows.csv",flows),("target_curve.csv",curve),("sensitivity.csv",experiments)):
            archive.writestr(name, translate_table(frame).to_csv(index=False).encode("utf-8-sig"))
        archive.writestr("inputs.json",json.dumps(input_snapshot(config),ensure_ascii=False,indent=2,allow_nan=False))
        archive.writestr("source_rows.csv",region_data(config).to_csv(index=False).encode("utf-8-sig"))
        archive.writestr("readme.txt","공식 처리량과 가정 최종량을 구분합니다. 비용 미입력은 0이 아닙니다. 입력·출처 해시와 단가 범위를 함께 검토하세요.")
    return buffer.getvalue()

def translate_table(frame):
    labels = {"policy_id":"대안 식별자","scenario_id":"시나리오","name":"대안 설명","adoption":"도입비중(%)",
              "geography":"지역","material":"품목","generated_t":"발생량(톤/년)","material_treatment_t":"가정 물질재활용 처리량(톤/년)",
              "final_t":"예상 최종 재생원료량(톤/년)","final_rate":"가정 최종 전환비율(%)",
              "comparison_cost":"범위 내 비교비용(원/년)","known_cost_subtotal":"입력된 비용의 부분합(원/년)",
              "public_cost":"가정 공공지출(원/년)","household_cost":"가정 가계 시간비용(원/년)",
              "producer_cost":"추가 생산자 실물비용(원/년)","annual_capital":"추가 투자 연간화(원/년)",
              "costs_complete":"선택 범위 비용 입력완료","capacity_status":"처리 용량 상태","budget_status":"공공지출 상한 상태",
              "missing_costs":"미입력 비용","recycling_ok":"재생원료 목표 충족","rejection_reasons":"조건 미충족 사유",
              "feasible":"조건부 비교 대상","fully_verified":"전체 실현가능성 검증완료","evidence_grade":"근거 구분",
              "effective_target":"적용 최소 전환비율(%)","savings_vs_a":"A 대비 비교비용 절감(원/년)",
              "collection_cost":"수거비용(원/년)","material_processing_cost":"물질재활용 처리비용(원/년)",
              "other_treatment_cost":"물질재활용 외 경로 비용(원/년)","processing_residue_cost":"재생공정 손실 처리비용(원/년)",
              "observed_material_treatment_t":"관측 물질재활용 처리량(톤/년)",
              "modeled_material_treatment_t":"가정 물질재활용 처리량(톤/년)","assumed_yield":"가정 최종 재처리 수율(%)",
              "other_pathways_t":"물질재활용 외 경로(톤/년)","processing_loss_t":"가정 재생공정 손실(톤/년)",
              "rate_clipped":"0~1 경계 보정 적용","observed_balance_error_t":"원표 반올림 수지 차이(톤/년)",
              "requested_target":"요청 전환비율(%)","selected_id":"조건부 최소비용안","minimum_cost":"최소 비교비용(원/년)",
              "feasible_count":"조건부 충족 대안 수","parameter":"변경 가정","value":"설정값","selected_final_rate":"선택안 가정 전환비율(%)"}
    output=frame.copy()
    for column in ("adoption","final_rate","effective_target","assumed_yield","requested_target","selected_final_rate"):
        if column in output:
            output[column]=pd.to_numeric(output[column])*100
    for column in ("costs_complete","recycling_ok","feasible","fully_verified","rate_clipped"):
        if column in output:
            output[column]=output[column].map({True:"예",False:"아니오"})
    return output.rename(columns=labels)

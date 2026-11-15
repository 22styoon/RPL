"""구로구 시설 대안의 조건부 비교를 위한 Streamlit 화면."""
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import json
from math import isfinite
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .facility_experiments import (
    COST_SCOPE,
    compare_facilities,
    evaluate_facility,
    minimum_cost_curve,
)
from .model import ROOT, best, number
from .presentation import korean_table


FACILITY_LABELS = {
    "baseline_final_rate": "A 기준 재생원료 전환비율(%)",
    "annual_budget_cap": "연간 비교비용 상한(원/년)",
    "comparison_cost_scope": "비용 포함범위",
    "budget_ok": "비교비용 상한 충족",
    "capacity_verified": "연간 용량 입력됨",
    "capacity_ok": "용량 조건 충족(미확인 허용 설정 반영)",
    "verified_feasible": "목표·예산·명시용량 충족(법규 제외)",
    "rejection_reasons": "탈락 이유",
    "verification_note": "용량 확인 상태",
    "selected_id": "조건부 최소 포함비용안",
    "selected_name": "선택 대안 설명",
    "minimum_comparison_cost": "최소 비교 포함비용(원/년)",
    "feasible_count": "조건부 후보 수",
}


def _korean_facility_table(table):
    displayed = table.copy()
    if "baseline_final_rate" in displayed:
        displayed["baseline_final_rate"] = (displayed["baseline_final_rate"] * 100).round(3)
    for column in ("budget_ok", "capacity_verified", "capacity_ok", "verified_feasible"):
        if column in displayed:
            displayed[column] = displayed[column].map({True: "예", False: "아니오"})
    return korean_table(displayed).rename(columns=FACILITY_LABELS)


def _numeric(value, label, upper=None, optional=False):
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        if optional:
            return None
        raise ValueError(f"{label}: 값을 입력해 주세요.")
    if isinstance(value, bool):
        raise ValueError(f"{label}: 숫자를 입력해 주세요.")
    try:
        parsed = float(value)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{label}: 숫자를 입력해 주세요.") from error
    return number(parsed, label, upper)


def _editor_rows(config):
    rows = []
    for scenario in config["scenarios"]:
        if scenario["id"] == "A":
            continue
        evaluated, _ = evaluate_facility(config, scenario)
        rows.append({
            "id": scenario["id"],
            "name": scenario["name"],
            "sorting_target": evaluated["sorting_rate"] * 100,
            "processing_yield": evaluated["processing_yield"] * 100,
            "collection_budget_multiplier": scenario["collection_budget_multiplier"],
            "sorting_budget_multiplier": scenario["sorting_budget_multiplier"],
            "additional_capital": scenario["additional_capital"],
            "capacity_t": scenario.get("capacity_t"),
        })
    return rows


def _apply_editor(config, edited, reference_yield):
    """A를 보존하고 편집된 대안만 교체한다. 비율 편집 단위는 %다."""
    sample = deepcopy(config)
    sample["common"]["processing_yield"] = number(reference_yield, "기준 수율", 1)
    originals = {scenario["id"]: scenario for scenario in sample["scenarios"]}
    baselines = [scenario for scenario in sample["scenarios"] if scenario["id"] == "A"]
    if len(baselines) != 1:
        raise ValueError("기준선 A가 정확히 하나여야 합니다.")
    baseline = deepcopy(baselines[0])
    baseline["processing_yield"] = reference_yield
    alternatives = []
    ids = {"A"}
    for index, row in enumerate(edited.to_dict("records"), start=1):
        scenario_id = row.get("id")
        name = row.get("name")
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ValueError(f"대안 {index}: 식별자를 입력해 주세요.")
        scenario_id = scenario_id.strip()
        if scenario_id.upper() == "A" or scenario_id in ids:
            raise ValueError("A는 고정 기준선이며 대안 식별자는 중복될 수 없습니다.")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{scenario_id}: 대안 설명을 입력해 주세요.")
        ids.add(scenario_id)
        candidate = deepcopy(originals.get(scenario_id, baseline))
        candidate.update(
            id=scenario_id,
            name=name.strip(),
            sorting_target=_numeric(row.get("sorting_target"), f"{scenario_id} 선별률", 100) / 100,
            processing_yield=_numeric(row.get("processing_yield"), f"{scenario_id} 수율", 100) / 100,
            collection_budget_multiplier=_numeric(
                row.get("collection_budget_multiplier"), f"{scenario_id} 수거예산 배율"
            ),
            sorting_budget_multiplier=_numeric(
                row.get("sorting_budget_multiplier"), f"{scenario_id} 선별예산 배율"
            ),
            additional_capital=_numeric(row.get("additional_capital"), f"{scenario_id} 추가 투자비"),
            capacity_t=_numeric(row.get("capacity_t"), f"{scenario_id} 연간 용량", optional=True),
        )
        alternatives.append(candidate)
    sample["scenarios"] = [baseline, *alternatives]
    return sample


def _facility_sources():
    sources = pd.read_csv(ROOT / "data/sources.csv", keep_default_na=False)
    return sources.loc[sources.source_id.isin(["GURO", "GURO_SYSTEM"])].copy()


def _export_bundle(config, constraints, results, flows, curve, sources):
    """현재 실행값만 메모리에서 묶는다. 로컬 인증설정은 접근하지 않는다."""
    settings = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "구로구 시설 조건부 비교",
        "config": config,
        "constraints": constraints,
        "comparison_cost_scope": COST_SCOPE,
        "fully_verified": False,
        "limitations": [
            "수거·선별 예산 대리값과 추가 투자 연금액이며 총사회적비용이 아님",
            "최종 재처리 수율·대안 효과는 외생 가정",
            "미입력 용량은 미확인, 법규·허가조건은 미검증",
            "혼합 재활용품 행정처리 흐름이며 구 전체 발생량·품목별 실적이 아님",
        ],
    }
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "현재_실행설정.json",
            json.dumps(settings, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"),
        )
        tables = {
            "시설_조건부_비교.csv": _korean_facility_table(results),
            "목표별_최소포함비용.csv": _korean_facility_table(curve),
            "자료_출처.csv": korean_table(sources),
            "대안별_물질흐름.csv": korean_table(flows),
        }
        for filename, table in tables.items():
            archive.writestr(filename, table.to_csv(index=False).encode("utf-8-sig"))
        archive.writestr(
            "해석_안내.txt",
            ("이 ZIP은 현재 화면의 시나리오·수율·목표·예산·용량 설정을 저장합니다.\n"
             "최종 재생원료량은 관측 선별량과 가정 수율의 곱입니다.\n"
             "비교비용은 예산 대리값이며 총사회적비용·확정 경제성이 아닙니다.\n"
             "미확인 용량과 법규·허가조건은 검증 완료가 아닙니다.\n").encode("utf-8"),
        )
    return output.getvalue()


def render_facility_experiment(config, target=None):
    """기존 구로구 설정을 복사해 시설 실험과 현재 실행값 ZIP을 표시한다."""
    st.subheader("구로구 시설 대안 조건부 실험")
    st.info(
        "비교액은 알려진 수거·선별 예산 대리값과 추가 투자 연금액입니다. "
        "가계·재처리·별도 처분비가 완비된 총사회적비용이 아닙니다."
    )
    st.caption(
        "구로구의 혼합 재활용품 수거·선별 행정처리 흐름을 비교합니다. "
        "최종 재생원료량과 대안 효과는 가정이며 법규·허가조건은 미검증입니다."
    )
    try:
        sample = deepcopy(config)
        number(sample["common"]["processing_yield"], "기준 최종 수율", 1)
        reference_yield = st.slider(
            "가정: 시설 기준 최종 재처리 수율(%)",
            min_value=0.0, max_value=100.0,
            value=float(sample["common"]["processing_yield"] * 100),
            step=0.5, key="facility_reference_yield",
        ) / 100
        sample["common"]["processing_yield"] = reference_yield
        baselines = [scenario for scenario in sample["scenarios"] if scenario["id"] == "A"]
        if len(baselines) != 1:
            raise ValueError("기준선 A가 정확히 하나여야 합니다.")
        # 기준 수율 슬라이더는 A의 외생 가정을 정하며 대안 편집과 분리한다.
        baselines[0]["processing_yield"] = reference_yield
        baseline, _ = evaluate_facility(sample, baselines[0])
        st.caption(
            f"고정 A: 관측 선별률 {baseline['sorting_rate']:.2%}, "
            f"기준 수율 {reference_yield:.2%}, 재생원료율 하한 {baseline['final_rate']:.2%}. "
            "아래 대안의 수율을 바꿔도 A의 하한은 낮아지지 않습니다."
        )
        if target is None:
            requested_target = st.slider(
                "가정: 시설 최소 재생원료 전환비율(%)",
                min_value=0.0, max_value=100.0, value=0.0,
                step=1.0, key="facility_minimum_target",
            ) / 100
        else:
            requested_target = number(target, "최소 재생원료 전환비율", 1)
            st.caption(f"공통 설정의 요청 목표 {requested_target:.2%}를 적용합니다.")
        annual_budget_cap = st.number_input(
            "연간 비교비용 상한(원/년, 빈칸은 상한 없음)",
            min_value=0.0, value=None, step=100000000.0,
            format="%.0f", placeholder="상한 없음", key="facility_annual_budget_cap",
        )
        require_known_capacity = st.checkbox(
            "연간 용량이 미확인인 대안도 비교 대상에서 제외",
            value=False, key="facility_require_known_capacity",
        )
        include_e = False
        if not any(scenario["id"] == "E" for scenario in sample["scenarios"]):
            include_e = st.checkbox("새 시설 대안 E 추가", value=False, key="facility_add_e")
        rows = _editor_rows(sample)
        if include_e:
            rows.append({
                "id": "E", "name": "사용자 지정 시설 대안",
                "sorting_target": baseline["sorting_rate"] * 100,
                "processing_yield": reference_yield * 100,
                "collection_budget_multiplier": 1.0, "sorting_budget_multiplier": 1.0,
                "additional_capital": 0.0, "capacity_t": None,
            })
        columns = [
            "id", "name", "sorting_target", "processing_yield",
            "collection_budget_multiplier", "sorting_budget_multiplier",
            "additional_capital", "capacity_t",
        ]
        editor = pd.DataFrame(rows, columns=columns)
        for column in columns[2:]:
            editor[column] = pd.to_numeric(editor[column], errors="coerce").astype(float)
        st.markdown("**시설 대안 설정**")
        st.caption(
            "B/C/D와 추가 대안을 편집합니다. 선별률·수율은 %이며 예산 배율 1은 기준 예산입니다. "
            "용량 빈칸은 미확인이고 0은 연간 용량 0t입니다. 행 추가 시 A 이외의 고유 식별자를 입력하세요."
        )
        edited = st.data_editor(
            editor, hide_index=True, width="stretch", num_rows="dynamic",
            key="facility_scenarios_editor",
            column_config={
                "id": st.column_config.TextColumn("식별자", required=True),
                "name": st.column_config.TextColumn("대안 설명", required=True),
                "sorting_target": st.column_config.NumberColumn(
                    "선별률(%)", min_value=0.0, max_value=100.0, step=0.1,
                    required=True, default=float(baseline["sorting_rate"] * 100), format="%.3f",
                ),
                "processing_yield": st.column_config.NumberColumn(
                    "가정 재처리 수율(%)", min_value=0.0, max_value=100.0, step=0.1,
                    required=True, default=float(reference_yield * 100), format="%.3f",
                ),
                "collection_budget_multiplier": st.column_config.NumberColumn(
                    "수거예산 배율", min_value=0.0, step=0.01, required=True, default=1.0,
                ),
                "sorting_budget_multiplier": st.column_config.NumberColumn(
                    "선별예산 배율", min_value=0.0, step=0.01, required=True, default=1.0,
                ),
                "additional_capital": st.column_config.NumberColumn(
                    "추가 투자비(원)", min_value=0.0, step=10000000.0,
                    required=True, default=0.0, format="%.0f",
                ),
                "capacity_t": st.column_config.NumberColumn(
                    "연간 처리용량(t/년, 빈칸 미확인)", min_value=0.0, step=100.0, format="%.1f",
                ),
            },
        )
        sample = _apply_editor(sample, edited, reference_yield)
        table = compare_facilities(
            sample, target=requested_target, annual_budget_cap=annual_budget_cap,
            require_known_capacity=require_known_capacity,
        )
        selected_id = best(table)
        selected = None if selected_id is None else table.loc[table.id == selected_id].iloc[0]
        metrics = st.columns(3)
        metrics[0].metric(
            "등록 대안 중 조건부 최소 포함비용안",
            "충족 대안 없음" if selected is None else selected_id,
        )
        metrics[1].metric(
            "비교 포함비용(원/년)",
            "—" if selected is None else f"{selected.comparison_cost:,.0f}",
        )
        metrics[2].metric(
            "가정 적용 재생원료 전환비율",
            "—" if selected is None else f"{selected.final_rate:.2%}",
        )
        st.caption(
            f"적용 최소 전환비율 {table.effective_target.iloc[0]:.2%}: "
            "요청 목표와 A의 하한 중 높은 값입니다. 연간 용량이 미확인이면 조건부 후보입니다. "
            "명시 용량 충족 여부와 별개로 법규 및 전체 제약 검증은 완료되지 않았습니다."
        )
        result_columns = [
            "id", "name", "sorting_rate", "processing_yield", "final_rate",
            "comparison_cost", "savings_vs_a", "recycling_ok", "budget_ok",
            "capacity_status", "feasible", "rejection_reasons", "verification_note",
        ]
        st.dataframe(
            _korean_facility_table(table[result_columns]), hide_index=True, width="stretch"
        )
        if selected is None:
            st.warning("현재 목표·예산·용량 조건을 충족하는 등록 대안이 없습니다. 표의 탈락 이유를 확인하세요.")

        flows_by_id = {}
        for scenario in sample["scenarios"]:
            _, flow = evaluate_facility(sample, scenario)
            flows_by_id[scenario["id"]] = flow.assign(id=scenario["id"], name=scenario["name"])
        names = dict(zip(table.id, table["name"]))
        flow_id = st.selectbox(
            "물질흐름을 확인할 시설 대안", table.id.tolist(),
            format_func=lambda scenario_id: f"{scenario_id}: {names[scenario_id]}",
            key="facility_flow_scenario",
        )
        st.dataframe(korean_table(flows_by_id[flow_id]), hide_index=True, width="stretch")
        st.caption(
            "구로구 품목별 구성은 미공표이므로 혼합 재활용품 합계 흐름입니다. "
            "선별 회수량과 최종 재생원료량을 구분하며 선별·공정 손실을 함께 표시합니다."
        )

        targets = {index / 20 for index in range(21)}
        targets.add(float(requested_target))
        for final_rate in table.final_rate:
            if isfinite(final_rate):
                targets.add(float(final_rate))
                targets.add(min(1.0, float(final_rate) + 1e-8))
        curve = minimum_cost_curve(
            sample, sorted(targets), annual_budget_cap=annual_budget_cap,
            require_known_capacity=require_known_capacity,
        )
        figure = go.Figure(go.Scatter(
            x=curve.requested_target * 100, y=curve.minimum_comparison_cost,
            mode="lines+markers", line_shape="hv", connectgaps=False,
            text=curve.selected_id.fillna("충족 대안 없음"),
            hovertemplate="요청 목표 %{x:.3f}%<br>비교비용 %{y:,.0f}원/년<br>대안 %{text}<extra></extra>",
            name="등록 대안 최소 포함비용",
        ))
        figure.update_layout(
            title="목표별 조건부 최소 포함비용", xaxis_title="요청 재생원료 전환비율(%)",
            yaxis_title="비교 포함비용(원/년)", showlegend=False,
        )
        st.plotly_chart(figure, width="stretch")
        st.caption(
            "등록한 이산 대안의 단계형 곡선입니다. 충족 대안이 없는 목표는 공백으로 남깁니다. "
            "새로운 설비 조합의 연속 최적화 결과가 아닙니다."
        )
        with st.expander("목표별 비교표"):
            st.dataframe(_korean_facility_table(curve), hide_index=True, width="stretch")
        constraints = {
            "requested_target": float(requested_target),
            "effective_target": float(table.effective_target.iloc[0]),
            "baseline_final_rate": float(table.baseline_final_rate.iloc[0]),
            "annual_budget_cap": annual_budget_cap,
            "require_known_capacity": require_known_capacity,
            "capacity_unit": "t/year, 처리대상량 기준",
        }
        sources = _facility_sources()
        bundle = _export_bundle(
            sample, constraints, table, pd.concat(flows_by_id.values(), ignore_index=True), curve, sources
        )
        st.download_button(
            "시설 실험 현재값·결과·출처 ZIP 저장", data=bundle,
            file_name="구로구_시설_조건부_실험.zip", mime="application/zip",
            key="facility_export_zip",
        )
        return table
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as error:
        st.error(f"시설 실험 입력을 확인해 주세요: {error}")
        return None

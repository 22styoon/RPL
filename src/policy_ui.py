"""전국·시도 4품목 조건부 정책 실험의 Streamlit 화면.

정책 계산과 자료 검증은 national_policy에 위임한다. 화면에서 비어 있는
비용·가계·용량 입력을 0으로 치환하지 않으며 A 기준선은 편집하지 않는다.
"""

from copy import deepcopy
import json
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.national_policy import (
    available_regions,
    default_curve_targets,
    compare_policies,
    export_bundle,
    input_snapshot,
    load_policy_config,
    selected_policy,
    sensitivity,
    target_curve,
    translate_table,
)


_PREFIX = "national_policy_"
_MATERIALS = ("폐지류", "폐합성수지류", "폐금속류", "폐유리류")
_COST_LABELS = {
    "collection_per_t": "수거·운반 단가(원/발생 톤)",
    "material_processing_per_t": "물질재활용 처리 단가(원/처리 톤)",
    "other_treatment_per_t": "다른 처리경로 단가(원/해당 톤)",
    "processing_residue_per_t": "공정손실 처리 단가(원/손실 톤)",
}
_PARAMETER_LABELS = {
    "baseline_yield": "기준선 최종 수율",
    "baseline_yields": "기준선 최종 수율",
    "processing_yield": "최종 수율",
    "yield": "최종 수율",
    "yield_multiplier": "최종 수율 배율",
    "yield_shift_pp": "최종 수율 변화",
    "collection_per_t": "수거·운반 단가",
    "material_processing_per_t": "물질재활용 처리 단가",
    "other_treatment_per_t": "다른 처리경로 단가",
    "processing_residue_per_t": "공정손실 처리 단가",
    "cost_multiplier": "비용 단가 배율",
    "unit_cost_multiplier": "비용 단가 배율",
    "collection_factor": "수거비 배율",
    "processing_factor": "물질처리비 배율",
    "time_value": "가계 시간가치",
    "discount_rate": "연간 할인율",
}
_SCENARIO_FIELDS = (
    "id", "name", "treatment_change_pp", "yield_change_pp",
    "collection_factor", "processing_factor", "other_factor", "capital",
    "additional_capacity_t", "producer_real_per_t", "household_time_factor",
)
_SCENARIO_LABELS = {
    "id": "정책",
    "name": "정책 설명",
    "treatment_change_pp": "물질재활용 처리비율 변화(%p)",
    "yield_change_pp": "최종 수율 변화(%p)",
    "collection_factor": "수거·운반비 배율",
    "processing_factor": "물질처리비 배율",
    "other_factor": "다른 경로 비용 배율",
    "capital": "추가 투자비(원)",
    "additional_capacity_t": "추가 처리용량(톤/년)",
    "producer_real_per_t": "생산자 실질비용(원/발생 톤)",
    "household_time_factor": "가계 분리배출 시간 배율",
}


def _missing(value):
    if value is None:
        return True
    try:
        return bool(pd.isna(value)) or not math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _korean_table(frame):
    """화면·CSV·ZIP의 한글 명칭과 단위를 동일하게 유지한다."""
    return translate_table(frame)


def _csv(frame):
    return _korean_table(frame).to_csv(index=False).encode("utf-8-sig")


def _optional_number(label, value, key, *, integer=False, step=1000.0, help=None):
    """빈칸은 None으로 반환하며 측정되지 않은 값을 만들지 않는다."""
    options = dict(
        label=label,
        min_value=0 if integer else 0.0,
        value=None if _missing(value) else (int(value) if integer else float(value)),
        step=int(step) if integer else float(step),
        key=_PREFIX + key,
        placeholder="미입력",
        help=help,
    )
    return st.number_input(**options)


def _edit_inputs(config):
    input_tabs = st.tabs(["지역·최종 수율", "비용·가계", "목표·예산·용량"])
    with input_tabs[0]:
        regions = list(available_regions())
        if not regions:
            raise ValueError("지역 목록이 없습니다. KOSIS 품목 집계자료를 확인하세요.")
        current = config.get("region", "전국")
        config["region"] = st.selectbox(
            "정책 실험 지역", regions,
            index=regions.index(current) if current in regions else 0,
            key=_PREFIX + "region",
        )
        st.caption(
            f"기준연도: {config['reference_year']}년 · 대상: 폐지류·폐합성수지류·폐금속류·폐유리류. "
            "선택 지역의 대응 4품목만 비교하며 생활폐기물 전체 결과로 확대하지 않습니다."
        )
        cols = st.columns(4)
        for column, material in zip(cols, _MATERIALS):
            with column:
                config["baseline_yields"][material] = st.number_input(
                    f"가정: {material} 최종 수율(%)",
                    min_value=0.0, max_value=100.0,
                    value=float(config["baseline_yields"][material]) * 100,
                    step=1.0, key=_PREFIX + "yield_" + material,
                ) / 100
        st.caption(
            "최종 수율은 물질재활용 처리량 중 최종 재생원료가 되는 비중에 대한 D등급 가정입니다. "
            "KOSIS의 물질재활용 처리비율을 수거율·선별률로 분해하거나 최종 수율로 해석하지 않습니다."
        )
    with input_tabs[1]:
        st.caption(
            "KOSIS 처리실적에는 아래 단가가 없습니다. 근거 또는 명시적 가정을 입력하세요. "
            "빈칸은 미입력이며, 0원도 사용자가 명시적으로 입력한 경우에만 적용합니다."
        )
        cols = st.columns(2)
        for index, (field, label) in enumerate(_COST_LABELS.items()):
            with cols[index % 2]:
                config["costs"][field] = _optional_number(
                    label, config["costs"].get(field), "cost_" + field,
                )
        economics = config["economics"]
        economics["include_household"] = st.checkbox(
            "가계 분리배출 시간비용을 비교에 포함",
            value=bool(economics.get("include_household", False)),
            key=_PREFIX + "include_household",
        )
        if economics["include_household"]:
            left, right = st.columns(2)
            with left:
                economics["households"] = _optional_number(
                    "가정: 해당 지역의 대상 가구 수(가구)", economics.get("households"),
                    "households", integer=True, step=1000,
                )
                economics["time_value"] = st.number_input(
                    "가정: 가계 시간가치(원/시간)", min_value=0.0,
                    value=float(economics["time_value"]), step=100.0,
                    key=_PREFIX + "time_value",
                )
            with right:
                economics["baseline_minutes_per_week"] = _optional_number(
                    "가정: 기준선 가구당 주간 분리배출 시간(분)",
                    economics.get("baseline_minutes_per_week"),
                    "baseline_minutes_per_week", step=1.0,
                )
            st.caption(
                "가구 수와 분리배출 시간의 지역 실측값은 제공되지 않았습니다. "
                "시간가치 기본값 9,860원/시간은 2024년 최저임금을 활용한 가정입니다."
            )
        left, right = st.columns(2)
        with left:
            economics["discount_rate"] = st.number_input(
                "가정: 투자비 연간화 할인율(%)",
                min_value=0.0, max_value=100.0,
                value=float(economics["discount_rate"]) * 100, step=0.5,
                key=_PREFIX + "discount_rate",
            ) / 100
        with right:
            economics["life_years"] = st.number_input(
                "가정: 추가 투자 사용기간(년)", min_value=1,
                value=int(economics["life_years"]), step=1,
                key=_PREFIX + "life_years",
            )
    with input_tabs[2]:
        constraints = config["constraints"]
        constraints["minimum_final_rate"] = st.number_input(
            "요청: 최소 최종 재생원료 전환비율(%)",
            min_value=0.0, max_value=100.0,
            value=float(constraints["minimum_final_rate"]) * 100, step=1.0,
            key=_PREFIX + "minimum_final_rate",
        ) / 100
        left, right = st.columns(2)
        with left:
            constraints["annual_public_budget"] = _optional_number(
                "연간 공공예산 상한(원/년)",
                constraints.get("annual_public_budget"), "annual_public_budget",
                step=1000000.0,
            )
        with right:
            constraints["material_capacity_t"] = _optional_number(
                "기준선 물질재활용 단계 처리용량(톤/년)",
                constraints.get("material_capacity_t"), "material_capacity_t",
                step=1000.0,
            )
        constraints["require_known_capacity"] = st.checkbox(
            "처리용량 미확인 정책을 비교에서 제외",
            value=bool(constraints.get("require_known_capacity", False)),
            key=_PREFIX + "require_known_capacity",
        )
        st.caption(
            "최소 전환비율은 요청값과 A의 가정 적용 전환비율 중 큰 값입니다. "
            "물질재활용 단계 용량에만 용량 제약을 적용합니다. "
            "공란인 예산·용량은 해당 제약의 검증 근거를 제공하지 않습니다."
        )


def _scenario_frame(scenarios):
    frame = pd.DataFrame([
        {field: scenario.get(field) for field in _SCENARIO_FIELDS}
        for scenario in scenarios
    ])
    if frame.empty:
        return frame
    for field in _SCENARIO_FIELDS:
        if field not in ("id", "name"):
            frame[field] = pd.to_numeric(frame[field], errors="coerce").astype(float)
    for field in ("treatment_change_pp", "yield_change_pp"):
        frame[field] = frame[field] * 100
    return frame


def _edit_scenarios(config):
    st.subheader("정책별 외생 가정")
    baseline = [scenario for scenario in config["scenarios"] if scenario["id"] == "A"]
    if len(baseline) != 1:
        raise ValueError("편집하지 않는 A 기준선이 정확히 하나 필요합니다.")
    with st.expander("A 기준선 설정 보기", expanded=False):
        st.dataframe(
            _scenario_frame(baseline).rename(columns=_SCENARIO_LABELS),
            hide_index=True, width="stretch",
        )
    alternatives = [scenario for scenario in config["scenarios"] if scenario["id"] != "A"]
    editor_columns = {
        "id": st.column_config.TextColumn("정책", disabled=True),
        "name": st.column_config.TextColumn("정책 설명", required=True),
    }
    for field in _SCENARIO_FIELDS:
        if field in ("id", "name"):
            continue
        is_pp = field in ("treatment_change_pp", "yield_change_pp")
        editor_columns[field] = st.column_config.NumberColumn(
            _SCENARIO_LABELS[field],
            min_value=-100.0 if is_pp else 0.0,
            max_value=100.0 if is_pp else None,
            step=0.1 if is_pp else (0.05 if field.endswith("factor") else 1000.0),
            required=True,
            format="%.2f" if is_pp or field.endswith("factor") else "%.0f",
        )
    edited = st.data_editor(
        _scenario_frame(alternatives), column_config=editor_columns,
        hide_index=True, num_rows="fixed", width="stretch",
        key=_PREFIX + "scenario_editor",
    )
    rows_by_id = {str(row["id"]): row for row in edited.to_dict("records")}
    for scenario in alternatives:
        row = rows_by_id.get(str(scenario["id"]))
        if row is None:
            raise ValueError(f"{scenario['id']} 정책의 편집 행이 없습니다.")
        if not str(row.get("name", "")).strip():
            raise ValueError(f"{scenario['id']} 정책 설명을 입력하세요.")
        scenario["name"] = str(row["name"])
        for field in _SCENARIO_FIELDS:
            if field in ("id", "name"):
                continue
            value = row[field]
            if _missing(value):
                raise ValueError(f"{scenario['id']}의 {_SCENARIO_LABELS[field]}을 입력하세요.")
            scenario[field] = float(value) / 100 if field.endswith("_pp") else float(value)
    config["scan_adoption"] = st.checkbox(
        "B·C·D의 적용 비중 25·50·75·100%를 함께 비교",
        value=bool(config.get("scan_adoption", False)),
        key=_PREFIX + "scan_adoption",
    )
    st.caption(
        "표의 변화량 단위는 %p입니다. 예: 3.0은 처리비율 또는 수율에 3%p를 더합니다. "
        "B·C·D 효과는 D등급 가정입니다. 적용 비중 탐색은 정해진 0.25·0.5·0.75·1 비중에서 "
        "기준선과 정책 가정을 조건부 선형보간하며, 연속 최적화나 인과효과 추정이 아닙니다."
    )


def _render_results(config, results):
    selected = selected_policy(results)
    complete = results["costs_complete"].fillna(False).astype(bool)
    feasible = results["feasible"].fillna(False).astype(bool)
    cols = st.columns(3)
    selection_label = selected or ("비용 입력 후 순위 산정" if not bool(complete.all()) else "선정 없음")
    cols[0].metric("조건부 최소 비교비용 정책", selection_label)
    cols[1].metric("조건부 비교 대상", f"{int(feasible.sum())} / {len(results)}개")
    cols[2].metric("필수 비용 입력완료", f"{int(complete.sum())} / {len(results)}개")
    missing = [label for field, label in _COST_LABELS.items() if _missing(config["costs"].get(field))]
    economics = config["economics"]
    if economics["include_household"]:
        if _missing(economics.get("households")):
            missing.append("대상 가구 수")
        if _missing(economics.get("baseline_minutes_per_week")):
            missing.append("기준선 분리배출 시간")
    if not bool(complete.all()):
        suffix = " · ".join(missing) if missing else "정책별 비용 입력을 확인하세요."
        st.warning("비용이 완성되지 않은 정책은 최소비용 순위에서 제외합니다. 미입력: " + suffix)
    if selected is None and bool(complete.any()):
        st.info("현재 입력에서 비용과 적용 제약조건을 함께 충족한 정책이 없습니다. 아래 탈락 사유를 확인하세요.")
    baseline = results.loc[results["policy_id"].astype(str) == "A"]
    requested = float(config["constraints"]["minimum_final_rate"])
    if not baseline.empty:
        floor = max(requested, float(baseline.iloc[0]["final_rate"]))
        st.caption(f"요청 최소 전환비율 {requested:.2%} · A 유지 조건을 반영한 적용 하한 {floor:.2%}")
    st.dataframe(_korean_table(results), hide_index=True, width="stretch")
    st.download_button(
        "한글 정책 비교 CSV", _csv(results), "policy_comparison.csv", "text/csv",
        key=_PREFIX + "results_csv",
    )
    chart = go.Figure(go.Bar(
        x=results["policy_id"].astype(str),
        y=pd.to_numeric(results["final_rate"], errors="coerce") * 100,
        text=results["name"], name="가정 적용 최종 전환비율",
    ))
    chart.add_hline(y=requested * 100, line_dash="dot", annotation_text="요청 하한")
    if not baseline.empty:
        chart.add_hline(
            y=float(baseline.iloc[0]["final_rate"]) * 100,
            line_dash="dash", line_color="#777777", annotation_text="A 유지 하한",
        )
    chart.update_layout(
        xaxis_title="정책 식별자", yaxis_title="최종 재생원료 전환비율(%)",
        yaxis_rangemode="tozero", showlegend=False,
    )
    st.plotly_chart(chart, width="stretch")
    known = results.loc[pd.to_numeric(results["comparison_cost"], errors="coerce").notna()]
    if not known.empty:
        cost_chart = go.Figure()
        for allowed, label, color in ((True, "조건부 비교 대상", "#237a63"), (False, "제약 미충족", "#a5a5a5")):
            subset = known.loc[known["feasible"].fillna(False).astype(bool) == allowed]
            if not subset.empty:
                cost_chart.add_trace(go.Scatter(
                    x=subset["final_rate"] * 100, y=subset["comparison_cost"],
                    text=subset["policy_id"], mode="markers+text",
                    textposition="top center", name=label,
                    marker={"size": 11, "color": color},
                ))
        cost_chart.update_layout(
            xaxis_title="가정 적용 최종 재생원료 전환비율(%)",
            yaxis_title="선택 범위 비교비용(원/년)",
        )
        st.plotly_chart(cost_chart, width="stretch")
    st.caption(
        "입력된 비용항목 소계는 미입력 비용을 제외한 참고값이며 정책 순위의 근거가 아닙니다. "
        "용량·법규 등 전체 실현가능성이 검증된 정책을 뜻하지 않습니다."
    )


def _render_flows(flows):
    st.subheader("정책별 물질수지")
    if flows.empty:
        st.info("표시할 물질수지 결과가 없습니다.")
        return
    policies = flows["policy_id"].drop_duplicates().astype(str).tolist()
    policy = st.selectbox("물질수지 정책", policies, key=_PREFIX + "flow_policy")
    chosen = flows.loc[flows["policy_id"].astype(str) == policy]
    st.dataframe(_korean_table(chosen), hide_index=True, width="stretch")
    quantities = [
        float(chosen[column].sum()) for column in (
            "modeled_material_treatment_t", "other_pathways_t", "final_t", "processing_loss_t"
        )
    ]
    if all(math.isfinite(value) and value >= 0 for value in quantities):
        chart = go.Figure(go.Sankey(
            node={"label": ["4품목 발생량", "물질재활용 처리", "다른 처리경로", "예상 최종 재생원료", "가정 공정손실"]},
            link={"source": [0, 0, 1, 1], "target": [1, 2, 3, 4], "value": quantities},
        ))
        chart.update_layout(title=f"{policy} · 연간 물질수지(톤/년)")
        st.plotly_chart(chart, width="stretch")
    st.caption(
        "다른 처리경로에는 물질재활용 이외 경로를 묶었습니다. 공정손실은 최종 수율 가정에서 "
        "산출한 값이며, 실제 처분 경로를 확인한 수치가 아닙니다."
    )
    st.download_button(
        "한글 전체 물질수지 CSV", _csv(flows), "policy_material_flows.csv", "text/csv",
        key=_PREFIX + "flows_csv",
    )


def _curve_targets(config, results):
    return default_curve_targets(config, results)


def _render_curve(config, results):
    st.subheader("목표–최소 비교비용 곡선")
    curve = target_curve(config, _curve_targets(config, results))
    numeric_cost = pd.to_numeric(curve["minimum_cost"], errors="coerce")
    if numeric_cost.notna().any():
        chart = go.Figure(go.Scatter(
            x=curve["requested_target"] * 100,
            y=numeric_cost,
            mode="lines+markers",
            line={"shape": "hv"},
            connectgaps=False,
            customdata=curve["selected_id"].fillna("선정 없음"),
            hovertemplate="요청 목표 %{x:.2f}%<br>최소 비교비용 %{y:,.0f}원/년<br>%{customdata}<extra></extra>",
            name="조건부 최소 비교비용",
        ))
        chart.update_layout(
            xaxis_title="요청 최소 최종 재생원료 전환비율(%)",
            yaxis_title="최소 비교비용(원/년)",
        )
        st.plotly_chart(chart, width="stretch")
    else:
        st.info("비용 또는 제약조건을 충족하는 후보가 없어 최소비용 곡선이 비어 있습니다.")
    st.caption(
        "등록 정책과 선택한 적용 비중에서 얻은 단계 곡선입니다. 선정할 정책이 없는 목표 구간은 "
        "선을 연결하지 않습니다. 모든 목표에 A의 가정 적용 전환비율을 하한으로 적용합니다."
    )
    with st.expander("목표별 계산값"):
        st.dataframe(_korean_table(curve), hide_index=True, width="stretch")
    st.download_button(
        "한글 목표 곡선 CSV", _csv(curve), "policy_target_curve.csv", "text/csv",
        key=_PREFIX + "curve_csv",
    )


def _render_sensitivity(config):
    st.subheader("가정 민감도")
    experiments = sensitivity(config)
    st.caption(
        "한 번에 한 가정을 바꾸고 정책을 다시 비교합니다. 다른 입력과 제약조건은 현재 설정을 "
        "유지합니다. 통계적 신뢰구간이나 정책효과의 불확실성 분포를 뜻하지 않습니다. "
        "표의 최종 재처리 수율 설정값은 0~1 비율입니다(0.85 = 85%)."
    )
    st.dataframe(_korean_table(experiments), hide_index=True, width="stretch")
    if not experiments.empty:
        for parameter, subset in experiments.groupby("parameter", sort=False):
            numeric_cost = pd.to_numeric(subset["minimum_cost"], errors="coerce")
            if numeric_cost.notna().any():
                chart = go.Figure(go.Scatter(
                    x=subset["value"], y=numeric_cost, mode="lines+markers",
                    connectgaps=False,
                    customdata=subset["selected_id"].fillna("선정 없음"),
                    hovertemplate="설정값 %{x}<br>최소 비교비용 %{y:,.0f}원/년<br>%{customdata}<extra></extra>",
                ))
                chart.update_layout(
                    title=_PARAMETER_LABELS.get(parameter, parameter),
                    xaxis_title="변경 설정값", yaxis_title="최소 비교비용(원/년)",
                )
                st.plotly_chart(chart, width="stretch")
    st.download_button(
        "한글 민감도 CSV", _csv(experiments), "policy_sensitivity.csv", "text/csv",
        key=_PREFIX + "sensitivity_csv",
    )


def render_policy_experiment():
    """app.py의 조건부 정책 실험 탭 안에서 호출한다."""
    st.subheader("전국·시도 4품목 조건부 정책 실험")
    st.info(
        "KOSIS 관측값은 발생량과 물질재활용 처리량입니다. 최종 재생원료 전환량과 B·C·D의 정책효과는 "
        "D등급 가정입니다. 비교액은 입력 단가·투자 연간화·포함한 가계 시간비용·생산자 실질비용의 "
        "선택 범위 비교비용이며, 총사회비용이 아닙니다."
    )
    try:
        config = deepcopy(load_policy_config())
        with st.expander("실험 입력", expanded=True):
            _edit_inputs(config)
        _edit_scenarios(config)
        results, flows = compare_policies(config)
    except Exception as error:
        st.error(f"정책 실험을 계산하지 못했습니다: {error}")
        st.caption("지역별 KOSIS 4품목 집계 파일, 설정 파일, 입력의 단위와 필수값을 확인하세요.")
        return
    if results.empty:
        st.warning("비교할 정책이 없습니다. 정책 설정과 지역 데이터를 확인하세요.")
        return
    result_tabs = st.tabs(["정책 비교", "물질수지", "목표 곡선", "민감도", "입력·내려받기"])
    with result_tabs[0]:
        _render_results(config, results)
    with result_tabs[1]:
        _render_flows(flows)
    with result_tabs[2]:
        try:
            _render_curve(config, results)
        except Exception as error:
            st.warning(f"목표 곡선을 계산하지 못했습니다: {error}")
    with result_tabs[3]:
        try:
            _render_sensitivity(config)
        except Exception as error:
            st.warning(f"민감도를 계산하지 못했습니다: {error}")
    with result_tabs[4]:
        st.subheader("현재 실행 입력 스냅샷")
        snapshot = input_snapshot(config)
        st.json(snapshot, expanded=False)
        st.download_button(
            "입력 스냅샷 JSON",
            json.dumps(snapshot, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
            "policy_input_snapshot.json", "application/json",
            key=_PREFIX + "snapshot_json",
        )
        st.caption(
            "스냅샷과 ZIP은 현재 화면에서 적용한 가정 및 계산 결과를 보존합니다. "
            "미입력은 미입력으로 기록하며, 비용 입력은 공식 관측비용으로 격상하지 않습니다."
        )
        try:
            bundle = export_bundle(config, results=results, flows=flows)
            st.download_button(
                "현재 실험 전체 ZIP", bundle, "policy_experiment.zip", "application/zip",
                key=_PREFIX + "bundle_zip",
            )
        except Exception as error:
            st.warning(f"ZIP 파일을 만들지 못했습니다: {error}")

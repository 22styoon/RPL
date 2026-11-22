"""Evidence-based indicator study: offline tables, figures, report and provenance."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from string import Template
import base64
import hashlib
import html
import json
import os
import re
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from src.model import ROOT
from .standardization import compute_standardization
from .recycling_indicator import BOUNDARY, evaluate_rates, pool_three_years
from .indicator_robustness import build_robustness_tables, DOMAIN_LABELS

TITLE = "재활용률은 같은 것을 측정하고 있는가?"
COLORS = ["#25657d", "#c17b36", "#367c68", "#856394"]


def build_tables(root=ROOT):
    root = Path(root)
    kr = pd.read_csv(root / "data/processed/kosis_materials_2024.csv")
    sg_path = root / "data/processed/international/nea/records.csv"
    sg = pd.read_csv(sg_path)
    meta_path = sg_path.with_name("manifest.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    raw = root / meta["raw_file"].replace("\\", "/")
    for path, expected in [(sg_path, meta["processed_sha256"]), (raw, meta["sha256"])]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("NEA source hash mismatch: " + str(path))
    national = kr.loc[kr.geography.eq("전국")]
    if len(national) != 4 or national.generated_t.le(0).any():
        raise ValueError("Expected four national material rows")
    generated = float(national.generated_t.sum())
    numerator = national[["recycling_total_t", "material_recycling_t", "energy_recovery_t"]].sum()
    if not np.isclose(numerator.recycling_total_t, numerator.material_recycling_t + numerator.energy_recovery_t, atol=.5, rtol=0):
        raise ValueError("KOSIS treatment split fails mass check")
    energy = pd.DataFrame([
        {"기준": label, "발생량(t)": generated, "분자(t)": mass, "처리비율(%)": 100 * mass / generated,
         "자료구분": "실제 행정통계·4재질 처리량", "출처ID": "KOSIS24"}
        for label, mass in [("에너지회수 포함 처리총량", numerator.recycling_total_t),
                            ("물질재활용 처리량", numerator.material_recycling_t)]])
    subset = sg.loc[sg.year.eq(2024) & sg.metric.isin(["generated", "recycled"])]
    if subset.duplicated(["material", "metric"]).any():
        raise ValueError("Duplicate NEA material metric")
    wide = subset.pivot(index="material", columns="metric", values="value")
    if wide.isna().any().any() or not {"Overall", "Construction & Demolition (C&D)", "Used slag"}.issubset(wide.index):
        raise ValueError("Missing NEA scope evidence")
    # Overall is authoritative; component sums are rounded and never added to it.
    rows = []
    for label, excluded in [("원표 전체 범위", []), ("건설·해체 제외", ["Construction & Demolition (C&D)"]),
                            ("건설·해체·사용 슬래그 제외", ["Construction & Demolition (C&D)", "Used slag"])]:
        values = wide.loc["Overall"] - (wide.loc[excluded].sum() if excluded else 0)
        rows.append({"범위": label, "발생량(t)": values.generated, "보고 재활용량(t)": values.recycled,
                     "보고량으로 계산한 비율(%)": 100 * values.recycled / values.generated,
                     "자료구분": "실제 공식통계의 범위 민감도", "출처ID": "NEA24"})
    scope = pd.DataFrame(rows)
    swiss = pd.DataFrame([
        {"재질": material, "단계": stage, "비율(%)": rate, "자료구분": "문헌 사례·스위스 2012 MFA", "출처ID": "HAUPT17"}
        for material, collected, final in [("종이", 74, 59), ("판지", 89, 81)]
        for stage, rate in [("수거 단계", collected), ("재생자원 산출 단계", final)]])
    scores, contributions, sensitivity, summary, weights = compute_standardization(kr)
    common = sensitivity.loc[~sensitivity["가중치 기준"].str.contains("제외")]
    span = common.groupby("시도")["표준화 처리비율(%)"].agg(["min", "max"])
    regional = scores[["시도", "관측 처리비율 R_r(%)", "전국 고정가중 표준화 S_r(%)", "구성 차이 R-S(%p)"]].merge(span, left_on="시도", right_index=True)
    regional = regional.rename(columns={"min": "공통 가중치 대안 최솟값(%)", "max": "공통 가중치 대안 최댓값(%)"})
    regional["자료구분"] = "실제 행정통계·최종 산출률 아님"
    regional["출처ID"] = "KOSIS24"

    demo = pd.DataFrame([
        {"entity": entity, "year": 2024, "material": material, "generated_t": mass,
         "secondary_output_t": mass * rate, "source_id": "constructed_example", "source_locator": "연구보고서 5절",
         **BOUNDARY}
        for entity, masses, rates in [("A", [900, 100], [.8, .2]), ("B", [100, 900], [.9, .3])]
        for material, mass, rate in zip(["paper", "plastic"], masses, rates)])
    demo["자료구분"] = "가상 설명·국가 관측 아님"
    demo_scores, _ = evaluate_rates(demo, {"paper": .5, "plastic": .5})
    simpson = demo_scores[["entity", "H_pct", "S_pct"]].rename(columns={"entity": "가상 국가", "H_pct": "실제 구성 H(%)", "S_pct": "50:50 표준화 S(%)"})
    simpson["자료구분"] = "가상 설명·국가 관측 아님"
    temporal = []
    for year, mass, rate in [(2022, 200, .3), (2023, 100, .5), (2024, 50, .7)]:
        part = demo.loc[demo.entity.eq("A")].copy()
        part["year"], part["generated_t"], part["secondary_output_t"] = year, mass, mass * rate
        temporal.append(part)
    temporal_input = pd.concat(temporal, ignore_index=True)
    pooled, _ = pool_three_years(temporal_input, {"paper": .5, "plastic": .5}, end_year=2024)
    time = pd.DataFrame({"집계 방법": ["최근 연도", "연간 비율 단순평균", "재질별 질량 3년 합산", "0.2·0.3·0.5 예시"],
                         "비율(%)": [70, np.mean([30, 50, 70]), pooled.S_pct.iloc[0], np.dot([.2, .3, .5], [30, 50, 70])],
                         "자료구분": "가상 설명·EPR 산식 재현 아님"})
    incomplete = demo.loc[demo.entity.eq("A")].copy()
    incomplete.loc[incomplete.material.eq("plastic"), "secondary_output_t"] = np.nan
    bounded, _ = evaluate_rates(incomplete, {"paper": .5, "plastic": .5})
    bounded["자료구분"] = "가상 설명·식별구간, 신뢰구간 아님"
    mass_flow = pd.DataFrame({"경로": ["발생→미수거", "발생→수거", "수거→선별잔재", "수거→공정투입", "공정투입→공정손실", "공정투입→최종재생물질"],
                              "질량(t)": [30, 70, 14, 56, 14, 42], "자료구분": "가상 설명·동일 물질 기준"})
    causal = pd.DataFrame([
        ("정책", "수거", "가설 물리 경로"), ("수거", "선별", "가설 물리 경로"), ("선별", "최종 산출", "가설 물리 경로"),
        ("최종 산출", "1차 원료 대체", "품질·시장 조건에 의존"),
        ("1차 원료 대체", "환경영향", "LCA·반사실 필요"), ("지역·시장 여건", "정책", "잠재 교란"),
        ("지역·시장 여건", "최종 산출", "잠재 교란"), ("정의·측정점", "보고 재활용률", "측정 효과"),
        ("최종 산출", "보고 재활용률", "물리량의 보고 반영")], columns=["출발", "도착", "경로 의미"])
    causal["자료구분"] = "인과 가설·효과 추정 없음"
    tables = {"swiss_stages": swiss, "nea_scope": scope, "kosis_energy": energy,
            "regional_scores": regional, "regional_weights": weights, "regional_sensitivity": sensitivity,
            "regional_contributions": contributions, "weight_summary": summary,
            "composition_example": simpson, "composition_inputs": demo,
            "time_methods": time, "time_inputs": temporal_input, "partial_bounds": bounded,
            "partial_inputs": incomplete, "mass_flow": mass_flow, "causal_edges": causal}
    tables.update(build_robustness_tables(kr))
    evidence = root / "data/indicator_followup_observations.csv"
    tables["jrc_plastics"] = pd.read_csv(evidence)
    jrc=tables["jrc_plastics"]
    required_jrc = {"indicator", "rate_pct", "reference_year", "publication_year", "scope", "measurement_type", "source_id", "source_locator"}
    if not required_jrc.issubset(jrc.columns) or len(jrc)!=2 or not jrc.source_id.eq("JRC25").all() or not jrc.reference_year.eq(2022).all() or not jrc.publication_year.eq(2025).all() or not jrc.rate_pct.between(0,100).all():
        raise ValueError("Expected two labelled EU-27 2022 JRC model rates")
    if not jrc.indicator.iloc[0].startswith("적정 수거율") or not jrc.indicator.iloc[1].startswith("폐기 후 재활용률"):
        raise ValueError("JRC collection and EOL rates must retain their measurement labels and order")
    return tables, [
                root / "data/processed/kosis_materials_2024.csv", sg_path, meta_path, raw, evidence]


def _grouped(frame, category, series, value, labels=None):
    fig = go.Figure()
    for index, label in enumerate(labels or list(frame[series].unique())):
        part = frame.loc[frame[series].eq(label)]
        fig.add_bar(x=part[category], y=part[value], name=label, marker_color=COLORS[index % len(COLORS)])
    fig.update_layout(barmode="group", yaxis_title="비율 (%)", yaxis_range=[0, 100])
    return fig


def build_figures(tables):
    figs = {}
    figs["swiss_stages"] = _grouped(tables["swiss_stages"], "재질", "단계", "비율(%)")
    for name, category, value in [("nea_scope", "범위", "보고량으로 계산한 비율(%)"),
                                  ("kosis_energy", "기준", "처리비율(%)"), ("time_methods", "집계 방법", "비율(%)")]:
        part = tables[name]
        fig = go.Figure(go.Bar(x=part[category], y=part[value], marker_color=COLORS[0], text=part[value], texttemplate="%{text:.2f}%", textposition="outside"))
        fig.update_layout(yaxis_range=[0, 100], yaxis_title="비율 (%)")
        figs[name] = fig
    regional = tables["regional_scores"].sort_values("전국 고정가중 표준화 S_r(%)")
    fig = go.Figure()
    for _, row in regional.iterrows():
        fig.add_trace(go.Scatter(x=[row["공통 가중치 대안 최솟값(%)"], row["공통 가중치 대안 최댓값(%)"]], y=[row.시도, row.시도], mode="lines", line={"color": "#aab9ba", "width": 5}, showlegend=False, hoverinfo="skip"))
    for name, label, symbol, color in [("관측 처리비율 R_r(%)", "실제 구성 처리비율 R", "circle", COLORS[0]),
                                        ("전국 고정가중 표준화 S_r(%)", "전국 구성 표준화 처리비율 S", "diamond", COLORS[1])]:
        fig.add_trace(go.Scatter(x=regional[name], y=regional.시도, mode="markers", name=label,
                                marker={"symbol": symbol, "color": color, "size": 9}, hovertemplate="%{y}: %{x:.2f}%<extra>%{fullData.name}</extra>"))
    fig.update_layout(xaxis_title="처리비율 (%) · 회색선: 공통 가중치 3안의 범위", height=720, xaxis_range=[0, 100])
    figs["regional_scores"] = fig
    part = tables["composition_example"].melt(id_vars=["가상 국가", "자료구분"], var_name="집계 기준", value_name="비율(%)")
    figs["composition_example"] = _grouped(part, "가상 국가", "집계 기준", "비율(%)")
    row = tables["partial_bounds"].iloc[0]
    fig = go.Figure(go.Bar(x=[row.S_upper_pct - row.S_lower_pct], base=[row.S_lower_pct], y=["가상 A"], orientation="h", marker_color=COLORS[2], name="미확인 재질의 가능 범위", hovertemplate="40–90% (식별구간)<extra></extra>"))
    fig.update_layout(xaxis_range=[0, 100], xaxis_title="표준화 최종 회수율 S (%)", height=330)
    figs["partial_bounds"] = fig
    labels = ["발생 100", "수거 70", "미수거 30", "공정투입 56", "선별잔재 14", "최종 재생물질 42", "공정손실 14"]
    figs["mass_flow"] = go.Figure(go.Sankey(node={"label": labels, "pad": 26, "thickness": 20, "color": [COLORS[0], COLORS[0], "#b6bfc1", COLORS[1], "#b6bfc1", COLORS[2], "#b6bfc1"]},
        link={"source": [0, 0, 1, 1, 3, 3], "target": [2, 1, 4, 3, 6, 5], "value": [30, 70, 14, 56, 14, 42], "color": "rgba(75,111,120,.25)"}))
    evidence = tables["jrc_plastics"]
    fig = go.Figure(go.Bar(x=["적정 수거 전체<br>(재활용 전용 수거 아님)","폐기 후 재활용률<br>(EOL)"], y=evidence.rate_pct, marker_color=COLORS[:2],
                          text=evidence.rate_pct, texttemplate="%{text:.1f}%", textposition="outside"))
    fig.update_layout(yaxis_range=[0,100], yaxis_title="보고된 모형 비율 (%)")
    figs["jrc_plastics"] = fig
    summary = tables["weight_pair_counts"]
    fig = go.Figure()
    for column, color in [("비교 방향이 유지되는 쌍", COLORS[2]), ("비교 방향이 달라질 수 있는 쌍", COLORS[1])]:
        fig.add_bar(x=summary["가중치 범위"], y=summary[column], name=column, marker_color=color,
                    text=summary[column], textposition="inside")
    fig.update_layout(barmode="stack", yaxis_title="비교한 지역쌍 수 (총 136쌍)", yaxis_range=[0,150])
    figs["weight_pair_counts"] = fig
    matrix, order = _pair_matrix(tables)
    fig = go.Figure(go.Heatmap(z=matrix, x=order, y=order, zmin=-1,zmax=1,
        colorscale=[[0,"#c17b36"],[.2499,"#c17b36"],[.25,"#edf0ee"],[.7499,"#edf0ee"],[.75,"#367c68"],[1,"#367c68"]],
        colorbar={"tickvals":[-1,0,1],"ticktext":["열 지역 우세","가중치에 따라 역전","행 지역 우세"]},
        hovertemplate="행 %{y} / 열 %{x}<br>1=행 우세, 0=역전 가능, -1=열 우세<extra></extra>"))
    fig.update_layout(height=720, yaxis_autorange="reversed", xaxis_title="비교 대상 지역(열)", yaxis_title="평가 지역(행)")
    figs["weight_pair_matrix"] = fig
    return dict(sorted(figs.items(), key=lambda item: int(CHARTS[item[0]][0])))


def _pair_matrix(tables):
    order = tables["regional_scores"].sort_values("전국 고정가중 표준화 S_r(%)", ascending=False).시도.tolist()
    matrix = pd.DataFrame(np.nan,index=order,columns=order)
    for row in tables["weight_pair_matrix"].itertuples(index=False):
        value = 1 if row.comparison in ["a_strict","a_no_reversal"] else -1 if row.comparison in ["b_strict","b_no_reversal"] else 0
        matrix.loc[row.entity_a,row.entity_b] = value
        matrix.loc[row.entity_b,row.entity_a] = -value
    return matrix.to_numpy(), order


CHARTS = {
    "swiss_stages": ("01", "수거율과 재생자원 산출률은 다르다", "문헌 사례 · 스위스 2012 · Haupt 외(2017)", "종이 15%p, 판지 8%p의 단계 차이다. 연구의 동일 경계 두 쌍을 사용했으며 한국 수율로 적용하지 않는다.", ["HAUPT17"]),
    "nea_scope": ("02", "폐기물 범위를 바꾸면 같은 해의 비율도 바뀐다", "실제 공식통계 · 싱가포르 NEA 2024 · t/년", "원표 전체 물량에서 제외 범주의 분자와 분모를 함께 뺐다. 제외 후 비율은 범위 민감도이며 municipal waste 공식률이 아니다.", ["NEA24"]),
    "kosis_energy": ("03", "에너지회수와 물질회수를 구분해야 한다", "실제 행정통계 · 한국 KOSIS 2024 · 대응 4재질", "같은 발생량을 분모로 사용한다. 두 값 모두 처리경로 집계이며 최종 재생원료 산출률은 아니다.", ["KOSIS24"]),
    "regional_scores": ("04", "재질 구성을 고정하면 지역 비교가 달라진다", "실제 행정통계 · 한국 17개 시도 · 대응 4재질", "점은 실제 구성 R과 전국 고정 구성 S다. 회색선은 전국비중·시도비중 평균·균등의 3개 공통 가중치 대안 범위로, 신뢰구간이 아니다. 기존 처리비율을 최종 회수율과 구분한다.", ["KOSIS24", "OECD08"]),
    "composition_example": ("05", "모든 재질에서 더 잘 회수해도 총률은 낮을 수 있다", "가상 설명 · 실제 국가 관측 아님", "B의 두 재질 회수율이 A보다 각각 10%p 높다. 구성에 따른 원래 순서는 A 74% > B 36%지만 50:50 표준화에서는 A 50% < B 60%다.", []),
    "time_methods": ("06", "연도 집계 방식도 같은 질문을 답하지 않는다", "가상 설명 · EPR 의무율 산식 재현 아님", "연간 발생량 200·100·50t과 회수율 30·50·70%를 사용했다. 3년 질량합산과 연간 비율 평균은 다른 추정 대상이다. 한국 법정 실적 가중치는 의무율 산정연도 t−2부터 과거 3년을 참조한다.", ["KR_EPR"]),
    "partial_bounds": ("07", "미확인 산출량은 점수가 아닌 구간으로 남긴다", "가상 설명 · 물리적 식별구간 · 통계적 신뢰구간 아님", "관측된 종이 회수율 80%와 미확인 플라스틱에 각각 가중치 0.5를 적용하면 S는 40–90%다. 미확인 출력을 0으로 대입한 관측값이나 구간 중간값을 발표하지 않는다.", []),
    "mass_flow": ("08", "물질흐름에서 비교할 단계를 고정한다", "가상 설명 · 동일 코호트·무수 대상물질 기준 · 단위 t", "70% 수거 × 80% 선별 후 투입 × 75% 공정수율 = 42% 최종 회수다. 각 항은 같은 물질흐름이어야 하며 이것은 회계 항등식이다.", ["GRAEDEL11", "HAUPT17"]),
    "jrc_plastics": ("09", "적정 수거와 최종 재활용을 구분한 최신 기관 연구", "기관 모형 · EU-27 플라스틱 2022 · JRC 2025 발표", "적정 수거 86%는 재활용용 수거만을 뜻하지 않으며 처분 경로를 포함한다. EOL 재활용률 19.6%와 감산·나눗셈하여 공정손실이나 수율을 추정하지 않는다. 한국 관측 H/S나 municipal 4재질과 범위가 다르다.", ["JRC25"]),
    "weight_pair_counts": ("10", "가중치 범위 전체에서 비교 방향이 유지되는가", "실제 처리통계 · KOSIS 2024 · 17개 시도 136쌍", "3개 공통 가중치의 혼합, 재질별 최소·최대 경계 전체, 비음수 가중치 전체를 각각 검증했다. 집합이 넓어질수록 보장되는 비교가 줄 수 있다. 가중치 범위는 선언한 시나리오이며 확률·신뢰구간·사회적 합의가 아니다.", ["KOSIS24","SETH18"]),
    "weight_pair_matrix": ("11", "단일 순위 대신 가중치 전체에 견디는 비교를 표시한다", "실제 처리통계 · 모든 비음수 공통 가중치의 보수적 검증", "초록은 행 지역의 비율이 모든 공통 가중치에서 열 지역보다 높게 유지됨을, 주황은 반대 방향을 뜻한다. 회색은 가중치에 따라 우열이 바뀔 수 있다. 대각선은 자기비교를 제외한다. 최종 회수율·정책 인과효과의 우열은 아니다.", ["KOSIS24","SETH18"]),
}


def save_static(tables, directory):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    families = {font.name for font in font_manager.fontManager.ttflist}
    font = next((name for name in ["Malgun Gothic", "Noto Sans CJK KR", "NanumGothic", "AppleGothic"] if name in families), "DejaVu Sans")
    plt.rcParams.update({"font.family": font, "axes.unicode_minus": False, "svg.fonttype": "path", "font.size": 11})

    def save(fig, name):
        for ext in ["png", "svg"]:
            fig.savefig(directory / f"{name}.{ext}", dpi=180, bbox_inches="tight", facecolor="#faf9f6")
        plt.close(fig)

    for name, (_, title, label, note, _) in CHARTS.items():
        fig, ax = plt.subplots(figsize=(11.5, 8.5 if name in ["regional_scores","weight_pair_matrix"] else 5.5))
        fig.patch.set_facecolor("#faf9f6")
        ax.set_facecolor("#faf9f6")
        if name in ["swiss_stages", "composition_example"]:
            if name == "swiss_stages":
                wide = tables[name].pivot(index="재질", columns="단계", values="비율(%)").reindex(index=["종이", "판지"], columns=["수거 단계", "재생자원 산출 단계"])
            else:
                wide = tables[name].set_index("가상 국가").drop(columns="자료구분")
            x = np.arange(len(wide))
            for j, column in enumerate(wide.columns):
                bars = ax.bar(x + (j - .5) * .32, wide[column], width=.32, color=COLORS[j], label=column)
                ax.bar_label(bars, fmt="%.1f%%", padding=4)
            ax.set_xticks(x, wide.index)
            ax.set_ylim(0, 105)
            ax.set_ylabel("비율 (%)")
            ax.legend(loc="upper right")
        elif name == "regional_scores":
            part = tables[name].sort_values("전국 고정가중 표준화 S_r(%)")
            y = np.arange(len(part))
            ax.hlines(y, part["공통 가중치 대안 최솟값(%)"], part["공통 가중치 대안 최댓값(%)"], color="#b8c1c1", linewidth=5, label="공통 가중치 3안 범위")
            ax.scatter(part["관측 처리비율 R_r(%)"], y, color=COLORS[0], s=25, label="실제 구성 처리비율 R", zorder=3)
            ax.scatter(part["전국 고정가중 표준화 S_r(%)"], y, color=COLORS[1], s=35, marker="D", label="전국 구성 표준화 처리비율 S", zorder=4)
            ax.set_yticks(y, part.시도)
            ax.set_xlim(0, 100)
            ax.set_xlabel("처리비율 (%) · 대안 범위는 신뢰구간이 아님")
            ax.legend(loc="lower right", fontsize=9)
        elif name == "partial_bounds":
            row = tables[name].iloc[0]
            ax.barh(["가상 A"], [row.S_upper_pct - row.S_lower_pct], left=[row.S_lower_pct], color=COLORS[2], height=.3)
            ax.text(65, 0, "40–90%\n최종 산출 미확인에 따른 식별구간", ha="center", va="center", color="white", fontweight="bold")
            ax.set_xlim(0, 100)
            ax.set_xlabel("표준화 최종 회수율 S (%)")
        elif name == "weight_pair_matrix":
            from matplotlib.colors import ListedColormap, BoundaryNorm
            matrix, order = _pair_matrix(tables)
            cmap = ListedColormap([COLORS[1],"#edf0ee",COLORS[2]])
            ax.imshow(matrix,cmap=cmap,norm=BoundaryNorm([-1.5,-.5,.5,1.5],cmap.N))
            ax.set_xticks(range(len(order)),order,rotation=90)
            ax.set_yticks(range(len(order)),order)
            ax.set_xlabel("열 지역 · 초록=행 우세, 주황=열 우세, 회색=역전 가능")
        elif name == "weight_pair_counts":
            part=tables[name]
            bottom=np.zeros(len(part))
            for column,color in [("비교 방향이 유지되는 쌍",COLORS[2]),("비교 방향이 달라질 수 있는 쌍",COLORS[1])]:
                bars=ax.bar(part["가중치 범위"],part[column],bottom=bottom,color=color,label=column)
                ax.bar_label(bars,label_type="center",color="white",fmt="%.0f")
                bottom+=part[column].to_numpy()
            ax.set_ylim(0,160); ax.set_ylabel("지역쌍 수 (총 136쌍)"); ax.legend(loc="upper right",fontsize=9)
        elif name == "jrc_plastics":
            part=tables[name]
            bars=ax.bar(["적정 수거 전체\n(재활용 전용 수거 아님)","폐기 후 재활용률\n(EOL)"],part.rate_pct,color=COLORS[:2])
            ax.bar_label(bars,fmt="%.1f%%",padding=5)
            ax.set_ylim(0,105); ax.set_ylabel("기관 모형의 보고 비율 (%)")
        elif name == "mass_flow":
            values = [100, 70, 56, 42]
            bars = ax.bar(["발생", "수거", "공정투입", "최종 재생물질"], values, color=[COLORS[0], COLORS[0], COLORS[1], COLORS[2]])
            ax.bar_label(bars, fmt="%.0f t", padding=5)
            ax.set_ylim(0, 115)
            ax.set_ylabel("동일 코호트의 대상물질량 (t)")
        else:
            category, value = {"nea_scope": ("범위", "보고량으로 계산한 비율(%)"), "kosis_energy": ("기준", "처리비율(%)"), "time_methods": ("집계 방법", "비율(%)")}[name]
            part = tables[name]
            bars = ax.bar(part[category], part[value], color=COLORS[:len(part)])
            ax.bar_label(bars, fmt="%.2f%%", padding=5)
            ax.set_ylim(0, 100)
            ax.set_ylabel("비율 (%)")
        ax.set_title(title + "\n" + label, loc="left", pad=20, fontweight="bold")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="x" if name in ["regional_scores", "partial_bounds"] else "y", alpha=.15)
        ax.set_axisbelow(True)
        fig.text(.02, .012, "RPL 연구안 v1.1 · 수치 원본은 같은 이름의 CSV · 출처와 해석 범위는 보고서 참조", fontsize=9, color="#596b6c")
        fig.tight_layout(rect=[0, .04, 1, 1])
        save(fig, name)

    fig, ax = plt.subplots(figsize=(13, 6.3))
    ax.set_xlim(-.7, 5.8)
    ax.set_ylim(-1.5, 2.1)
    ax.axis("off")
    pos = {"정책": (0, 0), "수거": (1, 0), "선별": (2, 0), "최종 산출": (3, 0),
           "1차 원료 대체": (4, 0), "환경영향": (5, 0), "지역·시장 여건": (1.5, 1.3),
           "정의·측정점": (3, -1), "보고 재활용률": (4.5, -1)}
    nodes = {}
    for label, (x, y) in pos.items():
        color = COLORS[0] if y == 0 else (COLORS[1] if y > 0 else COLORS[2])
        node = FancyBboxPatch((x - .4, y - .2), .8, .4, boxstyle="round,pad=.025", facecolor=color, edgecolor="none", zorder=3)
        nodes[label] = node
        ax.add_patch(node)
        ax.text(x, y, label, color="white", ha="center", va="center", fontsize=10, zorder=4)
    for _, row in tables["causal_edges"].iterrows():
        start, end = pos[row["출발"]], pos[row["도착"]]
        ax.add_patch(FancyArrowPatch(start, end, patchA=nodes[row["출발"]], patchB=nodes[row["도착"]],
            arrowstyle="-|>", mutation_scale=14, color="#657e83", shrinkA=3, shrinkB=3,
            connectionstyle="arc3,rad=.06", zorder=2,
            linestyle="--" if row["출발"] in ["지역·시장 여건", "정의·측정점"] else "-"))
    ax.set_title("정책효과와 통계 정의의 효과를 구분한다\n인과 가설 · 화살표는 추정된 효과가 아님", loc="left", fontweight="bold")
    fig.text(.03, .03, "재질 구성 표준화는 지역·시장 여건의 교란을 제거하지 않는다. 원료 대체와 환경영향은 추가 자료·반사실이 필요하다.", fontsize=10)
    save(fig, "causal_dag")


def run(root=ROOT, output_root=None):
    root = Path(root).resolve()
    output = Path(output_root or root / "outputs").resolve()
    report, figures, tables_dir = [output / path / "recycling_indicator" for path in ["reports", "figures", "tables"]]
    for directory in [report, figures, tables_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    tables, inputs = build_tables(root)
    for name, frame in tables.items():
        frame.to_csv(tables_dir / f"{name}.csv", index=False, encoding="utf-8-sig")
    sources_path = root / "data/indicator_sources.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    followup_sources_path=root/"data/indicator_followup_sources.json"
    sources.extend(json.loads(followup_sources_path.read_text(encoding="utf-8")))
    if len({source["source_id"] for source in sources})!=len(sources):
        raise ValueError("Duplicate research source IDs")
    (report/"sources.json").write_text(json.dumps(sources,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    pd.DataFrame(sources).to_csv(tables_dir / "sources.csv", index=False, encoding="utf-8-sig")
    figs = build_figures(tables)
    save_static(tables, figures)
    sections = []
    for index, (name, fig) in enumerate(figs.items()):
        number, title, label, note, source_ids = CHARTS[name]
        fig.update_layout(template="plotly_white", font={"family": "Malgun Gothic, sans-serif"},
                          title={"text": title + "<br><sup>" + label + "</sup>", "font": {"size": 17}},
                          paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", margin={"t": 115, "b": 80},
                          legend={"orientation": "h", "y": 1.08}, meta={"evidence_type": label, "source_ids": source_ids})
        fig.write_json(figures / f"{name}.json")
        fig.write_html(figures / f"{name}.html", include_plotlyjs=True)
        fragment = pio.to_html(fig, full_html=False, include_plotlyjs=True if index == 0 else False,
                               div_id="indicator-" + name, config={"displaylogo": False, "responsive": True})
        references = " · ".join(f'<a href="#source-{sid}">{html.escape(sid)}</a>' for sid in source_ids)
        prefix = "../../figures/recycling_indicator/" + name
        sections.append(f'<section id="{name}" class="chart"><p class="eyebrow">FIGURE {number} · {html.escape(label)}</p><h2>{html.escape(title)}</h2>{fragment}<p>{html.escape(note)} {references}</p><details><summary>수치·단위·정적 그림 다운로드</summary><p><a href="../../tables/recycling_indicator/{name}.csv">CSV</a> · <a href="{prefix}.png">PNG</a> · <a href="{prefix}.svg">SVG</a></p>{tables[name].to_html(index=False, na_rep="미확인", float_format=lambda v: f"{v:,.3f}")}</details></section>')
    cards = []
    for source in sources:
        e = lambda key: html.escape(str(source[key]))
        cards.append(f'<article id="source-{e("source_id")}" class="source"><p class="eyebrow">{e("source_id")} · {e("type")}</p><h3><a href="{html.escape(source["url"], quote=True)}">{e("title")}</a></h3><p>{e("authors")} · {e("year")}</p><p>{e("contribution")}</p><p class="muted">확인: {e("verified")} · {e("locator")}<br>한계: {e("limitation")}</p></article>')
    # Keep the full study and evidence alongside the HTML for review and sharing.
    for src, name in [(root / "docs/recycling_indicator_study.md", "study.md"),
                      (root / "docs/indicator_data_contract.md", "data_contract.md"),
                      (root/"docs/indicator_weight_robustness_2026-11-19.md","weight_robustness.md"),
                      (root/"docs/indicator_followup_evidence_2026-11-19.md","followup_evidence.md")]:
        content = src.read_text(encoding="utf-8")
        if src.suffix == ".md":
            def local_link(match):
                target = match.group(1)
                if ":" in target or target.startswith("#"):
                    return match.group(0)
                source_target = (src.parent / target).resolve()
                renamed = {root / "docs/recycling_indicator_study.md": "study.md", root / "docs/indicator_data_contract.md": "data_contract.md",
                           root / "docs/indicator_weight_robustness_2026-11-19.md": "weight_robustness.md",
                           root / "docs/indicator_followup_evidence_2026-11-19.md": "followup_evidence.md"}
                relative = renamed.get(source_target, os.path.relpath(source_target, report).replace("\\", "/"))
                return "](" + relative + ")"
            content = re.sub(r"\]\(([^)]+)\)", local_link, content)
        (report / name).write_text(content, encoding="utf-8")
    regional = tables["regional_scores"]
    energy_gap = float(tables["kosis_energy"]["처리비율(%)"].iloc[0] - tables["kosis_energy"]["처리비율(%)"].iloc[1])
    scope_values = tables["nea_scope"]["보고량으로 계산한 비율(%)"].tolist()
    robustness=tables["weight_pair_counts"].set_index("domain")
    summary = {"source_items": len(sources), "figure_count": len(figs)+1, "regional_count": len(regional),
               "kosis_energy_gap_pp": energy_gap, "nea_scope_rates_pct": scope_values,
               "maximum_composition_gap_pp": float(regional["구성 차이 R-S(%p)"].abs().max()),
               "final_output_country_comparison": "not_identified", "policy_causal_effect": "not_estimated",
               "robust_nonreversal_pairs": {name:int(robustness.loc[name,"nonreversal_pairs"]) for name in DOMAIN_LABELS},
               "pair_count":int(robustness.pair_count.iloc[0]), "latest_evidence_check":"2026-11-19"}
    generated = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    template = Template((root / "docs/indicator_report_template.html").read_text(encoding="utf-8"))
    page = template.substitute(title=html.escape(TITLE), generated=generated, source_count=len(sources),
        energy_gap=f"{energy_gap:.2f}", scope_start=f"{scope_values[0]:.2f}", scope_end=f"{scope_values[-1]:.2f}",
        composition_gap=f'{summary["maximum_composition_gap_pp"]:.2f}',
        hull_pairs=summary["robust_nonreversal_pairs"]["reference_hull"],
        box_pairs=summary["robust_nonreversal_pairs"]["reference_box"],
        simplex_pairs=summary["robust_nonreversal_pairs"]["all_simplex"],
        causal_image="data:image/svg+xml;base64," + base64.b64encode((figures / "causal_dag.svg").read_bytes()).decode("ascii"),
        charts="\n".join(sections), sources="\n".join(cards))
    (report / "index.html").write_text(page, encoding="utf-8")
    code = [root / path for path in ["src/analysis/recycling_indicator.py", "src/analysis/recycling_indicator_report.py",
        "src/analysis/standardization.py", "scripts/run_recycling_indicator.py", "docs/recycling_indicator_study.md",
        "docs/indicator_data_contract.md", "docs/indicator_report_template.html", "data/indicator_sources.json",
        "data/indicator_followup_sources.json","docs/indicator_followup_evidence_2026-11-19.md",
        "docs/indicator_weight_robustness_2026-11-19.md","src/analysis/weight_robustness.py","src/analysis/indicator_robustness.py"]]
    files = [{"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in [*inputs, *code]]
    artifacts = {path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                 for directory in [report, figures, tables_dir] for path in sorted(directory.iterdir())
                 if path.is_file() and path.name != "manifest.json"}
    manifest = {"title": TITLE, "status": "complete", "generated_at": generated, "summary": summary,
                "source_files": files, "artifacts": artifacts,
                "reproduction_command": r".\.venv\Scripts\python scripts/run_recycling_indicator.py",
                "caveat": "최종 H/S 국가값은 미식별. 실측 처리비율과 문헌·가상 사례를 구분한다."}
    (report / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest

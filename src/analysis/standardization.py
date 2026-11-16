"""2024년 시도별 관측 처리비율의 전국 고정 재질구성 표준화."""
import numpy as np
import pandas as pd

MATERIALS = ("폐지류", "폐합성수지류", "폐금속류", "폐유리류")
REGIONS = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주")


def compute_standardization(frame: pd.DataFrame, *, expected_regions=None, region_label="시도"):
    required = {"geography", "material", "reference_year", "generated_t", "material_recycling_t"}
    if not required.issubset(frame.columns):
        raise ValueError("지역·재질·연도·발생량·물질재활용 처리량 열이 필요합니다.")
    area_values=list(REGIONS if expected_regions is None else expected_regions)
    if len(area_values)<1 or len(set(area_values))!=len(area_values) or "전국" in area_values:
        raise ValueError("비교 지역 목록은 중복 없이 전국을 제외해야 합니다.")
    data = frame.loc[frame.geography.isin(["전국", *area_values])].copy()
    data["reference_year"] = pd.to_numeric(data.reference_year, errors="raise")
    for column in ("generated_t", "material_recycling_t"):
        data[column] = pd.to_numeric(data[column], errors="raise")
    if data.empty or not data.reference_year.eq(2024).all():
        raise ValueError("2024년 관측 자료만 허용합니다.")
    if data.duplicated(["geography", "reference_year", "material"]).any():
        raise ValueError("지역·연도·재질 중복 관측이 있습니다.")
    if set(data.material) != set(MATERIALS):
        raise ValueError("대응 4재질 외의 행 또는 누락 재질이 있습니다.")
    counts = data.groupby("geography").material.nunique()
    if not counts.eq(4).all() or set(counts.index) != {"전국", *area_values}:
        raise ValueError("전국 및 분석 지역 각각의 4재질 관측이 필요합니다.")
    values = data[["generated_t", "material_recycling_t"]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (data.generated_t <= 0).any() or (data.material_recycling_t < 0).any() or (data.material_recycling_t > data.generated_t).any():
        raise ValueError("유한한 양의 발생량과 0≤물질재활용 처리량≤발생량을 확인하세요.")

    regions = data.loc[data.geography != "전국"].copy()
    regions["p_rm"] = regions.material_recycling_t / regions.generated_t
    totals = regions.groupby("geography").generated_t.transform("sum")
    regions["a_rm"] = regions.generated_t / totals
    national = data.loc[data.geography == "전국"].set_index("material").generated_t.reindex(MATERIALS)
    w_national = national / national.sum()
    if not np.isclose(w_national.sum(), 1.0):
        raise ValueError("전국 기준 재질 가중치 합이 1이 아닙니다.")
    mean_shares = regions.pivot(index="geography", columns="material", values="a_rm").reindex(index=area_values, columns=MATERIALS).mean()
    weight_sets = {
        "전국 발생량 비중(기준)": w_national,
        f"{len(area_values)}개 {region_label} 재질비중 평균": mean_shares,
        "4재질 균등": pd.Series(1 / len(MATERIALS), index=MATERIALS),
    }
    long = regions.set_index(["geography", "material"])
    rows, sensitivity_rows, contribution_rows = [], [], []
    for region in area_values:
        part = long.loc[region].reindex(MATERIALS)
        p = part.p_rm
        a = part.a_rm
        observed = float((a * p).sum() * 100)
        base = float((w_national * p).sum() * 100)
        region_weights = dict(weight_sets)
        # Leave-one-region-out national composition: the excluded region cannot define its own reference.
        national_minus = data.loc[(data.geography == "전국")].set_index("material").generated_t.reindex(MATERIALS) - part.generated_t.reindex(MATERIALS)
        if (national_minus < 0).any() or national_minus.sum() <= 0:
            raise ValueError("지역 제외 전국 기준 가중치가 음수 또는 0입니다.")
        region_weights[f"해당 {region_label} 제외 전국 비중"] = national_minus / national_minus.sum()
        scores = {}
        for label, weights in region_weights.items():
            score = float((weights.reindex(MATERIALS) * p).sum() * 100)
            scores[label] = score
            sensitivity_rows.append({region_label: region, "가중치 기준": label, "표준화 처리비율(%)": score,
                                     "순위(높은 값=1)": np.nan})
        rows.append({region_label: region, "4재질 발생량(t/년)": float(part.generated_t.sum()),
                     "4재질 물질재활용 처리량(t/년)": float(part.material_recycling_t.sum()),
                     "관측 처리비율 R_r(%)": observed, "전국 고정가중 표준화 S_r(%)": base,
                     "구성 차이 R-S(%p)": observed - base,
                     **{f"기준재질비중_{m}": float(w_national[m]) for m in MATERIALS},
                     **{f"처리비율_{m}(%)": float(p[m] * 100) for m in MATERIALS}})
        for material in MATERIALS:
            contribution_rows.append({region_label: region, "재질": material,
                                      "발생량 구성비 a_rm(%)": float(a[material] * 100),
                                      "관측 처리비율 p_rm(%)": float(p[material] * 100),
                                      "전국 기준 비중 w_m(%)": float(w_national[material] * 100),
                                      "R-S 기여도(%p)": float(100 * (a[material] - w_national[material]) * p[material])})
    scores_frame = pd.DataFrame(rows)
    sensitivity = pd.DataFrame(sensitivity_rows)
    sensitivity["순위(높은 값=1)"] = sensitivity.groupby("가중치 기준")["표준화 처리비율(%)"].rank(ascending=False, method="min").astype(int)
    contribution = pd.DataFrame(contribution_rows)
    # Algebraic identity and attribution additivity are explicit QA gates.
    if not np.allclose(scores_frame["관측 처리비율 R_r(%)"] - scores_frame["전국 고정가중 표준화 S_r(%)"],
                        contribution.groupby(region_label)["R-S 기여도(%p)"].sum().reindex(area_values), atol=1e-10):
        raise AssertionError("R-S 재질 기여도 합이 지표 차이와 일치하지 않습니다.")
    score_wide = sensitivity.pivot(index=region_label, columns="가중치 기준", values="표준화 처리비율(%)")
    rank_wide = sensitivity.pivot(index=region_label, columns="가중치 기준", values="순위(높은 값=1)")
    base_label = "전국 발생량 비중(기준)"
    sensitivity_summary = []
    for label in score_wide.columns:
        corr = None if rank_wide[base_label].nunique()<2 or rank_wide[label].nunique()<2 else float(rank_wide[base_label].corr(rank_wide[label], method="spearman"))
        sensitivity_summary.append({"가중치 기준": label,
                                    "기준과의 Spearman 순위상관": corr,
                                    f"기준 대비 순위 3단계 초과 {region_label} 수": int((rank_wide[base_label] - rank_wide[label]).abs().gt(3).sum()),
                                    "지역별 점수 변화 최대폭(%p)": float((score_wide[label] - score_wide[base_label]).abs().max()),
                                    "표준화 점수 최대-최소(%p)": float((score_wide[label].max() - score_wide[label].min()))})
    order={name:i for i,name in enumerate(area_values)}
    scores_frame = scores_frame.sort_values(region_label, key=lambda s: s.map(order)).reset_index(drop=True)
    return scores_frame, contribution, sensitivity, pd.DataFrame(sensitivity_summary), w_national.rename("전국 발생량 가중치").rename_axis("재질").reset_index()

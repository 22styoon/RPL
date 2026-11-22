"""KOSIS treatment-rate application of common-weight robustness analysis."""
import numpy as np
import pandas as pd
from .standardization import MATERIALS, REGIONS
from .weight_robustness import compare_rate_bounds

DOMAIN_LABELS = {"reference_hull": "3안의 모든 혼합", "reference_box": "3안의 최소·최대 범위", "all_simplex": "비음수 가중치 전체"}


def build_robustness_tables(frame):
    national = frame.loc[frame.geography.eq("전국")].set_index("material").reindex(MATERIALS)
    region = frame.loc[frame.geography.isin(REGIONS)].copy()
    if not frame.reference_year.eq(2024).all():
        raise ValueError("2024 KOSIS reference profile required")
    if region.duplicated(["geography", "material"]).any():
        raise ValueError("Duplicate regional material profile")
    region["rate"] = region.material_recycling_t / region.generated_t
    region["share"] = region.generated_t / region.groupby("geography").generated_t.transform("sum")
    profiles = region.pivot(index="geography", columns="material", values="rate").reindex(index=REGIONS, columns=MATERIALS)
    shares = region.pivot(index="geography", columns="material", values="share").reindex(index=REGIONS, columns=MATERIALS)
    reference = national.generated_t / national.generated_t.sum()
    vertices = pd.DataFrame({"전국 발생비중": reference, "시도 재질비중 평균": shares.mean(), "4재질 균등": 1/4}, index=MATERIALS).T
    if not np.isfinite(vertices.to_numpy()).all():
        raise ValueError("Missing reference composition")
    domains = {
        "reference_hull": {"kind": "hull", "vertices": vertices.T.to_dict()},
        "reference_box": {"kind": "box", "lower": vertices.min().to_dict(), "upper": vertices.max().to_dict()},
        "all_simplex": {"kind": "box", "lower": dict.fromkeys(MATERIALS, 0), "upper": dict.fromkeys(MATERIALS, 1)},
    }
    pairs, bounds, witnesses, summary = compare_rate_bounds(profiles, profiles, domains,
        reference_weights=reference.to_dict(), reference_year=2024,
        measurement_label="KOSIS 대응 4재질 물질재활용 처리비율; 최종 산출률 아님")
    for table in [pairs, bounds, witnesses, summary]:
        table["가중치 범위"] = table.domain.map(DOMAIN_LABELS)
    summary["비교 방향이 유지되는 쌍"] = summary.nonreversal_pairs
    summary["비교 방향이 달라질 수 있는 쌍"] = summary.indeterminate_pairs
    vertices_long = vertices.rename_axis("기준 가중치").reset_index().melt(id_vars="기준 가중치", var_name="재질", value_name="가중치")
    weight_bounds = []
    for domain_id, domain in domains.items():
        for m in MATERIALS:
            weight_bounds.append({"domain": domain_id, "가중치 범위": DOMAIN_LABELS[domain_id], "kind": domain["kind"], "재질": m,
                "하한": float(domain.get("lower", vertices.min().to_dict())[m]),
                "상한": float(domain.get("upper", vertices.max().to_dict())[m]),
                "주의": "hull은 꼭짓점들의 혼합만 허용; 좌표 상하한만으로 정의하지 않음" if domain_id == "reference_hull" else "각 재질 상하한과 합계 1을 함께 적용"})
    return {"weight_pair_counts": summary, "weight_comparisons": pairs, "weight_rank_outer": bounds,
        "weight_witnesses": witnesses, "weight_reference_vertices": vertices_long,
        "weight_domain_bounds": pd.DataFrame(weight_bounds),
        "weight_pair_matrix": pairs.loc[pairs.domain.eq("all_simplex")].copy()}

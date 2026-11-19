import hashlib
import json
import re
import numpy as np
import pandas as pd
import pytest
from src.analysis.recycling_indicator_report import build_tables, run
from src.model import ROOT


def test_actual_scope_and_treatment_results_follow_saved_mass_not_reported_integer_rates():
    tables, _ = build_tables()
    scope = tables["nea_scope"]
    assert scope["발생량(t)"].tolist() == [6658000, 5950000, 5838000]
    assert scope["보고 재활용량(t)"].tolist() == [3326000, 2620000, 2510000]
    assert scope["보고량으로 계산한 비율(%)"].iloc[0] == pytest.approx(100 * 3326 / 6658)
    assert scope["보고량으로 계산한 비율(%)"].iloc[0] != 50
    energy = tables["kosis_energy"]
    assert energy["발생량(t)"].iloc[0] == pytest.approx(7269015.7)
    gap = np.diff(energy["처리비율(%)"])[0] * -1
    assert gap == pytest.approx(100 * (3819793.9 - 3129884.1) / 7269015.7)
    assert len(tables["regional_scores"]) == 17
    assert tables["regional_scores"]["자료구분"].str.contains("최종 산출률 아님").all()


def test_constructed_cases_and_partial_identification_remain_separate_from_observations():
    tables, _ = build_tables()
    sample = tables["composition_example"]
    assert sample["실제 구성 H(%)"].tolist() == pytest.approx([74, 36])
    assert sample["50:50 표준화 S(%)"].tolist() == pytest.approx([50, 60])
    assert sample["자료구분"].str.contains("가상").all()
    row = tables["partial_bounds"].iloc[0]
    assert pd.isna(row.S_pct)
    assert [row.S_lower_pct, row.S_upper_pct] == pytest.approx([40, 90])
    assert tables["time_methods"]["비율(%)"].tolist() == pytest.approx([70, 50, 100 * 145 / 350, 56])


def test_report_is_offline_hashed_and_explicit_about_evidence(tmp_path):
    manifest = run(output_root=tmp_path)
    assert manifest["summary"]["source_items"] == 25
    assert manifest["summary"]["figure_count"] == 12
    assert manifest["summary"]["latest_evidence_check"] == "2026-11-19"
    assert manifest["summary"]["robust_nonreversal_pairs"] == {"reference_hull":123,"reference_box":118,"all_simplex":83}
    assert manifest["summary"]["final_output_country_comparison"] == "not_identified"
    page = (tmp_path / "reports/recycling_indicator/index.html").read_text(encoding="utf-8")
    assert not re.search(r'<script[^>]+src=["\']https?://', page)
    assert 'data:image/svg+xml;base64,' in page
    assert "가상 설명" in page and "통계적 신뢰구간 아님" in page
    assert "t−2·t−3·t−4" in page
    assert "123 / 136쌍" in page and "118 / 136쌍" in page and "83 / 136쌍" in page
    assert "보수적 외곽 범위" in page and "FIGURE 12" in page
    assert (tmp_path / "reports/recycling_indicator/weight_robustness.md").exists()
    assert (tmp_path / "reports/recycling_indicator/followup_evidence.md").exists()
    for relative, expected in manifest["artifacts"].items():
        assert hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest() == expected
    assert len(list((tmp_path / "figures/recycling_indicator").glob("*.png"))) == 12
    assert len(list((tmp_path / "figures/recycling_indicator").glob("*.svg"))) == 12
    actual = pd.read_csv(tmp_path / "tables/recycling_indicator/nea_scope.csv")
    assert actual["발생량(t)"].iloc[0] == 6658000
    for name in ["composition_example", "partial_bounds"]:
        figure = json.loads((tmp_path / f"figures/recycling_indicator/{name}.json").read_text(encoding="utf-8"))
        assert "가상" in figure["layout"]["meta"]["evidence_type"]
    jrc_figure = json.loads((tmp_path / "figures/recycling_indicator/jrc_plastics.json").read_text(encoding="utf-8"))
    assert "기관 모형" in jrc_figure["layout"]["meta"]["evidence_type"]
    assert jrc_figure["layout"]["meta"]["source_ids"] == ["JRC25"]
    sources=json.loads((tmp_path/"reports/recycling_indicator/sources.json").read_text(encoding="utf-8"))
    assert {"JRC25","SETH18","EUROSTAT26"}.issubset({source["source_id"] for source in sources})


def test_actual_weight_domains_have_nested_guarantees_and_expected_pair_counts():
    tables, _ = build_tables()
    counts=tables["weight_pair_counts"].set_index("domain")
    assert counts.pair_count.tolist() == [136,136,136]
    assert counts.nonreversal_pairs.tolist() == [123,118,83]
    assert counts.indeterminate_pairs.tolist() == [13,18,53]
    pairs=tables["weight_comparisons"]
    assert len(pairs)==408 and pairs.rates_exact.all()
    key=["entity_a","entity_b"]
    guaranteed={domain:set(map(tuple,part.loc[part.comparison.ne("indeterminate"),key].to_numpy()))
                for domain,part in pairs.groupby("domain")}
    assert guaranteed["all_simplex"] <= guaranteed["reference_box"] <= guaranteed["reference_hull"]
    lower=pairs.pivot(index=key,columns="domain",values="gap_lower_pp")
    upper=pairs.pivot(index=key,columns="domain",values="gap_upper_pp")
    assert (lower.all_simplex <= lower.reference_box+1e-10).all()
    assert (lower.reference_box <= lower.reference_hull+1e-10).all()
    assert (upper.all_simplex >= upper.reference_box-1e-10).all()
    assert (upper.reference_box >= upper.reference_hull-1e-10).all()


def test_extreme_weight_witnesses_reproduce_actual_gaps_and_obey_declared_domains():
    tables, _ = build_tables()
    witness=tables["weight_witnesses"]
    keys=["domain","entity_a","entity_b"]
    grouped=witness.groupby([*keys,"endpoint"])
    assert np.allclose(grouped.weight.sum(),1)
    contributions=grouped.gap_contribution_pp.sum().unstack("endpoint")
    gaps=tables["weight_comparisons"].set_index(keys)
    assert np.allclose(contributions.lower.reindex(gaps.index),gaps.gap_lower_pp)
    assert np.allclose(contributions.upper.reindex(gaps.index),gaps.gap_upper_pp)
    bounds=tables["weight_domain_bounds"].rename(columns={"재질":"material"})
    checked=witness.merge(bounds[["domain","material","하한","상한"]],on=["domain","material"],validate="many_to_one")
    assert checked.weight.ge(checked["하한"]-1e-10).all()
    assert checked.weight.le(checked["상한"]+1e-10).all()
    # For the full simplex the extreme gap is independently the minimum/maximum
    # material-rate difference, calculated directly from the source quantities.
    raw=pd.read_csv(ROOT/"data/processed/kosis_materials_2024.csv")
    raw=raw.loc[raw.geography.ne("전국")].copy()
    raw["p"]=raw.material_recycling_t/raw.generated_t
    profiles=raw.pivot(index="geography",columns="material",values="p")
    for row in tables["weight_pair_matrix"].itertuples():
        difference=100*(profiles.loc[row.entity_a]-profiles.loc[row.entity_b])
        assert row.gap_lower_pp == pytest.approx(difference.min())
        assert row.gap_upper_pp == pytest.approx(difference.max())


def test_baseline_observed_rank_is_within_conservative_outer_bounds_and_jrc_is_model_data():
    tables, _ = build_tables()
    outer=tables["weight_rank_outer"]
    for _,part in outer.groupby("domain"):
        rank=part.reference_score_pct.rank(ascending=False,method="min")
        assert rank.ge(part.rank_lower_outer).all()
        assert rank.le(part.rank_upper_outer).all()
    jrc=tables["jrc_plastics"]
    assert jrc.rate_pct.tolist()==[86,19.6]
    assert jrc.reference_year.eq(2022).all() and jrc.publication_year.eq(2025).all()
    assert jrc.measurement_type.str.contains("모형").all()
    assert "처분 경로 포함" in jrc.indicator.iloc[0]

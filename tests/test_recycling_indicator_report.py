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
    assert manifest["summary"]["source_items"] == 22
    assert manifest["summary"]["final_output_country_comparison"] == "not_identified"
    page = (tmp_path / "reports/recycling_indicator/index.html").read_text(encoding="utf-8")
    assert not re.search(r'<script[^>]+src=["\']https?://', page)
    assert 'data:image/svg+xml;base64,' in page
    assert "가상 설명" in page and "통계적 신뢰구간 아님" in page
    assert "t−2·t−3·t−4" in page
    for relative, expected in manifest["artifacts"].items():
        assert hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest() == expected
    assert len(list((tmp_path / "figures/recycling_indicator").glob("*.png"))) == 9
    assert len(list((tmp_path / "figures/recycling_indicator").glob("*.svg"))) == 9
    actual = pd.read_csv(tmp_path / "tables/recycling_indicator/nea_scope.csv")
    assert actual["발생량(t)"].iloc[0] == 6658000
    for name in ["composition_example", "partial_bounds"]:
        figure = json.loads((tmp_path / f"figures/recycling_indicator/{name}.json").read_text(encoding="utf-8"))
        assert "가상" in figure["layout"]["meta"]["evidence_type"]

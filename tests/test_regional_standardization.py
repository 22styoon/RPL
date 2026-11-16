import numpy as np
import pandas as pd
import pytest

from src.analysis.standardization import MATERIALS, REGIONS, compute_standardization
from src.analysis.regional_inference import run_composition_diagnostics
from src.analysis.regional_indicator_report import run as run_regional_report
from src.regional_data.geocodes import normalize_mois


def synthetic_frame():
    rows=[]
    rates={m:r for m,r in zip(MATERIALS,(.2,.4,.6,.8))}
    for i,region in enumerate(REGIONS):
        amounts={m:float((i+1)*(j+2+((i+j)%5)*.3)*100) for j,m in enumerate(MATERIALS)}
        for material in MATERIALS:
            generated=amounts[material]
            rows.append({"geography":region,"material":material,"reference_year":2024,
                         "generated_t":generated,"material_recycling_t":generated*rates[material]})
    for material in MATERIALS:
        generated=sum(r["generated_t"] for r in rows if r["material"]==material)
        recycled=sum(r["material_recycling_t"] for r in rows if r["material"]==material)
        rows.append({"geography":"전국","material":material,"reference_year":2024,
                     "generated_t":generated,"material_recycling_t":recycled})
    return pd.DataFrame(rows)


def test_same_material_rates_produce_invariant_standardized_scores():
    scores, *_ = compute_standardization(synthetic_frame())
    assert np.ptp(scores["전국 고정가중 표준화 S_r(%)"].to_numpy()) < 1e-10
    assert scores["관측 처리비율 R_r(%)"].nunique() > 1


def test_contribution_identity_weights_and_bounds():
    scores, contributions, sensitivity, summary, weights = compute_standardization(synthetic_frame())
    total=contributions.groupby("시도")["R-S 기여도(%p)"].sum().reindex(scores["시도"]).to_numpy()
    assert np.allclose(total,scores["구성 차이 R-S(%p)"].to_numpy())
    assert np.isclose(weights["전국 발생량 가중치"].sum(),1)
    assert sensitivity["표준화 처리비율(%)"].between(0,100).all()
    assert len(summary)==4


def test_materialwise_monotonicity():
    frame=synthetic_frame()
    before=compute_standardization(frame)[0].set_index("시도")["전국 고정가중 표준화 S_r(%)"]
    idx=frame.index[(frame.geography==REGIONS[0])&(frame.material==MATERIALS[0])][0]
    frame.loc[idx,"material_recycling_t"] += frame.loc[idx,"generated_t"]*.05
    after=compute_standardization(frame)[0].set_index("시도")["전국 고정가중 표준화 S_r(%)"]
    assert after.loc[REGIONS[0]] >= before.loc[REGIONS[0]]


@pytest.mark.parametrize("change",["year","missing","above_generated","negative"])
def test_invalid_measurements_are_rejected(change):
    frame=synthetic_frame()
    idx=frame.index[0]
    if change=="year":frame.loc[idx,"reference_year"]=2023
    elif change=="missing":frame.loc[idx,"generated_t"]=np.nan
    elif change=="above_generated":frame.loc[idx,"material_recycling_t"]=frame.loc[idx,"generated_t"]+1
    else:frame.loc[idx,"material_recycling_t"]=-1
    with pytest.raises(ValueError):compute_standardization(frame)


def test_actual_kosis_produces_17_sido_rows_and_diagnostics():
    frame=pd.read_csv("data/processed/kosis_materials_2024.csv")
    scores,contributions,sensitivity,_,_=compute_standardization(frame)
    assert len(scores)==17 and len(contributions)==68 and len(sensitivity)==68
    result=run_composition_diagnostics(frame)
    assert result["status"]=="computed" and result["n"]==17
    assert set(result["tests"]["공분산"])=={"일반 OLS","HC0 강건","HC3 강건"}
    assert len(result["leave_one_out"])==17
    assert len(result["diagnostics"])==17


def test_mois_special_city_unit_maps_to_workbook_name_explicitly():
    state={"records":[{"admmCd":"3611000000","ctpvNm":"세종특별자치시","sggNm":"",
                       "statsYm":"202412","totNmprCnt":"390685","hhCnt":"163432"}],
           "retrieved_at":"2026-11-16T10:40:56+09:00"}
    row=normalize_mois(state).iloc[0]
    assert row.sigungu_name=="세종시"
    assert row.code_verified


def test_offline_regional_report_has_hashed_tables_and_figures(tmp_path):
    from src.model import ROOT
    manifest=run_regional_report(root=ROOT,output_root=tmp_path)
    assert manifest["status"]=="complete"
    assert manifest["summary"]["sido_rows"]==17
    assert manifest["summary"]["verified_join_rows"]==0
    assert (tmp_path/"reports/regional_indicator/index.html").exists()
    assert (tmp_path/"reports/regional_indicator/report.md").exists()
    assert "tables/regional_indicator/scores.csv" in manifest["artifacts"]
    assert "figures/regional_indicator/regional_scores.png" in manifest["artifacts"]

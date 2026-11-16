from copy import deepcopy
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from src.model import ROOT
from src.analysis.trend import yearly_trend
from src.analysis.composition import material_composition
from src.analysis.regional import regional_profiles
from src.analysis.costs import guro_flows,guro_budgets
from src.analysis.quality import missingness
from src.analysis.household_time import summarize_diary,FIELDS
from src.analysis.pipeline import build_analyses,plotly_figure
from src.comparability import assess_comparability,convert_mass

def test_observed_trend_preserves_official_values_and_does_not_forecast():
    source=pd.read_csv(ROOT/"data/processed/kosis_public_waste.csv")
    result=yearly_trend(source)
    assert result.table["연도"].tolist()==[2020,2021,2022,2023,2024]
    assert result.table["발생량(t/년)"].tolist()==[17303386,16751315,16754168,16685207,17045141]
    assert pd.isna(result.table["전년 대비 증감률(%)"].iloc[0])
    assert result.table["전년 대비 증감률(%)"].iloc[-1]==pytest.approx((17045141/16685207-1)*100)
    assert result.extra["cagr_pct"]==pytest.approx(((17045141/17303386)**.25-1)*100)

def test_year_gap_is_not_mislabeled_as_annual_growth():
    frame=pd.read_csv(ROOT/"data/processed/kosis_public_waste.csv").iloc[[0,2,4]]
    result=yearly_trend(frame)
    assert result.table["전년 대비 증감률(%)"].isna().all()

@pytest.mark.parametrize("column",["unit","geography","waste_scope"])
def test_trend_refuses_inconsistent_scope(column):
    frame=pd.read_csv(ROOT/"data/processed/kosis_public_waste.csv")
    frame.loc[0,column]="different"
    with pytest.raises(ValueError):
        yearly_trend(frame)

def test_duplicate_years_are_rejected():
    frame=pd.read_csv(ROOT/"data/processed/kosis_public_waste.csv")
    with pytest.raises(ValueError):
        yearly_trend(pd.concat([frame,frame.iloc[[0]]]))

def test_composition_is_disjoint_and_keeps_final_yield_out_of_observations():
    frame=pd.read_csv(ROOT/"data/processed/kosis_materials_2024.csv")
    result=material_composition(frame)
    assert len(result.table)==20
    assert result.table["처리경로"].nunique()==5
    assert result.table.loc[result.table["처리경로"]=="물질재활용","처리량(t/년)"].sum()==pytest.approx(3129884.1)
    assert result.table.groupby("품목")["처리경로 비중(%)"].sum().to_numpy()==pytest.approx([100]*4,abs=.001)
    assert "가정" not in result.table.columns

def test_changed_balance_is_rejected_instead_of_rescaled():
    frame=pd.read_csv(ROOT/"data/processed/kosis_materials_2024.csv")
    frame.loc[0,"generated_t"]+=100
    with pytest.raises(ValueError):
        material_composition(frame)

def test_regional_profile_excludes_national_total_and_uses_weighted_ratio():
    frame=pd.read_csv(ROOT/"data/processed/kosis_materials_2024.csv")
    result=regional_profiles(frame)
    assert len(result.table)==17
    assert "전국" not in set(result.table["시도"])
    row=result.table.loc[result.table["시도"]=="서울"].iloc[0]
    raw=frame.loc[frame.geography=="서울"]
    assert row["물질재활용 처리비율(%)"]==pytest.approx(raw.material_recycling_t.sum()/raw.generated_t.sum()*100)

def test_regions_from_multiple_years_cannot_be_summed():
    frame=pd.read_csv(ROOT/"data/processed/kosis_materials_2024.csv")
    copy=frame.copy();copy.reference_year=2023
    with pytest.raises(ValueError):
        regional_profiles(pd.concat([frame,copy]))

def test_guro_observed_flow_and_budget_proxy():
    source=pd.read_csv(ROOT/"data/processed/guro_recycling.csv")
    flows=guro_flows(source);budget=guro_budgets(source)
    assert flows.table["선별 회수율(%)"].iloc[-1]==pytest.approx(7733/13195*100)
    assert budget.table["합계 예산(원)"].iloc[-1]==11529161000
    assert budget.table["처리대상량당 예산 참고비율(원/t)"].iloc[-1]==pytest.approx(11529161000/13195)
    assert budget.measurement_type=="공개 예산 대리값"

def test_missingness_retains_unknown_fields_without_zero_imputation():
    result=missingness(pd.DataFrame({"known":[0,None,""]}),["known","absent"])
    assert result["미입력 행수"].tolist()==[2,3]
    assert result["미입력 비율(%)"].tolist()==pytest.approx([200/3,100])

@pytest.mark.parametrize("unit,value,expected",[("US short ton",1,.90718474),("kg",1000,1),("1000 tonnes",2,2000)])
def test_explicit_mass_conversion(unit,value,expected):
    assert convert_mass(value,unit)==pytest.approx(expected)

def comparable():
    return dict(country="KR",year=2024,waste_scope="same",material="same",process_stage="same",
        numerator_definition="same",denominator_definition="same",mass_unit="t",geography_level="national")

def test_different_countries_can_be_compared_when_definitions_match():
    left=comparable();right=dict(left,country="DE")
    assert assess_comparability(left,right)["compatible"]

@pytest.mark.parametrize("field",["year","waste_scope","material","process_stage","numerator_definition","denominator_definition","mass_unit","geography_level"])
def test_incompatible_or_unknown_definition_blocks_comparison(field):
    left=comparable();right=deepcopy(left);right[field]=None
    assert not assess_comparability(left,right)["compatible"]
    right[field]="different"
    assert not assess_comparability(left,right)["compatible"]

def test_foreign_values_cannot_automatically_enter_korean_model():
    left=comparable();right=dict(left,country="NO")
    result=assess_comparability(left,right,purpose="korean_model_input")
    assert "foreign_value_is_not_korean_observation" in result["reasons"]

def test_monetary_comparisons_require_price_year_and_currency():
    assert not assess_comparability(comparable(),comparable(),monetary=True)["compatible"]

def diary(n=20):
    return pd.DataFrame([dict(household_id=str(i),week=1,cleaning_minutes=i,sorting_minutes=1,storage_minutes=2,walking_minutes=3) for i in range(n)])

def test_repeated_diaries_do_not_inflate_household_sample():
    frame=diary(20);week2=frame.copy();week2.week=2
    result=summarize_diary(pd.concat([frame,week2]))
    single=summarize_diary(frame)
    assert result["households"]==20
    assert result["mean"]==single["mean"]
    assert result["ci95"]==single["ci95"]

def test_incomplete_task_time_is_not_filled_with_zero():
    frame=diary(2);frame.loc[0,"cleaning_minutes"]=None
    result=summarize_diary(frame)
    assert result["households"]==1
    assert result["excluded_rows"]==1
    assert result["ci95"] is None

def test_bootstrap_is_seeded_and_small_sample_ci_is_omitted():
    assert summarize_diary(diary(20))["ci95"]==summarize_diary(diary(20))["ci95"]
    assert summarize_diary(diary(19))["ci95"] is None

def test_duplicate_household_week_is_rejected():
    frame=diary(2)
    with pytest.raises(ValueError):
        summarize_diary(pd.concat([frame,frame.iloc[[0]]]))

@pytest.mark.parametrize("value",[-1,float("inf")])
def test_invalid_time_is_rejected(value):
    frame=diary(2);frame["sorting_minutes"]=frame["sorting_minutes"].astype(float);frame.loc[0,"sorting_minutes"]=value
    with pytest.raises(ValueError):
        summarize_diary(frame)

def test_plot_reproduces_table_values_without_new_estimates():
    frame=pd.read_csv(ROOT/"data/processed/kosis_public_waste.csv")
    analysis=yearly_trend(frame);fig=plotly_figure(analysis)
    np.testing.assert_array_equal(fig.data[0].y,analysis.table["발생량(t/년)"].to_numpy())
    assert fig.layout.meta["measurement_type"]=="관측 행정통계"

def test_every_result_has_question_source_code_and_limitations():
    results,_,_=build_analyses()
    assert len(results)>=5
    assert len({r.question for r in results})==len(results)
    for result in results:
        assert result.sources and result.question and result.code_source and result.limitations
        assert not result.table.empty and not result.plot.empty

def test_changed_raw_bytes_are_rejected_before_foreign_analysis(tmp_path):
    import shutil
    directory=tmp_path/"data/processed"
    directory.mkdir(parents=True)
    for name in ("kosis_public_waste.csv","kosis_materials_2024.csv","guro_recycling.csv"):
        shutil.copyfile(ROOT/"data/processed"/name,directory/name)
    international=directory/"international/eurostat"
    international.mkdir(parents=True)
    (international/"records.csv").write_text("value\n1\n",encoding="utf-8")
    raw=tmp_path/"data/raw/test.json"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"changed")
    (international/"manifest.json").write_text(json.dumps({"raw_file":"data/raw/test.json","sha256":"0"*64}),encoding="utf-8")
    with pytest.raises(ValueError,match="SHA-256"):
        build_analyses(tmp_path)

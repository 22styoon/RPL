"""Synthetic locality fixtures verify candidate linkage without policy upgrading."""
import pandas as pd
import pytest

from src.regional_data.policy_geography import GEOGRAPHY_FIELDS, link_ordinance_geography


CANDIDATE_STATUS = "ordinance_history_only_operational_policy_unverified"


@pytest.fixture
def codes():
    return pd.DataFrame([
        ("서울", "강남구", "11", "1168000000"),
        ("서울", "중구", "11", "1114000000"),
        ("부산", "중구", "26", "2611000000"),
        ("경기", "수원시", "41", "4111000000"),
        ("경기", "수원시 장안구", "41", "4111100000"),
        ("전북", "전주시", "52", "5211000000"),
    ], columns=["sido_name", "sigungu_name", "sido_code", "sigungu_code"])


@pytest.fixture
def waste_units():
    # Waste observations have one row per material, not one row per admin code.
    return pd.DataFrame({"sigungu_code": [code for code in [
        "1168000000", "1114000000", "2611000000", "4111000000", "5211000000"
    ] for _ in range(4)]})


def candidates(*localities):
    return pd.DataFrame([
        {"locality": locality, "ordinance_id": f"law-{index}",
         "ordinance_serial": f"version-{index}", "candidate_status": CANDIDATE_STATUS,
         "effective_date": "2024-01-01", "policy_name": "분리수거 조례 후보"}
        for index, locality in enumerate(localities)
    ], columns=["locality", "ordinance_id", "ordinance_serial", "candidate_status", "effective_date", "policy_name"])


def test_exact_province_and_county_names_disambiguate_same_county_label(codes, waste_units):
    linked, summary = link_ordinance_geography(
        candidates("서울특별시 중구", "부산광역시 중구"), codes, waste_units)
    assert linked.matched_sigungu_code_2024.tolist() == ["1114000000", "2611000000"]
    assert linked.geography_match_status.eq("matched_2024_waste_statistical_unit").all()
    assert linked.geography_source_locator.str.contains("statsYm=202412", regex=False).all()
    assert summary["matched_waste_statistical_unit_rows"] == 2


def test_whitespace_is_normalized_but_partial_or_similar_names_are_not_guessed(codes, waste_units):
    linked, _ = link_ordinance_geography(candidates(
        " 서울특별시 \t 중구 ", "중구", "서울특별시 강남", "서울특별시교육청", "서울특별시 없는구"
    ), codes, waste_units)
    assert linked.geography_match_status.iloc[0] == "matched_2024_waste_statistical_unit"
    assert linked.geography_match_status.iloc[1:].eq("locality_unmatched_2024_admin_roster").all()
    assert linked.matched_sigungu_code_2024.iloc[1:].eq("").all()


def test_multiple_codes_with_same_exact_locality_remain_unmatched(codes, waste_units):
    conflicting = pd.concat([codes, pd.DataFrame([{
        "sido_name": "서울", "sigungu_name": "중구", "sido_code": "11", "sigungu_code": "1199000000"
    }])], ignore_index=True)
    linked, summary = link_ordinance_geography(candidates("서울특별시 중구"), conflicting, waste_units)
    assert linked.geography_match_status.iloc[0] == "locality_unmatched_2024_admin_roster"
    assert linked.matched_sigungu_code_2024.iloc[0] == ""
    assert summary["unmatched_locality_rows"] == 1


def test_province_only_is_not_expanded_into_county_outcome_exposure(codes, waste_units):
    linked, summary = link_ordinance_geography(candidates("서울특별시", "경기도"), codes, waste_units)
    assert linked.geography_match_status.eq("sido_only_no_sigungu_outcome_join").all()
    assert linked.matched_sido_code_2024.tolist() == ["11", "41"]
    assert linked.matched_sigungu_code_2024.eq("").all()
    assert not linked.waste_statistical_unit_2024.any()
    assert summary["sido_only_rows"] == 2
    assert summary["matched_waste_statistical_unit_rows"] == 0


def test_admin_subdistrict_is_not_upgraded_to_parent_waste_statistical_unit(codes, waste_units):
    linked, summary = link_ordinance_geography(
        candidates("경기도 수원시 장안구", "경기도 수원시"), codes, waste_units)
    assert linked.matched_sigungu_code_2024.tolist() == ["4111100000", "4111000000"]
    assert linked.geography_match_status.tolist() == [
        "matched_2024_admin_code_not_waste_unit", "matched_2024_waste_statistical_unit"]
    assert summary["matched_admin_code_non_statistical_unit_rows"] == 1
    assert summary["matched_waste_statistical_unit_rows"] == 1


def test_declared_province_aliases_use_2024_codes_without_historical_code_guessing(codes, waste_units):
    linked, _ = link_ordinance_geography(
        candidates("전라북도 전주시", "전북특별자치도 전주시"), codes, waste_units)
    assert linked.matched_sido_name_2024.tolist() == ["전북", "전북"]
    assert linked.matched_sigungu_code_2024.tolist() == ["5211000000", "5211000000"]


def test_linkage_preserves_legal_versions_and_never_verifies_operational_policy(codes, waste_units):
    source = candidates("서울특별시 중구", "서울특별시 중구", "서울특별시")
    source.loc[1, "ordinance_id"] = source.loc[0, "ordinance_id"]
    before = source.copy(deep=True)
    linked, summary = link_ordinance_geography(source, codes, waste_units)
    pd.testing.assert_frame_equal(source, before)
    pd.testing.assert_frame_equal(linked[source.columns], source)
    assert len(linked) == 3
    assert summary["unique_ordinance_ids"] == 2
    assert linked.candidate_status.eq(CANDIDATE_STATUS).all()
    assert "evidence_status" not in linked
    assert summary["operational_policy_verified_rows"] == 0
    assert summary["verified_outcome_join_rows"] == 0


def test_missing_locality_is_reported_as_missing_not_an_outcome_join(codes, waste_units):
    linked, summary = link_ordinance_geography(candidates("", "  "), codes, waste_units)
    assert linked.geography_match_status.eq("locality_missing").all()
    assert not linked.waste_statistical_unit_2024.any()
    assert summary["match_status_counts"] == {"locality_missing": 2}
    assert summary["verified_outcome_join_rows"] == 0


def test_empty_candidate_search_returns_headed_empty_crosswalk_and_zero_summary(codes, waste_units):
    empty = candidates()
    linked, summary = link_ordinance_geography(empty, codes, waste_units)
    assert linked.empty
    assert linked.columns.tolist() == [*empty.columns, *GEOGRAPHY_FIELDS]
    for key in ["ordinance_version_rows", "unique_ordinance_ids", "unique_locality_labels",
                "matched_waste_statistical_unit_rows", "matched_admin_code_non_statistical_unit_rows",
                "sido_only_rows", "unmatched_locality_rows", "operational_policy_verified_rows",
                "verified_outcome_join_rows"]:
        assert summary[key] == 0
    assert summary["match_status_counts"] == {}


@pytest.mark.parametrize("input_name", ["codes", "waste"])
@pytest.mark.parametrize("field,expected,wrong", [
    ("code_reference_month", "202412", "202512"),
    ("reference_month", "202412", "202401"),
    ("reference_year", "2024", "2025"),
])
def test_explicit_mixed_geographic_periods_are_rejected(codes, waste_units, input_name, field, expected, wrong):
    frame = codes if input_name == "codes" else waste_units
    frame[field] = expected
    frame.loc[frame.index[-1], field] = wrong
    with pytest.raises(ValueError, match=field):
        link_ordinance_geography(candidates("서울특별시 중구"), codes, waste_units)


@pytest.mark.parametrize("field,value", [
    ("code_reference_month", "202311"), ("reference_month", "202501"),
    ("reference_year", "2023"), ("code_reference_month", ""),
])
def test_uniform_wrong_or_blank_period_is_not_relabeled_as_december_2024(codes, waste_units, field, value):
    codes[field] = value
    with pytest.raises(ValueError, match=field):
        link_ordinance_geography(candidates("서울특별시 중구"), codes, waste_units)


def test_explicit_consistent_periods_match_legacy_inputs_without_mutation(codes, waste_units):
    before, _ = link_ordinance_geography(candidates("서울특별시 중구"), codes, waste_units)
    codes = codes.assign(code_reference_month="202412", reference_month="202412", reference_year=2024)
    waste_units = waste_units.assign(code_reference_month="202412", reference_year=2024)
    codes_before, waste_before = codes.copy(deep=True), waste_units.copy(deep=True)
    after, summary = link_ordinance_geography(candidates("서울특별시 중구"), codes, waste_units)
    pd.testing.assert_frame_equal(before, after)
    pd.testing.assert_frame_equal(codes, codes_before)
    pd.testing.assert_frame_equal(waste_units, waste_before)
    assert summary["verified_outcome_join_rows"] == 0


def test_ambiguous_province_name_to_code_is_rejected_before_province_only_link(codes, waste_units):
    codes.loc[codes.sigungu_name.eq("중구") & codes.sido_name.eq("서울"), "sido_code"] = "12"
    with pytest.raises(ValueError, match="ambiguous province"):
        link_ordinance_geography(candidates("서울특별시"), codes, waste_units)


def test_province_code_with_conflicting_names_is_rejected(codes, waste_units):
    codes.loc[codes.sido_name.eq("부산"), "sido_code"] = "11"
    with pytest.raises(ValueError, match="ambiguous province"):
        link_ordinance_geography(candidates("서울특별시 중구"), codes, waste_units)


def test_same_county_code_with_conflicting_identity_is_rejected(codes, waste_units):
    codes.loc[codes.sigungu_name.eq("강남구"), "sigungu_code"] = "1114000000"
    with pytest.raises(ValueError, match="conflicting identity"):
        link_ordinance_geography(candidates("서울특별시 중구"), codes, waste_units)


def test_repeated_material_rows_cannot_disagree_about_county_identity(codes, waste_units):
    names = dict(zip(codes.sigungu_code, codes.sigungu_name))
    waste_units["sigungu_name"] = waste_units.sigungu_code.map(names)
    waste_units.loc[0, "sigungu_name"] = "다른구"
    with pytest.raises(ValueError, match="conflicting identity"):
        link_ordinance_geography(candidates("서울특별시 강남구"), codes, waste_units)


def test_shared_code_must_have_same_name_in_waste_and_admin_inputs(codes, waste_units):
    names = dict(zip(codes.sigungu_code, codes.sigungu_name))
    waste_units["sigungu_name"] = waste_units.sigungu_code.map(names)
    waste_units.loc[waste_units.sigungu_code.eq("1114000000"), "sigungu_name"] = "이름변경구"
    with pytest.raises(ValueError, match="MOIS and waste inputs disagree"):
        link_ordinance_geography(candidates("서울특별시 중구"), codes, waste_units)


def test_identical_admin_records_are_not_ambiguous(codes, waste_units):
    repeated = pd.concat([codes, codes.loc[codes.sigungu_code.eq("1114000000")]], ignore_index=True)
    linked, summary = link_ordinance_geography(candidates("서울특별시 중구"), repeated, waste_units)
    assert linked.matched_sigungu_code_2024.tolist() == ["1114000000"]
    assert summary["matched_waste_statistical_unit_rows"] == 1
    assert summary["verified_outcome_join_rows"] == 0


def test_null_locality_is_missing_without_guessing_a_region(codes, waste_units):
    linked, _ = link_ordinance_geography(candidates(pd.NA, float("nan")), codes, waste_units)
    assert linked.geography_match_status.eq("locality_missing").all()
    assert linked.matched_sigungu_code_2024.eq("").all()

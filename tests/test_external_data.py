from copy import deepcopy
import pytest
from src.external_data.common import ExternalDataError,check_url
from src.external_data.eurostat import normalize
from src.external_data.nea import normalize_text
from src.external_data.epa import normalize_html
from src.external_data.uk_waste import normalize_rows

META=dict(source_id="synthetic",source_url="https://ec.europa.eu/test",retrieved_at="2026-11-16",license="synthetic fixture")

def cube():
    return {"class":"dataset","id":["wst_oper","unit","geo","time"],"size":[1,2,2,1],
        "dimension":{
            "wst_oper":{"category":{"index":{"GEN":0},"label":{"GEN":"Waste generated"}}},
            "unit":{"category":{"index":{"KG_HAB":1,"THS_T":0},"label":{}}},
            "geo":{"category":{"index":{"DE":1,"FR":0},"label":{"DE":"Germany","FR":"France"}}},
            "time":{"category":{"index":{"2024":0},"label":{}}}},
        "value":{"0":2,"2":400,"3":500},"status":{"3":"ep"}}

def test_jsonstat_sparse_cube_missingness_unit_and_index_order():
    records=normalize(cube(),META)
    assert len(records)==4
    assert records[0]["country"]=="FR" and records[0]["value"]==2000
    assert records[1]["country"]=="DE" and records[1]["value"] is None
    assert records[2]["value"]==400 and records[2]["unit"]=="KG_HAB"
    assert records[3]["measurement_type"]=="official_estimate"

def test_non_contiguous_jsonstat_index_is_rejected():
    obj=cube();obj["dimension"]["geo"]["category"]["index"]={"FR":3,"DE":4}
    with pytest.raises(ExternalDataError):
        normalize(obj,META)

def test_jsonstat_negative_and_boolean_values_are_rejected():
    for value in (-1,True,float("nan")):
        obj=cube();obj["value"]["0"]=value
        with pytest.raises(ExternalDataError):
            normalize(obj,META)

def test_nea_pdf_table_converts_thousands_without_claiming_final_yield():
    text="Waste Statistics and Recycling Rate 2024\nPlastics 918 43 5% 875\nOverall 6,658 3,326 50% 3,332\n"
    records=normalize_text(text,META)
    assert len(records)==6
    assert records[0]["value"]==918000
    assert records[0]["comparability_flag"]=="not_harmonized"
    assert "wood fuel" in records[0]["process_stage"]

def test_nea_unrecognized_table_fails_instead_of_creating_zero():
    with pytest.raises(ExternalDataError):
        normalize_text("Waste Statistics and Recycling Rate 2024\nunknown",META)

def test_epa_summary_keeps_raw_short_tons_and_explicit_conversion():
    text="<p>The total generation of municipal solid waste (MSW) in 2018 was 292.4 million tons. approximately 69 million tons were recycled and 25 million tons were composted.</p>"
    records=normalize_html(text,META)
    assert len(records)==3
    assert records[0]["raw_value"]==292400000
    assert records[0]["value"]==pytest.approx(292400000*.90718474)
    assert records[0]["year"]==2018
    assert records[0]["measurement_type"]=="official_estimate"

def test_epa_changed_schema_is_not_silently_accepted():
    with pytest.raises(ExternalDataError):
        normalize_html("no known table",META)

def test_uk_groups_permits_and_excludes_operator_names():
    headers=["Permit","Facility RPA","Facility Type","Tonnes Received","Operator"]
    rows=[[123.0,"East","Transfer",5,"PRIVATE"],[123,"East","Transfer",-1,"PRIVATE"],[None,"West","Confidential",2,"PRIVATE"]]
    records=normalize_rows(headers,rows,META)
    known=next(row for row in records if row["site_key"]=="123")
    assert known["received_t"]==4 and known["source_rows"]==2
    assert known["negative_adjustment_rows"]==1
    assert "PRIVATE" not in str(records)
    assert any(row["site_key"] is None for row in records)

def test_uk_missing_mass_does_not_become_zero():
    with pytest.raises(ExternalDataError):
        normalize_rows(["Permit","Facility RPA","Facility Type","Tonnes Received"],[[1,"East","Transfer",None]],META)

@pytest.mark.parametrize("url",["http://ec.europa.eu/test","https://attacker.invalid","https://ec.europa.eu/test?serviceKey=secret"])
def test_unregistered_or_credential_urls_are_rejected(url):
    with pytest.raises(ExternalDataError):
        check_url(url)

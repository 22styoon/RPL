"""2024년 월별 MOIS 시군구 코드와 통계 원표 단위의 일관성을 점검한다."""
from datetime import datetime
from pathlib import Path
from time import sleep
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
import hashlib
import json
import re
import pandas as pd

from src.model import ROOT
from .clients import MOIS_ENDPOINT, dump, load_mois_key
from .audit_evidence import make_input_binding,assess_boundary_audit

ROOT_CODES=("11","26","27","28","29","30","31","36","41","43","44","46","47","48","50","51","52")
ALIASES={
    "서울특별시":"서울","부산광역시":"부산","대구광역시":"대구","인천광역시":"인천",
    "광주광역시":"광주","대전광역시":"대전","울산광역시":"울산","세종특별자치시":"세종",
    "경기도":"경기","강원특별자치도":"강원","충청북도":"충북","충청남도":"충남",
    "전라북도":"전북","전북특별자치도":"전북","전라남도":"전남",
    "경상북도":"경북","경상남도":"경남","제주특별자치도":"제주",
}
QUARTERS=(("202401","202403"),("202404","202406"),("202407","202409"),("202410","202412"))


def _items(payload, page, months):
    response=payload.get("Response")
    if not isinstance(response,dict) or not isinstance(response.get("head"),dict):
        raise ValueError("MOIS_response_schema_changed")
    head=response["head"]
    code=str(head.get("resultCode"))
    if code=="3":return [],0
    if code!="0":raise ValueError("MOIS_"+str(head.get("resultMsg","service_error")))
    if int(head.get("pageNo",-1))!=page:raise ValueError("MOIS_page_mismatch")
    rows=response.get("items",{})
    rows=rows.get("item",[]) if isinstance(rows,dict) else rows
    if isinstance(rows,dict):rows=[rows]
    if not isinstance(rows,list):raise ValueError("MOIS_items_schema_changed")
    if any(not isinstance(row,dict) or str(row.get("statsYm")) not in months for row in rows):
        raise ValueError("MOIS_reference_month_mismatch")
    return rows,int(head.get("totalCount",0))


def _fetch_page(key, params, *, timeout):
    request=urlencode(dict(params,serviceKey=key))
    try:
        with urlopen(Request(MOIS_ENDPOINT+"?"+request,headers={"User-Agent":"RPL regional audit/1.0"}),timeout=timeout) as response:
            raw=response.read(5_000_001)
    except HTTPError as exc:
        raise ValueError("MOIS_HTTP_"+str(exc.code)) from None
    except URLError:
        raise ValueError("MOIS_network_error") from None
    if len(raw)>5_000_000 or key.encode() in raw or quote(key,safe="").encode() in raw:
        raise ValueError("MOIS_response_size_or_secret_echo")
    try:return raw,json.loads(raw)
    except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError("MOIS_invalid_json") from None


def _normalize(rows):
    normalized=[]
    for row in rows:
        code=str(row.get("admmCd") or "")
        month=str(row.get("statsYm") or "")
        if not re.fullmatch(r"\d{10}",code) or not re.fullmatch(r"2024(0[1-9]|1[0-2])",month):
            raise ValueError("MOIS_code_or_month_invalid")
        sido=ALIASES.get(str(row.get("ctpvNm") or ""))
        county=str(row.get("sggNm") or "").strip()
        if sido=="세종" and not county and code=="3611000000":county="세종시"
        if not sido or not county:raise ValueError("MOIS_area_name_unresolved")
        normalized.append({"reference_month":month,"sido_name":sido,"sigungu_name":county,
            "sigungu_code":code,"sido_code":code[:2],"population":row.get("totNmprCnt"),
            "households":row.get("hhCnt"),"source_id":"kr_admin_codes_2024",
            "source_url":"https://www.data.go.kr/data/15108065/openapi.do"})
    frame=pd.DataFrame(normalized)
    if frame.duplicated(["reference_month","sigungu_code"]).any():
        raise ValueError("MOIS_duplicate_month_code")
    return frame


def _is_nested_general_gu(row, by_code):
    code=row.get("sigungu_code") if isinstance(row,dict) else row.sigungu_code
    name=row.get("sigungu_name") if isinstance(row,dict) else row.sigungu_name
    parent_code=str(code)[:4]+"000000"
    parent=by_code.get(parent_code)
    return bool(parent and parent["sigungu_name"].endswith("시")
                and str(name).startswith(parent["sigungu_name"]+" ")
                and str(name).endswith("구"))


def run_boundary_audit(*,root=ROOT,timeout=30,delay_seconds=.2,max_pages_per_query=20,refresh=False):
    root=Path(root).resolve()
    raw_base=root/"data/raw/regional_2024/administrative_boundary_audit_2024"
    existing=[] if refresh or not raw_base.exists() else sorted(path for path in raw_base.iterdir() if path.is_dir())
    run_dir=existing[-1] if existing else None
    run_id=run_dir.name if run_dir else datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%dT%H%M%S_%f")
    raw_dir=raw_base/run_id/"pages"
    raw_dir.mkdir(parents=True,exist_ok=True)
    try:key=load_mois_key(root)
    except ValueError:key=None
    request_log=[];all_rows=[]
    for start,end in QUARTERS:
        months={f"2024{m:02d}" for m in range(int(start[-2:]),int(end[-2:])+1)}
        for root_code in ROOT_CODES:
            page=1;received=0;total=None;seen=set()
            while page<=max_pages_per_query:
                params={"admmCd":root_code+"00000000","srchFrYm":start,"srchToYm":end,
                    "lv":"2","regSeCd":"1","type":"JSON","numOfRows":100,"pageNo":page}
                path=raw_dir/f"{start}_{end}_{root_code}_{page}.json"
                reused=path.exists() and not refresh
                if reused:
                    raw=path.read_bytes()
                    if key and (key.encode() in raw or quote(key,safe="").encode() in raw):
                        raise ValueError("MOIS_response_secret_echo_in_cache")
                    try:payload=json.loads(raw)
                    except json.JSONDecodeError:raise ValueError("MOIS_cached_json_invalid") from None
                else:
                    if not key:raise ValueError("MOIS_API_KEY_required_for_missing_pages")
                    raw,payload=_fetch_page(key,params,timeout=timeout)
                rows,current_total=_items(payload,page,months)
                if total is not None and current_total!=total:raise ValueError("MOIS_pagination_total_changed")
                total=current_total
                digest=hashlib.sha256(raw).hexdigest()
                if not reused:path.write_bytes(raw)
                request_log.append({"parameters":params,"result":"success" if rows else "no_data",
                    "sha256":digest,"raw_file":path.relative_to(root).as_posix(),"cache_reused":reused})
                for row in rows:
                    identity=(str(row.get("statsYm")),str(row.get("admmCd")))
                    if identity in seen:raise ValueError("MOIS_duplicate_in_query_pages")
                    seen.add(identity);all_rows.append(row)
                received+=len(rows)
                if received>=total:break
                if not rows:raise ValueError("MOIS_premature_empty_page")
                page+=1
                if delay_seconds and not reused:sleep(delay_seconds)
            else:raise ValueError("MOIS_page_budget_exceeded")
            if received!=total:raise ValueError("MOIS_total_count_mismatch")
            if delay_seconds and not reused:sleep(delay_seconds)

    monthly=_normalize(all_rows)
    expected_months={f"2024{m:02d}" for m in range(1,13)}
    if set(monthly.reference_month)!=expected_months:raise ValueError("MOIS_month_coverage_incomplete")
    waste_path=root/"data/processed/regional_2024/sigungu_2024_materials_verified.csv"
    waste=pd.read_csv(waste_path,dtype={"sigungu_code":str})
    waste_units=waste[["sido_name","sigungu_name","sigungu_code"]].drop_duplicates()
    waste_codes=set(waste_units.sigungu_code.astype(str))
    if len(waste_units)!=229 or len(waste_codes)!=229:raise ValueError("waste_statistical_unit_count_changed")

    month_summary=[];issues=[];prev_by_code=None
    for month in sorted(expected_months):
        part=monthly.loc[monthly.reference_month==month].copy()
        by_code=part.set_index("sigungu_code").to_dict("index")
        current_codes=set(by_code)
        missing=waste_codes-current_codes
        for code in sorted(missing):issues.append({"reference_month":month,"sigungu_code":code,"issue":"statistical_code_missing"})
        name_mismatches=0
        expected=waste_units.set_index("sigungu_code")
        for code in sorted(waste_codes&current_codes):
            actual=by_code[code];target=expected.loc[code]
            if actual["sido_name"]!=target.sido_name or actual["sigungu_name"]!=target.sigungu_name:
                name_mismatches+=1
                issues.append({"reference_month":month,"sigungu_code":code,"issue":"statistical_name_or_parent_mismatch",
                    "expected_sido":target.sido_name,"actual_sido":actual["sido_name"],
                    "expected_name":target.sigungu_name,"actual_name":actual["sigungu_name"]})
        nested=[];unknown=[]
        for code in sorted(current_codes-waste_codes):
            row=part.loc[part.sigungu_code==code].iloc[0]
            if _is_nested_general_gu(row,by_code):nested.append(code)
            else:
                unknown.append(code);issues.append({"reference_month":month,"sigungu_code":code,"issue":"unmatched_admin_unit"})
        added=removed=name_changed=0
        if prev_by_code is not None:
            added=len(current_codes-set(prev_by_code));removed=len(set(prev_by_code)-current_codes)
            for code in sorted(current_codes&set(prev_by_code)):
                old=prev_by_code[code];new=by_code[code]
                if (old["sido_name"],old["sigungu_name"])!=(new["sido_name"],new["sigungu_name"]):
                    name_changed+=1
                    issues.append({"reference_month":month,"sigungu_code":code,"issue":"month_to_month_name_change",
                        "previous_sido":old["sido_name"],"actual_sido":new["sido_name"],
                        "previous_name":old["sigungu_name"],"actual_name":new["sigungu_name"]})
        month_summary.append({"reference_month":month,"admin_code_rows":len(part),"statistical_units":len(current_codes&waste_codes),
            "missing_statistical_codes":len(missing),"name_mismatches":name_mismatches,
            "nested_general_districts_excluded":len(nested),"unmatched_admin_units":len(unknown),
            "codes_added_vs_previous_month":added,"codes_removed_vs_previous_month":removed,
            "code_names_changed_vs_previous_month":name_changed})
        prev_by_code=by_code

    # The reporting unit is the city/county/district in the waste workbook. The 35
    # child general districts returned by MOIS are nested under 12 city totals.
    crosswalk=[]
    december=monthly.loc[monthly.reference_month=="202412"]
    december_map=december.set_index("sigungu_code").to_dict("index")
    expected=waste_units.set_index("sigungu_code")
    for code,row in december_map.items():
        if code in waste_codes:
            target=expected.loc[code]
            status="statistical_unit_code_and_name_match" if row["sido_name"]==target.sido_name and row["sigungu_name"]==target.sigungu_name else "statistical_unit_mismatch"
            crosswalk.append({"sigungu_code":code,"sido_name":row["sido_name"],"sigungu_name":row["sigungu_name"],"parent_code":"","unit_role":"statistical_unit","crosswalk_status":status})
        else:
            parent_code=code[:4]+"000000"
            nested=_is_nested_general_gu({"sigungu_code":code,**row},december_map)
            crosswalk.append({"sigungu_code":code,"sido_name":row["sido_name"],"sigungu_name":row["sigungu_name"],
                "parent_code":parent_code if nested else "","unit_role":"nested_general_district" if nested else "unmatched_admin_unit",
                "crosswalk_status":"excluded_child_of_statistical_city_total" if nested else "review_required"})

    summary=pd.DataFrame(month_summary)
    stable=(summary.missing_statistical_codes.eq(0).all() and summary.name_mismatches.eq(0).all()
        and summary.unmatched_admin_units.eq(0).all() and summary.codes_added_vs_previous_month.eq(0).all()
        and summary.codes_removed_vs_previous_month.eq(0).all() and summary.code_names_changed_vs_previous_month.eq(0).all())
    output=root/"data/processed/regional_2024"
    monthly.to_csv(output/"admin_codes_monthly_2024.csv",index=False,encoding="utf-8-sig")
    summary.to_csv(output/"boundary_audit_monthly_summary.csv",index=False,encoding="utf-8-sig")
    issue_columns=["reference_month","sigungu_code","issue","expected_sido","actual_sido",
                   "expected_name","actual_name","previous_sido","previous_name"]
    pd.DataFrame(issues,columns=issue_columns).to_csv(output/"boundary_audit_issues.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(crosswalk).to_csv(output/"boundary_audit_crosswalk_202412.csv",index=False,encoding="utf-8-sig")
    manifest={"source_id":"kr_admin_codes_2024","source_url":"https://www.data.go.kr/data/15108065/openapi.do",
        "endpoint":MOIS_ENDPOINT,"reference_year":2024,"retrieved_at":datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
        "status":"complete" if stable else "review_required","audit_scope":"monthly sigungu code/name roster and statistical-unit crosswalk; legal geometry is not assessed",
        "summary":{"month_count":len(summary),"monthly_code_rows_min":int(summary.admin_code_rows.min()),
            "monthly_code_rows_max":int(summary.admin_code_rows.max()),"statistical_unit_count":len(waste_codes),
            "monthly_missing_statistical_codes":int(summary.missing_statistical_codes.sum()),
            "monthly_name_mismatches":int(summary.name_mismatches.sum()),
            "nested_general_district_count_december":int((pd.DataFrame(crosswalk).unit_role=="nested_general_district").sum()),
            "unknown_unmatched_units":int(summary.unmatched_admin_units.sum()),
            "code_roster_changes":int(summary.codes_added_vs_previous_month.sum()+summary.codes_removed_vs_previous_month.sum()),
            "code_name_changes":int(summary.code_names_changed_vs_previous_month.sum()),
            "statistical_code_name_roster_stable":bool(stable)},
        "requests":request_log,"run_id":run_id,"raw_directory":raw_dir.relative_to(root).as_posix(),
        "input_binding":make_input_binding(waste_units,monthly,request_log),
        "artifacts":{"monthly":"data/processed/regional_2024/admin_codes_monthly_2024.csv",
            "monthly_summary":"data/processed/regional_2024/boundary_audit_monthly_summary.csv",
            "issues":"data/processed/regional_2024/boundary_audit_issues.csv",
            "crosswalk":"data/processed/regional_2024/boundary_audit_crosswalk_202412.csv"}}
    dump(output/"boundary_audit_manifest.json",manifest)

    # A completed refresh may overturn an earlier successful audit. Propagate
    # both outcomes so downstream reports cannot retain a stale success flag.
    data_path=output/"sigungu_2024_materials_verified.csv"
    frame=pd.read_csv(data_path,dtype={"sigungu_code":str})
    assessment=assess_boundary_audit(root,waste_frame=frame)
    bound=assessment["verified"]
    frame["boundary_input_binding_verified"]=bool(bound)
    frame["boundary_waste_roster_sha256"]=assessment.get("waste_roster_sha256","")
    frame["boundary_monthly_roster_sha256"]=assessment.get("monthly_roster_sha256","")
    if bound:
        nested_count=manifest["summary"]["nested_general_district_count_december"]
        frame["compatibility_status"]=(
            f"2024_monthly_MOIS_code_name_roster_stable; input_binding_verified; {nested_count}_nested_general_districts_excluded; geometry_not_assessed")
    else:
        frame["compatibility_status"]="2024_monthly_MOIS_code_name_roster_review_required; input_binding_unverified; geometry_not_assessed"
    frame.to_csv(data_path,index=False,encoding="utf-8-sig")
    prep_manifest=output/"manifest.json"
    if prep_manifest.exists():
        meta=json.loads(prep_manifest.read_text(encoding="utf-8"))
        meta["metadata_code_snapshot"]=(
            "2024_monthly_code_name_roster_stable_input_binding_verified_geometry_not_assessed" if bound
            else "current_bound_monthly_audit_not_verified")
        meta["administrative_boundary_audit_status"]=assessment["status"]
        meta["boundary_input_binding_verified"]=bool(bound)
        meta["boundary_waste_roster_sha256"]=assessment.get("waste_roster_sha256","")
        meta["boundary_monthly_roster_sha256"]=assessment.get("monthly_roster_sha256","")
        meta["boundary_audit_reasons"]=assessment.get("reasons",[])
        meta["boundary_audit_input_binding_version"]=assessment.get("input_binding_version")
        # The audit verifies geography. Policy/outcome joins need their own
        # preparation pass after the current evidence has been established.
        meta["policy_join_boundary_input_verified"]=False
        meta["administrative_boundary_audit_geometry_assessed"]=False
        dump(prep_manifest,meta)
    return manifest

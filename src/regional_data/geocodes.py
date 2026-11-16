import re
import pandas as pd
ALIASES={"서울특별시":"서울","부산광역시":"부산","대구광역시":"대구","인천광역시":"인천","광주광역시":"광주","대전광역시":"대전","울산광역시":"울산","세종특별자치시":"세종","경기도":"경기","강원특별자치도":"강원","충청북도":"충북","충청남도":"충남","전북특별자치도":"전북","전라남도":"전남","경상북도":"경북","경상남도":"경남","제주특별자치도":"제주"}
def normalize_mois(state):
    rows=[]
    for item in state.get("records",[]):
        code=str(item.get("admmCd") or "")
        if not re.fullmatch(r"\d{10}",code) or str(item.get("statsYm"))!="202412":
            raise ValueError("MOIS 행정코드·기준월 오류")
        province=ALIASES.get(item.get("ctpvNm"))
        county=str(item.get("sggNm") or "").strip()
        # MOIS reports Sejong at province level at lv=2; the waste workbook
        # labels this same sole administrative unit "세종시".
        if province=="세종" and not county and code=="3611000000":
            county="세종시"
        rows.append(dict(sido_name=province,sigungu_name=county,sido_code=code[:2],sigungu_code=code,
            reference_year=2024,code_reference_month="202412",
            population=int(item["totNmprCnt"]) if item.get("totNmprCnt") is not None else None,
            households=int(item["hhCnt"]) if item.get("hhCnt") is not None else None,
            source_id="kr_admin_codes_2024",source_url="https://www.data.go.kr/data/15108065/openapi.do",
            source_locator="selectAdmmPpltnHhStus lv=2; statsYm=202412; admmCd="+code,
            retrieved_at=state.get("retrieved_at"),code_verified=bool(province and county)))
    columns=["sido_name","sigungu_name","sido_code","sigungu_code","reference_year","code_reference_month","population","households","source_id","source_url","source_locator","retrieved_at","code_verified"]
    frame=pd.DataFrame(rows,columns=columns)
    if frame.duplicated(["sigungu_code","reference_year"]).any():
        raise ValueError("MOIS 중복 코드·연도")
    return frame

def attach_codes(observations,codes):
    valid=codes.loc[codes.code_verified.eq(True)].copy()
    if valid.duplicated(["sido_name","sigungu_name","reference_year"]).any():
        raise ValueError("서로 다른 행정코드가 동일한 지역명에 대응합니다.")
    fields=["sido_name","sigungu_name","reference_year","sido_code","sigungu_code","code_reference_month"]
    return observations.merge(valid[fields],on=["sido_name","sigungu_name","reference_year"],how="left",validate="many_to_one")

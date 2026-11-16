import pandas as pd
from .common import AnalysisResult,require_unique,require_numeric

def eurostat_generation(frame):
    data=frame.loc[(frame.metric=="GEN")&(frame.unit=="KG_HAB")].copy()
    require_unique(data,["country","year"])
    require_numeric(data,["value"],allow_missing=True)
    if data.year.nunique()!=1:
        raise ValueError("동일 연도 국가 통계만 비교합니다.")
    table=data[["country","geography","year","value","status_flag"]].rename(columns={"country":"국가 코드","geography":"국가","year":"연도","value":"1인당 발생량(kg/인·년)","status_flag":"원표 상태표시"})
    table["국가(원문)"]=table["국가"]
    table["국가"]=table["국가 코드"].map({'BE': '벨기에', 'BG': '불가리아', 'CZ': '체코', 'DK': '덴마크', 'DE': '독일', 'EE': '에스토니아', 'IE': '아일랜드', 'EL': '그리스', 'ES': '스페인', 'FR': '프랑스', 'HR': '크로아티아', 'IT': '이탈리아', 'CY': '키프로스', 'LV': '라트비아', 'LT': '리투아니아', 'LU': '룩셈부르크', 'HU': '헝가리', 'MT': '몰타', 'NL': '네덜란드', 'AT': '오스트리아', 'PL': '폴란드', 'PT': '포르투갈', 'RO': '루마니아', 'SI': '슬로베니아', 'SK': '슬로바키아', 'FI': '핀란드', 'SE': '스웨덴', 'IS': '아이슬란드', 'NO': '노르웨이', 'CH': '스위스', 'BA': '보스니아헤르체고비나', 'ME': '몬테네그로', 'MK': '북마케도니아', 'GE': '조지아', 'AL': '알바니아', 'RS': '세르비아', 'TR': '튀르키예', 'XK': '코소보*'}).fillna(table["국가"])
    available=table.dropna(subset=["1인당 발생량(kg/인·년)"]).sort_values("1인당 발생량(kg/인·년)")
    if available.empty:
        raise ValueError("해당 연도의 Eurostat 관측이 없습니다.")
    return AnalysisResult("eurostat_generation","해외 통계 비교","Eurostat 국가별 1인당 municipal waste 발생량",
        "동일 출처·연도의 1인당 municipal waste 발생량 분포는 어떠한가?",
        table,available,"barh","국가","1인당 발생량(kg/인·년)",None,"kg/인·년",str(int(data.year.iloc[0])),
        sorted(set(data.source_url)),f"{len(table)}개 국가 코드 중 {len(available)}개에 값이 있다. 나머지 {len(table)-len(available)}개는 원표 결측이다.",
        ["한국 KOSIS와 폐기물 범위·통계 분모가 조화되지 않아 한국 수치를 이 그림에 합치지 않는다.","국가별 municipal waste 수집 범위 차이와 p/e 등 원표 상태표시를 함께 확인한다.","행정통계 분포이며 정책 인과효과나 신뢰구간을 추정하지 않는다."],
        "src/analysis/international.py",measurement_type="공식 통계·추정 표시 보존")

def nea_materials(frame,year=2024):
    data=frame.loc[(frame.year==year)&(frame.metric.isin(["generated","recycled"]))&(frame.material!="Overall")].copy()
    require_unique(data,["material","metric","year"])
    require_numeric(data,["value"])
    table=data.pivot(index="material",columns="metric",values="value").reset_index().rename(columns={"material":"재질","generated":"발생량(t)","recycled":"보고 재활용량(t)"})
    table["재질(원문)"]=table["재질"]
    table["재질"]=table["재질"].map({'Ferrous metal': '철금속', 'Non-ferrous metal': '비철금속', 'Paper/Cardboard': '종이·판지', 'Construction & Demolition (C&D)': '건설·해체폐기물', 'Plastics': '플라스틱', 'Food': '음식물', 'Wood': '목재', 'Horticultural': '조경폐기물', 'Ash & sludge': '소각재·슬러지', 'Textile/Leather': '섬유·가죽', 'Used slag': '사용 슬래그', 'Glass': '유리', 'Scrap tyres': '폐타이어', 'Others (stones, ceramics, etc.)': '기타(석재·도자기 등)'}).fillna(table["재질"])
    table["계산 재활용비율(%)"]=table["보고 재활용량(t)"]/table["발생량(t)"]*100
    table=table.sort_values("계산 재활용비율(%)")
    return AnalysisResult("nea_materials","해외 통계 비교","싱가포르 재질별 보고 재활용 비율",
        "싱가포르의 같은 연도 안에서 재질별 보고 재활용 비율은 어떻게 다른가?",
        table,table,"barh","재질","계산 재활용비율(%)",None,"%",str(year),sorted(set(data.source_url)),
        f"{len(table)}개 재질의 천 톤 단위 반올림 수치를 t로 변환하고 비율을 계산했다.",
        ["생활·비생활 부문과 건설폐기물을 포함하므로 국내 대응 4품목 또는 municipal waste와 직접 비교하지 않는다.","목재·조경폐기물 재활용에는 연료 사용이 포함된다. 최종 물질재생률이 아니다.","원문 정수 재활용률과 반올림 물량으로 계산한 비율은 차이가 날 수 있다."],"src/analysis/international.py")

def uk_facility_receipts(frame):
    require_unique(frame,["site_key"])
    require_numeric(frame,["received_t"])
    data=frame.loc[frame.site_key.notna()].copy()
    if data.empty:
        raise ValueError("시설 식별자가 있는 반입 자료가 없습니다.")
    table=data[["site_key","received_t","region","facility_type","source_rows"]].rename(columns={"site_key":"공개 허가번호","received_t":"보고 반입량(t)","region":"원문 시설지역","facility_type":"원문 시설유형","source_rows":"합산 원표 행수"})
    # Plot a distribution instead of publishing site-level source records.
    bins=[0,100,1000,10000,100000,1000000,float("inf")]
    labels=["100t 미만","100–1천t","1천–1만t","1만–10만t","10만–100만t","100만t 이상"]
    groups=pd.cut(table["보고 반입량(t)"],bins=bins,labels=labels,right=False)
    plot=groups.value_counts(sort=False).rename_axis("연간 반입량 구간").reset_index(name="허가번호 수")
    summary=table["보고 반입량(t)"].describe(percentiles=[.25,.5,.75,.95]).rename_axis("요약 통계").reset_index(name="값")
    return AnalysisResult("uk_receipts","해외 통계 비교","영국 보고 시설의 연간 반입량 분포",
        "영국 2024 WDI의 공개 허가번호별 보고 반입량 분포는 어떠한가?",
        summary,plot,"bar","연간 반입량 구간","허가번호 수",None,"허가번호 수","2024",
        sorted(set(frame.source_url)),f"공개 허가번호 {len(table):,}개의 반입량을 합산해 분포를 확인했다.",
        ["같은 폐기물의 시설 간 이동이 반복 보고될 수 있다. 반입 합계를 폐기물 발생량이나 최종 재활용량으로 해석하지 않는다.","이 자료만으로 반입/반출 비율이나 최종 수율을 계산하지 않는다.","출처의 조건부 이용허락을 확인해야 하며 원자료와 시설별 행의 공개 재배포를 자동 수행하지 않는다."],
        "src/analysis/international.py",extra={"site_count":len(table),"internal_site_table_not_exported":True})

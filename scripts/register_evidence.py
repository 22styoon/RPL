import csv
from pathlib import Path
import yaml
root=Path(__file__).resolve().parents[1]
report="https://www.guroc.go.kr/kr/bbs/download.do?bbs_id=memnotice&uid=10C5C2B6918247C7947B3A54914B8714"
wage="https://www.minimumwage.go.kr/minWage/policy/decisionMain.do"
literature="https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART001757031"
national="https://www.index.go.kr/unity/potal/eNara/sub/showStblGams3.do?freq=Y&idx_cd=1477&period=N&stts_cd=147701"
def write_csv(path, rows):
    with (root/path).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
sources=[]
for id,title,url,year,scope,unit,grade,status,notes in [
    ("KOSIS_API","KOSIS 폐기물 발생량 및 처리현황_생활폐기물","https://kosis.kr/statHtml/statHtml.do?orgId=106&tblId=DT_106N_29_2020005","2024","전국 및 17시도 생활폐기물; 지역·배출방식·품목 계층 유지","톤/년","A","인증 OpenAPI 실제 조회·원응답 보존","5,292행과 메타데이터 946개 수집. 4품목은 대응 분류의 파생그룹; 영농·복합제품 재질 제외."),
    ("KOSIS_PUBLIC","KOSIS 100대지표 생활폐기물 발생량","https://kosis.kr/visual/nsportalStats/detailContents.do?listId=C&statJipyoId=3664&vStatJipyoId=5061","2020~2024","전국 생활폐기물; 생활계 전체와 다름","톤/년","A","KOSIS 공개 지표 응답 직접 수집","원통계표 DT_106N_29_2020005. 인증 OpenAPI 상세 조회와 구분."),
    ("GURO","구로구 생활폐기물 재활용 활성화 정책 연구",report,"2022~2024","구로구 수거·선별 행정처리 흐름","t/년·원/년","B","공식 원표 전사·단위 변환","표5·6(인쇄57~58쪽), 구청 자료 재수록. 예산은 실물비용/집행액이 아님."),
    ("GURO_SYSTEM","구로구 재활용품 선별시설 안내","https://www.guro.go.kr/www/contents.do?key=2672","현재 시설 설명","구로구 재활용품 선별시설","제도 설명","A","공식 안내 확인","재활용품 혼합 배출을 선별하는 시설. 일일 명목용량을 연간 처리용량으로 환산하지 않음."),
    ("WAGE","최저임금위원회 연도별 결정현황",wage,"2024","대한민국 최저임금","원/시간","A","공식값 9,860원 확인","최저임금을 가계 시간가치로 사용하는 것은 별도의 가정."),
    ("PLASTIC_MFA","폐합성수지 재활용 시설의 물질흐름분석 연구",literature,"2013","국내 폐합성수지 재활용 시설; 구로 전체 품목 아님","시설 공정 수율","B","원논문 초록 확인·참고만","14개 시설 방문 평균 87.5%, 25개 설문 평균 84.3%. 혼합 전체 품목의 85% 관측 근거로 사용하지 않음."),
    ("NATIONAL","생활·사업장·건설폐기물 발생 및 처리현황",national,"2017~2024","전국 생활계폐기물 전체","t/일","A","공식 원표 전사","구로구 사례의 발생량 보정에 사용하지 않음. 일평균×일수의 연간값은 근사치."),
]:
    sources.append(dict(source_id=id,source_title=title,source_url=url,retrieved_at="2026-11-15",reference_year=year,geography="서울특별시 구로구" if id.startswith("GURO") else "대한민국",waste_scope=scope,unit=unit,evidence_grade=grade,status=status,notes=notes))
write_csv("data/sources.csv",sources)
config=yaml.safe_load((root/"configs/scenarios.yaml").read_text(encoding="utf-8-sig"))
rows=[]
def add(path,name,unit,grade,kind,source="",locator="",notes=""):
    rows.append(dict(parameter_path=path,parameter_name=name,value="",unit=unit,evidence_grade=grade,evidence_type=kind,source_url=source,source_title=next((r["source_title"] for r in sources if r["source_url"] == source), "외생 가정 또는 미확인"),source_locator=locator,reference_year=2024,geography="서울특별시 구로구",waste_scope="보고서 수거·선별 행정처리 흐름",retrieved_at="2026-11-15",notes=notes))
for field,name,unit in [
    ("handled_t","처리대상량(원표명: 재활용 발생량)","t/년"),("sorted_t","선별 회수량","t/년"),("residue_t","선별 잔재량","t/년"),
    ("collection_budget_krw","수거운반 예산","원/년"),("sorting_budget_krw","선별처리 예산","원/년"),("total_budget_krw","총 소요예산","원/년")]:
    add("observations."+field,name,unit,"B","공식 보고서 수록 행정자료",report,"표5·6, 인쇄57~58쪽","천원 원표는 ×1,000으로 원 환산. 최종 재생원료량/실물비용이 아님.")
add("runtime.minimum_final_rate","사용자가 요청한 최소 재생원료 전환비율","비율","D","사용자 목표",notes="0이면 A 수준을 적용. 실행 결과 CSV에 요청값과 실제 적용 하한을 별도 저장.")
add("reference_year","기준연도","년","B","자료 범위 선택",report,"표5·6")
add("common.processing_yield","선별 후 최종 재처리 수율","비율","D","혼합 전체 품목에 대한 미관측 가정",literature,"2013 원논문 초록·참고만",notes="플라스틱 시설 평균 84.3%/87.5% 문헌은 참고만. 구로 혼합 전체의 0.85를 정당화하지 않음. 민감도 0.70·0.85·0.95.")
add("common.time_value","가계 시간가치","원/시간","D","공식 최저임금 적용 가정",wage,"2024 적용연도","공식 임금은 A등급. 가계 기회비용으로 적용하는 행위는 D가정. 구로구 총가계비에 미적용.")
add("common.discount_rate","추가 투자 할인율","비율","D","재무 가정",notes="0.03은 공식 지침 준용을 주장하지 않는 실험값.")
add("common.life_years","추가 설비 수명","년","D","재무 가정",notes="15년은 해당 시설의 관측 내용연수가 아님.")
for s in config["scenarios"]:
    prefix="scenarios."+s["id"]+"."
    note={"A":"2024년 관측 선별량/처리대상량으로 계산","B":"2023년 7,949/12,621의 비율을 목표로 재사용; 2024 정책효과 관측이 아님","C":"55%는 저회수 스트레스 가정","D":"65%는 달성 여부가 검증되지 않은 목표"}[s["id"]]
    add(prefix+"sorting_target",s["id"]+" 선별률 기준·목표","비율 또는 기준명","B" if s["id"]=="A" else "D","관측 기준" if s["id"]=="A" else "외생 목표",report if s["id"] in ("A","B") else "","표5" if s["id"] in ("A","B") else "",note)
    for key,name in (("collection_budget_multiplier","수거운반 예산 배율"),("sorting_budget_multiplier","선별처리 예산 배율")):
        add(prefix+key,s["id"]+" "+name,"배","D","기준 유지 또는 정책 가정",notes="관측 예산에 곱하는 외생 배율. 추가 신규투자 연간화는 포함하지 않는다고 가정.")
    add(prefix+"additional_capital",s["id"]+" 추가 투자비","원","D","신규 투자 가정",notes="0은 추가투자를 가정하지 않음. 기존 투자비가 0이라는 의미 아님.")
    add(prefix+"capacity_t",s["id"]+" 연간 처리용량","t/년","미확인","미확인",notes="가동일·교대·품목 범위가 맞는 연간용량 미확인. 전체 제약 검증완료로 표시하지 않음.")
observed_rows=list(csv.DictReader((root/"data/processed/guro_recycling.csv").open(encoding="utf-8-sig")))
observed=next(r for r in observed_rows if int(r["reference_year"])==config["reference_year"])
values={f"observations.{k}":v for k,v in observed.items()}
values["reference_year"]=config["reference_year"]
values["runtime.minimum_final_rate"]=0.0
values.update({f"common.{k}":v for k,v in config["common"].items()})
for scenario in config["scenarios"]:
    values.update({f"scenarios.{scenario['id']}.{k}":v for k,v in scenario.items()})
for row in rows:
    value=values.get(row["parameter_path"])
    row["value"]="미확인" if value is None else str(value)
write_csv("data/input_evidence.csv",rows)
print("한글 출처 목록 및 입력별 근거 등록부 작성 완료")

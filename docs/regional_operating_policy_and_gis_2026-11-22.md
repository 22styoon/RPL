# 2024년 운영정책 증빙과 GIS 경계 감사

## 제주·세종 일회용컵 보증금제

자원순환보증금관리센터는 2022년 12월 2일부터 제주·세종 선도지역의 제도 적용 매장에서 개당 300원을 부과하고, 지정 반납처를 통해 돌려주는 제도를 운영했다. [운영 안내](https://eng.cosmo.or.kr/menu.es?mid=a10202000000)

| 집계 대상 | 집계 기간 | 보증금 대상 컵 판매 | 컵 반환 | 공표 반환율 |
|---|---|---:|---:|---:|
| 제주·세종 선도지역 합계 | 2022-12-02 ~ 2024-11-30 누적 | 2,011만 개 | 1,004만 개 | 49.9% |

환경부가 보고한 만 개 단위의 수량과 공표 반환율을 그대로 사용했다. 지역, 적용 매장의 거래, 품목, 반환 경로와 기간이 맞는 운영 근거와 성과 관측을 1행으로 연결했다. [환경부 2024년도 자체평가 결과보고서 268쪽](https://www.evaluation.go.kr/upload2/atch/eval/20250429100704260.pdf)

시군구 연간 생활폐기물 처리량에 결합 가능한 행은 0행이다. 결합하려면 행정구역 단위, 전체 생활폐기물 모집단과 재질, 연간 관측기간, 물질재활용 처리 단계가 모두 일치해야 한다. 사업의 컵 반환율은 사업 참여 매장의 반환 실적과 모집단을 설명한다.

```powershell
python scripts/join_regional_policy.py --year 2024
python scripts/run_regional_indicator.py --year 2024 --level sido
python scripts/run_regional_indicator.py --year 2024 --level sigungu
```

보고서 **운영정책과 자체 성과**에서 결과를 보고, CSV에서 운영·실적의 공식 URL과 본문 위치를 확인할 수 있다. `operating_policy_household_join_exclusions.csv`에 연간 생활폐기물과 결합하지 않은 근거를 기록한다.

## GIS 경계 감사

MOIS 2024년 12개월 코드·명칭과 229개 폐기물 통계지역 목록을 대조 기준으로 사용한다. 교육부 데이터 목록에 보존된 공공데이터포털 파일은 2023년 통계와 2024년 경계를 담고 있다. 이 ZIP에서 2024년 2분기 시군구 경계의 도형 252개를 추출했다. 모든 도형의 `BASE_DATE`는 2024년 6월 30일이며, 좌표계는 EPSG:5179다. [2024년 경계 보존 목록](https://data.edmgr.kr/dataView.do?id=www-data-go-kr-data-filedata-15129688) · [공공데이터포털 원본 ZIP](https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000003169215&fileDetailSn=1&insertDataPrcus=N)

ZIP의 SHA-256은 `bff76c956926e5a6c8ffa01931a28d7d302fac10410eb04cfbe90bb14f88757b`, `bnd_sigungu_00_2024_2Q.shp`의 SHA-256은 `7da236261196a62885246ab405f86b91f0b264582634abbbe35f75a47262062d`이다.

공개 배포본의 도형 252개를 모두 대조했다. 일반구 35개를 12개 시로 통합하면 폐기물 통계단위 229개가 모두 연결된다. 검증에서 무효 도형과 1㎡를 초과하는 통계단위 간 겹침은 확인되지 않았다. 이 기록의 검증 범위는 공개 배포본의 단일 기준일이다. 분석에 사용할 별도 경계 파일은 수령 후 같은 절차로 대조한다.

1. 원본 ZIP의 `2. 경계/2. 2024년 2분기 기준 시군구 경계/`에서 SHP, SHX, DBF, PRJ, CPG를 함께 추출한다. 별도 배포본은 SGIS **자료제공 → 자료신청 → 센서스용 행정구역 경계(시군구) → 2024년 전국**에서 받을 수 있다. [SGIS 자료 목록](https://sgis.mods.go.kr/view/pss/openDataIntrcn)
2. 대응표 초안을 생성하고 해당 행정구역의 명칭과 코드를 확인한다. 대응표에는 `gis_code,mois_code` 열을 사용한다. 기준일과 출처 URL, `boundary_file`과 `crosswalk_file`, 파일별 SHA-256을 JSON에 기록한다. 기본 경로는 `data/raw/regional_2024/gis_boundary/source_manifest.json`이다. 파일 경로와 `sha256` 항목의 이름은 모두 JSON 파일 기준 상대 경로다.
3. 아래 명령으로 현재 월별 감사, 기준일·해시, GIS 코드·이름, 좌표계와 폴리곤 유효성, 일반구의 상위시 통합, 통계지역 대응 및 도형 겹침을 확인한다. 같은 출처 계열에서 기준일이 다른 두 자료가 있을 때 `--compare-manifest`를 추가해 두 도형의 차이를 비교할 수 있다.

```powershell
python -m pip install -r requirements-gis.txt
python scripts/audit_regional_boundaries.py --check-only
python scripts/audit_regional_gis.py --propose-crosswalk data/raw/regional_2024/gis_boundary/bnd_sigungu_00_2024_2Q.shp --crosswalk-output data/raw/regional_2024/gis_boundary/crosswalk.csv --code-field SIGUNGU_CD --name-field SIGUNGU_NM
python scripts/audit_regional_gis.py
```

출처 JSON의 필수 필드는 `source_url`, `reference_date` (YYYY-MM-DD), `boundary_file`, `crosswalk_file`, `sha256` 객체다. 지문은 `Get-FileHash <파일> -Algorithm SHA256`의 해시를 소문자로 기록한다. 이 배포본은 `code_field`에 `SIGUNGU_CD`, `name_field`에 `SIGUNGU_NM`을 지정한다. 날짜 열은 `BASE_DATE`다.

기본 상태 `source_pending`은 원본 또는 원본 증빙을 기다리고 있다는 뜻이다. 한 파일의 검증이 통과하면 해당 기준일의 센서스 도형과 229개 통계단위 대응을 확인한 것으로 기록한다. 연중 경계 변동은 여러 기준일의 동종 자료가 있어야 조사할 수 있다.

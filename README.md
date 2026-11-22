# RPL | 분리배출 정책 통계분석 및 시각화

**진행 현황 확인: 2026-11-22 (Asia/Seoul).** 지표 연구·지역 감사·법령 연결 구현은 [PR #5](https://github.com/22styoon/RPL/pull/5)에 반영되어 있습니다. 현재 저장 증빙과 입력을 다시 대조한 결과 월별 코드·명칭 감사와 법령 연결 모두 유효했습니다. 이번 확인은 외부 API를 새로 수집한 결과가 아닙니다.

| 작업 | 현재 확보·구현 상태 |
|---|---|
| 국제 비교 지표 연구 | 근거 25항목·그림 12개, H/S 산식과 공통 가중치 민감도 |
| 지역 실자료 | 229개 시군구·4재질 916행, 2024년 12개월 코드·명칭 감사 |
| 법령정보 연결 | 연혁 후보 659버전 중 523버전 지역 코드 일치, 본문 60건·텍스트 1,031항목 검색·원문 연결 |
| 검증 | 마지막 전체 테스트: 2026-11-20, 683개 통과·건너뜀 0개. 2026-11-22에는 현재 입력·증빙 연결을 재확인 |
| 운영정책과 성과 | 제주·세종 일회용컵 보증금제 1건, 2024년 11월 30일까지 누적 반환율 49.9%. 시군구 연간 생활폐기물 처리량과 결합 가능한 정책은 0건 |
| GIS 경계 | 공개된 2024-06-30 SGIS 도형으로 감사 절차와 229개 지역 대응을 확인했습니다. 분석에 사용할 별도 제공본은 수령 후 대조합니다. |

[통합·진행 기록](docs/pr5_integration_review_2026-11-19.md) · [법령 연결 결과](docs/regional_ordinance_candidate_review_2026-11-19.md)

사업 운영 근거와 자체 성과는 지역 보고서와 앱의 **운영정책과 자체 성과**에서 볼 수 있습니다. [운영정책·GIS 재현 안내](docs/regional_operating_policy_and_gis_2026-11-22.md)

## 재활용률의 국제 비교 지표 연구

**국가마다 다른 재활용률의 계산 기준을 맞춘 뒤 비교한다.** [전체 연구 보고서](docs/recycling_indicator_study.md)는 선행연구와 공식 기준 22항목을 검토하고, 같은 폐기물 범위·발생국·발생연도의 최종 재생물질 회수율 H와 공통 재질 구성의 표준화 지표 S를 제안합니다. 산식의 정당성·인과 해석·검증 설계를 함께 설명합니다. [근거 원장](data/indicator_sources.json) · [입력 계약](docs/indicator_data_contract.md)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python scripts/run_recycling_indicator.py
```

[대화형 지표 연구 보고서](outputs/reports/recycling_indicator/index.html)를 열면 실측 통계·문헌 사례·가상 설명을 구분한 **9개 그림**, 그래프 수치 CSV, 발표용 PNG/SVG, 출처와 확인 범위를 볼 수 있습니다. 외부 CDN·API 키 없이 재현하며 앱의 **재활용 지표 연구** 메뉴에서도 확인할 수 있습니다. 실행 결과는 Git에서 제외된 `outputs/`에 생성됩니다. `run_statistical_analysis.py`도 이 연구 보고서를 함께 생성합니다.

한국 0.2·0.3·0.5는 국가 연간 재활용 실적률의 보편 가중치가 아니라 EPR **재활용의무율 설정용** 과거 실적 가중치입니다. 현재 KOSIS 자료는 최종 재생원료 산출량이 아닌 처리량이므로 새 H/S의 국가 관측 순위·정책 인과효과는 미산출 상태로 명시합니다.

## 2026-11-19 후속 연구: 가중치 범위 전체의 비교

초기 22개 근거·9개 그림에 [추가 근거 3항목](data/indicator_followup_sources.json)과 그림 3개를 더해 현재 보고서는 **근거 25항목·그림 12개**입니다. [후속 방법·결과](docs/indicator_weight_robustness_2026-11-19.md)는 두 지역에 같은 가중치를 적용해 허용 범위 전체의 비교가 유지되는지 검증합니다. KOSIS 2024년 17개 시도 136쌍 중, 세 기준 가중치의 모든 혼합에서는 123쌍, 재질별 최소·최대 경계 전체에서는 118쌍, 비음수 가중치 전체에서는 83쌍의 비교 방향이 유지됩니다. 극값을 만드는 가중치·재질 기여도와 보수적 순위 외곽 범위를 CSV로 재현합니다.

같은 실행 명령으로 보고서를 갱신하며 앱의 **재활용 지표 연구 → 가중치 범위 전체의 비교**에서 결과를 확인합니다. 가중치 집합은 민감도 시나리오이고 순위 범위는 신뢰구간이 아닙니다. [JRC 2025 모형과 Eurostat 2026 공표의 확인 범위](docs/indicator_followup_evidence_2026-11-19.md)도 추가했습니다. 이 자료를 최종 H/S 국가 실측값이나 정책 인과효과로 전환하지 않습니다.

## 기존 통계 분석

국내외 폐기물 실데이터를 Python으로 수집·정제·분석하고, 질문별 표·그래프·출처·한계를 재현하는 연구 프로젝트입니다. 기본 보고서는 **독립 분석 9개**를 제공합니다. 별도 지역 연구 보고서는 2024년 `R_r/S_r` 표준화와 가중치 민감도를 분석합니다. 기존 정책 계산은 별도의 **가정 기반 민감도 분석**입니다.

[대화형 통계 보고서](outputs/reports/statistical_analysis/index.html) · [개편 결과·검증](docs/statistical_refactor_report_2026-11-16.md) · [분석 사용법](docs/statistical_analysis_guide.md) · [선행연구](docs/literature_review.md)

[시도 표준화 분석 방법](docs/regional_policy_indicator_method.md) · [지역 자료 공백](docs/regional_data_gap_inventory.md) · [조례 연혁 후보 검토](docs/regional_ordinance_candidate_review_2026-11-19.md) · [기관 자료요청 양식](docs/regional_data_request_template.md)

## 실행

월별 경계 감사는 이제 현재 시군구 코드·명칭, 12월 코드 목록, 월별 자료와 원문 페이지의 지문이 맞아야 유효합니다. 네트워크 없이 상태만 확인하려면 `python scripts/audit_regional_boundaries.py --check-only`를 사용합니다. 입력이 달라지거나 기존 감사에 지문이 없으면 과거 완료·정책 결합을 현재 검증으로 인정하지 않습니다. [감사 증빙 계약과 재현 순서](docs/boundary_evidence_contract_2026-11-20.md)를 참고하세요.

법령정보는 지역 연구 메뉴에서 법령명·기관·조문으로 검색할 수 있습니다. 최신 로컬 수집은 연혁 후보 659버전·본문 60건이며, 조문·부칙 등 1,031개 텍스트 항목에 버전 일련번호·조문 위치·원문 해시·인증값 없는 공개 열람 링크를 연결했습니다. `python scripts/link_law_ordinances.py`로 연결표를 만들고 `--check-only`로 현재 원문·입력의 일치를 확인합니다. 시행일이 2024년인 연혁 검색과 실제 운영정책·연중 유효성을 구분하며, [실자료 결과와 재현 방법](docs/regional_ordinance_candidate_review_2026-11-19.md)을 제공합니다.

기존 가상환경에서는 한 명령으로 저장한 실데이터의 표·PNG/SVG·대화형 그래프·보고서를 다시 만듭니다. 기본 재생성은 네트워크나 API 키를 사용하지 않습니다.

```powershell
.\.venv\Scripts\python run_statistical_analysis.py
.\.venv\Scripts\python scripts/run_regional_indicator.py --year 2024 --level sido
.\.venv\Scripts\python -m streamlit run app.py
```

웹 화면은 http://localhost:8501 에서 열립니다. 보고서는 outputs/reports/statistical_analysis/index.html을 브라우저에서 직접 열어도 됩니다. 외부 CDN 없이 대화형 그래프를 사용할 수 있습니다.

지역 결과는 `outputs/reports/regional_indicator/index.html`에 생성되고 앱의 **시도 표준화 분석** 메뉴에서도 볼 수 있습니다. R과 S, 재질별 기여도, 기준 가중치, 대안별 점수·순위 민감도, OLS/HC0/HC3 진단을 확인할 수 있습니다.

새 환경:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python run_statistical_analysis.py
.\.venv\Scripts\python scripts/run_regional_indicator.py --year 2024 --level sido
```

기본 종합 보고서 실행은 기존 통계 보고서와 별도 지역 분석 보고서를 모두 재생성합니다. 기존 통계 보고서만 필요하면 `run_statistical_analysis.py --skip-regional-indicator`를 사용합니다. 지역 표 원본을 다시 준비하려면 `scripts/prepare_regional_recycling.py --year 2024`를 실행합니다. 수집은 필요할 때만 명시적으로 수행합니다.

```powershell
.\.venv\Scripts\python scripts/collect_regional_recycling.py --source kr_waste_2024_detail --year 2024 --dry-run
.\.venv\Scripts\python scripts/collect_regional_recycling.py --source kr_admin_codes_2024 --year 2024 --dry-run
.\.venv\Scripts\python scripts/collect_law_ordinances.py --limit-pages 30 --details 60
.\.venv\Scripts\python scripts/link_law_ordinances.py
.\.venv\Scripts\python scripts/join_regional_policy.py --year 2024
```

`kr_admin_codes_2024` 갱신에는 별도 `MOIS_API_KEY`가 필요합니다. 법제처 자치법규 연혁은 `LAW_OC` 설정 후 `scripts/collect_law_ordinances.py`로 후보를 검색할 수 있으며, 조례만으로 실제 시행을 확정하지 않습니다. API 신청과 도메인/IP 설정은 [법제처 API 설정](docs/law_api_setup.md), 자료 공백은 [공백 인벤토리](docs/regional_data_gap_inventory.md)를 확인합니다.

## 현재 분석

| 질문 | 데이터 | 결과 |
|---|---|---|
| 국내 발생량은 어떻게 변했는가 | KOSIS 동일 정의 2020~2024 | 추세·증감률·지수·기간 연평균 증감률 |
| 재질별 처리경로는 어떻게 다른가 | KOSIS 2024 대응 4품목 | 물질재활용·에너지회수·소각·매립·기타 구성 |
| 지역 간 처리 구성 차이는 어느 정도인가 | 전국 행과 분리한 17개 시도 | 발생량을 분모로 한 처리비율. 인구보정 지표는 미산출 |
| 재질 구성을 전국 기준으로 맞추면 시도별 비율은 어떻게 달라지는가 | KOSIS 2024 전국 가중치 + 17개 시도 재질별 실측치 | 관측 `R_r`, 표준화 `S_r`, 재질 기여도와 가중치 민감도. 별도 지역 보고서 |
| 선별 회수량과 잔재는 어떻게 변했는가 | 구로구 2022~2024 행정실적 | 관측 처리 흐름·선별 회수율 |
| 공개 예산과 처리대상량은 어떻게 변했는가 | 구로구 같은 연도 예산 | 명목 예산 구성·처리대상량당 예산 참고비율 |
| 시설 명부가 실제로 제공하는 정보는 무엇인가 | 처리시설 API 786행 | 용량·기준연도·지역명 등의 결측률 |
| 해외 국가의 발생량 분포는 어떠한가 | Eurostat 2024 municipal waste | 38개 국가 코드 중 33개 값·5개 결측을 구분한 kg/인·년 |
| 같은 나라의 재질별 보고 재활용 비율은 어떠한가 | 싱가포르 NEA 2024 | 재질 14개의 국내·비국내 부문 합계 |
| 영국 보고시설 반입량 분포는 어떠한가 | England WDI 2024 Version 2 | 원표 352,275행 → 공개 허가번호 6,452개, 구간·요약통계 |

영국 원자료·시설별 행은 출처의 조건부 이용허락에 따라 Git 공개 대상에서 제외합니다. 해당 자료가 없는 환경에서는 이 분석을 자료 미확보로 기록하며, 나머지 분석을 재생성합니다.

## 해외 자료 수집

공식 API·PDF·HTML·ZIP/XLSB에서 실제 검증한 형식만 사용합니다. 원본과 SHA-256, 열람일, 단위·범위·추정 여부를 보존합니다.

```powershell
.\.venv\Scripts\python scripts/collect_international.py --sources eurostat nea epa
.\.venv\Scripts\python scripts/collect_international.py --sources uk_waste
.\.venv\Scripts\python run_statistical_analysis.py
```

출처 등록은 configs/external_sources.yaml, 원본은 data/raw/international, 정규화 자료는 data/processed/international입니다. OECD 구조화 흐름 통계는 미검증이며, 원문 다운로드 시도도 현재 접근 실패 상태입니다. 확인하지 않은 SDMX 주소나 모형 수치를 만들지 않습니다.

## 국내 API 갱신

.env는 Git에서 제외합니다. KOSIS·공공데이터포털·나라장터의 인증정보는 별개로 관리합니다.

```text
KOSIS_API_KEY=...
DATA_GO_KR_SERVICE_KEY=...
JODAL=...
```

```powershell
.\.venv\Scripts\python collect_kosis.py --metadata
.\.venv\Scripts\python collect_kosis.py
.\.venv\Scripts\python collect_kosis.py --public-summary
.\.venv\Scripts\python scripts/collect_public_data.py --dataset facilities --limit-pages 10
.\.venv\Scripts\python scripts/collect_public_data.py --dataset contracts --begin 2024-01-01 --end 2024-01-07 --limit-pages 1
```

계약은 JODAL 키를 우선 사용하고 미설정이면 공통 키를 사용합니다. 조회일은 등록·변경·삭제 사건일이며 서비스 연도와 다릅니다. 기본 페이지 예산은 전체 요청을 통틀어 1페이지입니다. [API 수집 범위](docs/public_data_api_inventory.md)와 [KOSIS 설정](docs/kosis_setup.md)을 확인하세요.

## 해석 원칙

- 관측 통계, 공개 예산 대리값, 공식 추정치, 문헌 모형, 외생 가정을 구분합니다.
- KOSIS 물질재활용 처리량은 최종 재생원료 생산량이 아닙니다.
- 구로구 2024 수거·선별 예산 115.29억원은 관측 총사회적 비용이 아닙니다.
- 한국·해외의 연도·폐기물 범위·분자·분모·처리단계가 다르면 통합 비교를 차단합니다.
- 비용 단가 4개·실제 가구 시간·최종 수율·용량은 아직 추가 근거가 필요합니다. 결측은 0으로 채우지 않습니다.
- 문헌 평균으로 개인별 표본을 생성하지 않습니다. 짧은 연도 자료에서 정책 인과효과나 회귀 결과를 꾸미지 않습니다.

[비용 근거의 경계](docs/cost_boundary.md) · [비용 현황 기록](docs/current_social_cost_status_2026-11-16.md) · [보조 민감도 사용법](docs/policy_experiment_guide.md)

## 2024 지역 표준화 분석

전국 기준의 시도 보고서는 `outputs/reports/regional_indicator/index.html`에 생성됩니다. 시군구 기술 비교는 아래 명령으로 만들며, HTML 보고서와 CSV·그래프를 `outputs/reports/regional_indicator_sigungu/`, `outputs/tables/regional_indicator_sigungu/`, `outputs/figures/regional_indicator_sigungu/`에 저장합니다.

```powershell
.\.venv\Scripts\python scripts/run_regional_indicator.py --year 2024 --level sigungu
```

현재 로컬의 공식 원표 처리 결과는 시군구 229곳, 4개 재질 916행입니다. `R`은 해당 지역의 실제 재질 구성으로 집계한 처리비율이고 `S`는 모든 지역에 KOSIS 전국 재질 발생 비중을 적용한 비교값입니다. 월별 행정코드·명칭 감사에서 229개 통계단위가 12개월 모두 일치했습니다. 법제처 조례 연혁 659버전 중 523버전은 통계지역 코드에 연결됐습니다. 확인된 보증금제의 자체 성과는 별도 표에 표시하며, 시군구 연간 생활폐기물 처리량과 범위가 일치한 정책 결합은 0행입니다. 원자료와 처리 데이터는 배포 권한을 확인하기 전 저장소에 포함하지 않으므로, 새 환경에서는 지역 자료 수집 및 전처리가 먼저 필요합니다.

행정코드 감사의 범위와 법제처 조례후보 수집 설정은 [자료 공백 현황](docs/regional_data_gap_inventory.md)과 [법제처 API 설정](docs/law_api_setup.md)을 확인하세요.

## 검증

```powershell
.\.venv\Scripts\python -m pytest -q
```

중복집계·물질수지·연도/단위/정의 불일치·결측 보존·출처 해시·그래프 수치 재현·화면 렌더링을 검증합니다. 기존 내부 정책 인터페이스와 run_analysis.py·run_policy.py는 보조 분석용으로 유지합니다.

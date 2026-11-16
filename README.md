# RPL | 분리배출 정책 통계분석 및 시각화

## 재활용률의 국제 비교 지표 연구

**국가마다 다른 재활용률의 계산 기준을 맞춘 뒤 비교한다.** [전체 연구 보고서](docs/recycling_indicator_study.md)는 선행연구와 공식 기준 22항목을 검토하고, 같은 폐기물 범위·발생국·발생연도의 최종 재생물질 회수율 H와 공통 재질 구성의 표준화 지표 S를 제안합니다. 산식의 정당성·인과 해석·검증 설계를 함께 설명합니다. [근거 원장](data/indicator_sources.json) · [입력 계약](docs/indicator_data_contract.md)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python scripts/run_recycling_indicator.py
```

[대화형 지표 연구 보고서](outputs/reports/recycling_indicator/index.html)를 열면 실측 통계·문헌 사례·가상 설명을 구분한 **9개 그림**, 그래프 수치 CSV, 발표용 PNG/SVG, 출처와 확인 범위를 볼 수 있습니다. 외부 CDN·API 키 없이 재현하며 앱의 **재활용 지표 연구** 메뉴에서도 확인할 수 있습니다. 실행 결과는 Git에서 제외된 `outputs/`에 생성됩니다. `run_statistical_analysis.py`도 이 연구 보고서를 함께 생성합니다.

한국 0.2·0.3·0.5는 국가 연간 재활용 실적률의 보편 가중치가 아니라 EPR **재활용의무율 설정용** 과거 실적 가중치입니다. 현재 KOSIS 자료는 최종 재생원료 산출량이 아닌 처리량이므로 새 H/S의 국가 관측 순위·정책 인과효과는 미산출 상태로 명시합니다.

## 기존 통계 분석

국내외 폐기물 실데이터를 Python으로 수집·정제·분석하고, 질문별 표·그래프·출처·한계를 재현하는 연구 프로젝트입니다. 기본 보고서는 **독립 분석 9개**를 제공합니다. 별도 지역 연구 보고서는 2024년 `R_r/S_r` 표준화와 가중치 민감도를 분석합니다. 기존 정책 계산은 별도의 **가정 기반 민감도 분석**입니다.

[대화형 통계 보고서](outputs/reports/statistical_analysis/index.html) · [개편 결과·검증](docs/statistical_refactor_report_2026-11-16.md) · [분석 사용법](docs/statistical_analysis_guide.md) · [선행연구](docs/literature_review.md)

[시도 표준화 분석 방법](docs/regional_policy_indicator_method.md) · [지역 자료 공백](docs/regional_data_gap_inventory.md) · [기관 자료요청 양식](docs/regional_data_request_template.md)

## 실행

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
.\.venv\Scripts\python scripts/join_regional_policy.py --year 2024
```

`kr_admin_codes_2024` 갱신에는 별도 `MOIS_API_KEY`가 필요합니다. 수거정책 자료는 검증 가능한 원문이 아직 확보되지 않아 자동 수집·결합하지 않습니다. 검증된 정책 후보를 받으면 `data/processed/regional_2024/policy_candidates_unverified.csv`에 근거 필드를 채운 뒤 결합 명령으로 재검증합니다. API 응답·정책 자료의 상태는 [공백 인벤토리](docs/regional_data_gap_inventory.md)에 기록합니다.

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

현재 로컬의 공식 원표 처리 결과는 시군구 229곳, 4개 재질 916행입니다. `R`은 해당 지역의 실제 재질 구성으로 집계한 처리비율이고 `S`는 모든 지역에 KOSIS 전국 재질 발생 비중을 적용한 비교값입니다. 시군구 결과는 기술 비교이며, 2024년 연중 행정경계 감사와 정책 자료 결합이 끝날 때까지 지도·정책 순위·시군구 회귀로 해석하지 않습니다. 원자료와 처리 데이터는 배포 권한을 확인하기 전 저장소에 포함하지 않으므로, 새 환경에서는 지역 자료 수집 및 전처리가 먼저 필요합니다.

## 검증

```powershell
.\.venv\Scripts\python -m pytest -q
```

중복집계·물질수지·연도/단위/정의 불일치·결측 보존·출처 해시·그래프 수치 재현·화면 렌더링을 검증합니다. 기존 내부 정책 인터페이스와 run_analysis.py·run_policy.py는 보조 분석용으로 유지합니다.

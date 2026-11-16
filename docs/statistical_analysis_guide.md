# 통계분석 및 시각화 사용법

대상: RPL | 분리배출 정책 통계분석 및 시각화. 기본 화면은 실제 통계 결과이며 기존 조건부 계산은 가정 기반 민감도 분석 메뉴에 있다.

## 한 번에 재생성

```powershell
.\.venv\Scripts\python run_statistical_analysis.py
```

저장된 국내·해외 자료를 분석하며 기본 실행은 네트워크와 API 키를 사용하지 않는다. source SHA-256과 정규화 CSV 해시가 맞지 않으면 해외 자료를 분석하지 않고 오류를 낸다. 원자료를 바꿨다면 수집기·정규화부터 다시 실행한다.

결과 위치:

| 출력 | 위치 | 내용 |
|---|---|---|
| 대화형 전체 보고서 | outputs/reports/statistical_analysis/index.html | 질문·해석·표·Plotly 그래프·출처·한계 |
| Markdown 보고서 | 같은 폴더 report.md | 표·정적 그림 링크·자료 공백 |
| 실행 근거 | 같은 폴더 manifest.json | 분석 목록·코드·입력 해시·그래프 수치 해시·실행일 |
| 분석표 | outputs/tables/statistical_analysis/*.csv | 지표별 계산 결과·결측 |
| 그래프 수치 | 같은 폴더 *_plot.csv | PNG/SVG·Plotly에 공통으로 사용한 값 |
| 그림 | outputs/figures/statistical_analysis | PNG·SVG·개별 대화형 HTML·Plotly JSON |

보고서 HTML은 외부 CDN에 의존하지 않는다. PNG의 한글은 시스템의 맑은 고딕·Noto Sans CJK KR·나눔고딕·AppleGothic 중 사용 가능한 글꼴을 선택한다. SVG는 글리프 경로를 보존한다. 해당 글꼴이 없는 Linux 환경에서는 한글 글꼴을 설치한 후 재생성한다.

## 화면

```powershell
.\.venv\Scripts\python -m streamlit run app.py
```

국내 통계 현황 / 지역·재질별 비교 / 해외 통계 비교 / 시설 및 비용 분석 / 가구 시간 분석 / 선행연구 / 자료 출처·품질의 일곱 메뉴에서 분석 결과를 탐색한다. 각 그래프 아래 펼침 영역에서 CSV·PNG·SVG를 받는다. 자료 출처·품질 메뉴에서 보유 자료로 결과를 재생성할 수 있다.

가정 기반 민감도 분석은 별도 보조 메뉴다. 지역 4품목·구로구 사례·가구 시간가치의 입력 가정과 결과를 검토하며 실측 통계와 섞지 않는다.

## 해외 수집과 비교

```powershell
.\.venv\Scripts\python scripts/collect_international.py --sources eurostat nea epa
.\.venv\Scripts\python scripts/collect_international.py --sources uk_waste
.\.venv\Scripts\python run_statistical_analysis.py
```

Eurostat는 공식 Statistics API의 JSON-stat 큐브를 순서·희소 결측·원표 상태표시와 함께 해석한다. THS_T는 t로 변환하고 KG_HAB는 kg/인·년을 유지한다. EPA 2018 요약의 미국 short ton은 0.90718474 t로 변환하고 원 단위·반올림 및 방법 변경을 기록한다.

NEA는 공식 링크된 PDF의 2015~2025 표를 파싱한다. 천 톤 단위를 t로 변환하며 목재·조경 연료 이용이 보고 재활용에 포함된다는 점을 보존한다. 국가 간 동일 물질재생률로 해석하지 않는다.

영국 WDI 반입 ZIP의 실제 형식은 XLSB다. 수거 방식·시간·최종수율 자료가 아니라 허가시설의 반입 보고 자료다. 음수 정정 행은 삭제·0 치환하지 않고 허가번호 내 합산과 함께 횟수를 기록한다. 업체명·주소·좌표는 정규화 표에 복사하지 않는다. 원자료·시설별 정규화 행의 공개 재배포는 기본 Git 대상에서 제외했다. 공식 메타데이터의 조건부 이용허락을 확인해야 한다.

OECD 모듈은 공식 문서 보존용 경로를 제공하지만 이번 실행에서는 원문 다운로드가 실패했다. 구조화 흐름 표와 SDMX 식별자도 미검증이다. 자료 목록과 공백표에 이를 표시하며 실데이터 결과를 만들지 않는다.

## 자료 공백을 읽는 법

빈칸은 미입력·미관측이며 0과 다르다. Eurostat 2024 발생량 표는 국가 코드 38개를 보존하고 값이 있는 33개만 그림에 쓴다. 한국과의 직접 비교는 분자·분모·범위·연도 등의 호환성 검사에서 제외 사유를 표시한다.

구로구 예산 참고비율은 같은 범위의 공개 예산을 행정처리 대상량으로 나눈 값이다. 계약 처리단가·실집행액·사회적 실물비용으로 자동 채택하지 않는다. 계약 샘플의 검증 완료 원/t는 현재 0건이다.

국내 가구별 시간 원자료가 없어 시간 분포·부트스트랩 신뢰구간은 표시하지 않는다. [시간일지 빈 양식](../data/household_diary_template.csv)에 익명 가구 ID·주차·세척·분류·보관·배출 이동·배출량을 입력한다. 미입력 작업 시간을 0으로 바꾸지 않는다. 주차별 관측을 가구별로 먼저 평균해 반복 측정이 표본 수를 부풀리지 않게 한다.

## 코드와 출처

분석은 src/analysis, 해외 수집은 src/external_data, 정의 대조는 src/comparability.py에 분리했다. [해외 출처 설정](../configs/external_sources.yaml), [문헌 근거](literature_review.md), [국내 API 목록](public_data_api_inventory.md)을 참고한다.

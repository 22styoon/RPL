# 선행연구 검토

## 재활용률의 비교 기준과 지표 개발

2026-11-16 후속 연구에서는 비용·가구 시간 중심의 아래 목록에 더해 **재활용률의 정의·측정점·재질 표준화·원료 대체·인과 식별**을 조사했다. [전체 지표 연구](recycling_indicator_study.md)와 [22개 학술·공식·방법 근거 원장](../data/indicator_sources.json)에 확인 범위와 한계를 정리했다. 목적 중심 검토이며 전수 체계적 문헌고찰·메타분석은 아니다. `python scripts/run_recycling_indicator.py`로 실제 통계·문헌 사례·가상 설명을 구분한 9개 그림과 보고서를 재현한다.

## 기존 분리배출 비용·시간 연구

확인일: 2026-11-16. 기계 판독 근거는 [literature_evidence.csv](../data/literature_evidence.csv)에 기록했다. 초록·색인 본문·선택한 원문 절을 구분하며, 모든 논문의 원자료를 확보한 상태는 아니다.

| 질문 | 확인한 연구 | 활용 | 현재 한계 |
|---|---|---|---|
| 가구가 얼마나 시간을 쓰는가 | [Bruvoll 외, 2002](https://www.sciencedirect.com/science/article/abs/pii/S0921344902000551) | 노르웨이 1999년 자기보고 설문 1,162명의 근사 평균 약 30분/주와 185시간/톤 | 개인별 분포·정책 전후 증분시간은 확보하지 않음 |
| 시간을 어떻게 가치화하는가 | [Nainggolan 외, 2019, 저자기관](https://pure.au.dk/portal/en/publications/consumers-in-a-circular-economy-economic-analysis-of-household-wa/) | 덴마크 선택실험의 2.8–6.3 EUR/시간 | 모형·집단 간 범위이며 신뢰구간이 아님. 한국 환산 입력 금지 |
| 수거·선별 비용의 경계 | [Lakhan, 2015](https://www.mdpi.com/2079-9276/4/2/384) | 223개 온타리오 지자체·10년 패널을 사용한 시스템 비교 | 원문 표·분모 검증 전 28.5% 수치를 분석 입력에 채택하지 않음 |
| 비용과 환경영향의 동시 검토 | [Berardocco 외, 2022](https://www.mdpi.com/2071-1050/14/24/16747) | 단일·다중흐름 수거비 86.96·89 USD/source-ton, 기능단위·MRF 경계 | 사례 모형 결과. source-ton·가격연도 확인 전 한국 원/t 대입 금지 |
| 출하물 품질 | [Damgacioglu 외, 2020](https://pubmed.ncbi.nlm.nih.gov/31812094/) | MRF 4곳, OCC 35개·ONP 266개 표본. 기준 내 OCC 31.4%, ONP 0% | 표본 합격률이 최종 질량 수율은 아님 |
| 플라스틱 공정손실 | [OECD, 2022](https://www.oecd.org/en/publications/2022/02/global-plastics-outlook_a653d1c9/full-report/component-7.html) | 수거와 최종 경로를 구별하는 기관 모형 자료 | 구조화 테이블·SDMX 식별자 미검증. 수율 자동 채택 없음 |
| 국내 분리배출 역량 | [류호재 외, 2026](https://jepa.or.kr/_PR/view/?aidx=49071&bidx=4407) | 서울 615명의 16문항 평균 9.23점 | 시간·비용 관측으로 해석하지 않음 |

문헌 간 방향이 다른 결과도 보존한다. 수거 편의성, 시설 선별비, 출하물 품질, 지역 조건은 서로 다른 경계이므로 한 효과크기로 합치지 않는다. 현재 메타분석·개인별 시간분포·부트스트랩 신뢰구간은 산출하지 않는다.

국내 예비조사는 [빈 시간일지 양식](../data/household_diary_template.csv)으로 시작한다. 탐색 표본 20~40가구를 2~4주 관측하고, 세척·분류·보관·배출 이동 시간과 배출량을 기록한다. 주차별 반복 관측을 먼저 가구별로 평균하며 대표성이나 정책 인과효과를 주장하지 않는다. 개인정보를 수집할 식별자는 익명 가구 ID로 제한한다.

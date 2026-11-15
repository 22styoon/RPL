# 데이터 사전

## 국가통계포털 주자료

- data/raw/kosis/public_waste_summary.json: KOSIS 공개 차트의 실제 응답.
- data/raw/kosis/public_waste_summary_manifest.json: 조회조건·수집경로·SHA-256.
- data/processed/kosis_public_waste.csv: 2020~2024 전국 생활폐기물 발생량, 톤/년. 일평균에서 환산한 수치가 아님.
- data/raw/kosis/*_metadata.json: 인증 API로 받은 분류·항목 설명(키 설정 후).
- data/processed/kosis/통계표_연도.csv: 상세 통계. 통계부호·분류 코드·단위·최종수정일 보존.

KOSIS 공개 지표의 전국 코드와 OpenAPI의 자료 항목 코드는 별개입니다. 구분 계층의 지역·품목·총계·소계를 단순 합산하지 않습니다.

## 원자료와 변환

- `data/raw/guro_table_5_6.csv`: 구로구의회 보고서 표5·6 수동 전사. 수량 t/년, 예산 천원/년.
- `data/processed/guro_recycling.csv`: 예산을 ×1,000하여 원/년으로 변환. 물질수지·예산 합계 검증 후 생성.
- `data/raw/minimum_wage.csv`: 공식 2024 최저임금 원/시간.
- `data/raw/transcription_manifest.csv`: 전사 CSV 자체의 SHA-256. 원문 파일의 해시와 다름.
- `data/sources.csv`: 출처·범위·연도·단위·증거등급.
- `data/input_evidence.csv`: 입력별 근거 등록부. 화면·분석 실행 시 현재 설정값을 다시 적용.
- `outputs/tables/input_evidence.csv`: 해당 CLI 실행에 사용한 실제 값·근거.
- `data/processed/korea_waste_trend.csv`: 전국 생활계폐기물 별도 참고 추세. 구로 사례의 보정 계수가 아님.

기본 추적 필드는 source_url, source_title, retrieved_at, reference_year, geography, waste_scope, unit, evidence_grade입니다. 입력 근거의 자료명은 source_url에 대응하는 sources.csv에서 확인할 수 있습니다.

공식 최저임금 자체는 A등급이며, 이를 가계의 시간가치로 쓰는 적용 가정은 D등급입니다. 구로구청 자료를 재수록한 의회 연구보고서 값은 B등급으로 구분했습니다.

## 모형과 결과

| 내부 항목 | 의미 |
|---|---|
| handled_t | 보고서의 수거·선별 행정처리 대상량. 구 전체 발생량 아님 |
| sorted_t | 선별 적격 회수량 |
| sorting_rate | sorted_t / handled_t |
| processing_yield | 선별 후 최종 재처리 수율 가정 |
| recycled_t | sorted_t × processing_yield |
| final_rate | recycled_t / handled_t. 가정 적용 전환비율 |
| comparison_cost | 공공예산 대리값 + 추가 신규 투자 연간화 |
| recycling_ok | A와 사용자의 목표 중 더 높은 전환비율 충족 여부 |
| capacity_status | 연간 처리용량 미확인·충족·초과 |
| feasible | 재생원료 조건을 충족하고 확인된 용량 초과가 없는 조건부 비교 대상 |
| fully_verified | 모든 제약 검증 여부. 현재는 법규·용량 등 미검증으로 아니오 |
| savings_vs_a | A의 포함비용 − 해당 대안 포함비용 |

화면과 CSV는 한글 열 이름을 사용하며 비율은 %입니다. 내부 Python 값은 0~1 비율입니다. 미공표 비용은 None/빈 칸을 유지하므로 0원으로 읽으면 안 됩니다.

전국 추세 value는 t/일 전사값입니다. annual_t_estimate는 반올림된 일평균 ×해당연도 일수의 근사치이며 원자료 연간량이 아닙니다. 2020·2024년은 366일을 사용합니다.

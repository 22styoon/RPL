# 데이터 사전

`data/processed/korea_waste_trend.csv`: value는 원표의 생활계폐기물 발생량(t/일) 전사값입니다. annual_t_estimate는 value × days_in_year로 계산한 근사 t/년이며 반올림된 일평균으로부터 도출했습니다. 원본 연간 발생량으로 취급하지 않습니다.

출처 공통 필드: source_url, source_title, retrieved_at(열람일), reference_year(대상연도), geography, waste_scope, unit, evidence_grade. A는 공식 관측, D는 합성 가정입니다. 미확인 수치는 이 표에 입력하지 않습니다.

물질수지: generated → collected → sorted → recycled. uncollected, sorting_loss, processing_loss의 합이 disposal입니다. final_rate = recycled / generated. 최종 재생원료 전환율이며 공식 재활용 처리 비율과 다릅니다.

원자료 페이지 URL은 sources.csv에 보존했습니다. 현재 추세는 수동 전사로, 원본 보고서 파일 자동수집·해시 보존 파이프라인은 아직 없습니다.

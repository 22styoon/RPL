"""화면·CSV에 공통으로 적용하는 한글 명칭과 단위."""
LABELS = {
    "id": "시나리오", "name": "대안 설명", "handled_t": "처리대상량(t/년)",
    "sorting_rate": "선별률(%)", "sorted_t": "선별 회수량(t/년)",
    "processing_yield": "가정 재처리 수율(%)", "final_rate": "가정 적용 재생원료 전환비율(%)",
    "recycled_t": "예상 재생원료량(t/년)", "residue_t": "예상 잔재·공정손실(t/년)",
    "comparison_cost": "비교 포함비용(원/년)", "collection_budget": "수거운반 예산 대리값(원/년)",
    "sorting_budget": "선별처리 예산 대리값(원/년)", "additional_capital_annual": "추가 투자 연간화(원/년)",
    "household_cost": "가계 총비용(미확인)", "reprocessing_cost": "재처리 총비용(미확인)",
    "separate_disposal_cost": "별도 처분비(중복 여부 미확인)",
    "capacity_status": "연간 용량 검증", "fully_verified": "전체 제약 검증완료",
    "evidence_grade": "근거 구분", "recycling_ok": "재생원료 목표 충족",
    "feasible": "조건부 비교 대상", "savings_vs_a": "A 대비 포함비용 절감(원/년)",
    "material": "품목", "handled": "처리대상량(t/년)", "sorted": "선별 회수량(t/년)",
    "recycled": "예상 재생원료량(t/년)", "sorting_loss": "선별 잔재(t/년)",
    "processing_loss": "가정 공정손실(t/년)", "residue_total": "총 잔재·공정손실(t/년)",
    "requested_target": "요청 전환비율(%)", "effective_target": "적용 최소 전환비율(%)",
    "parameter": "변경 가정", "assumption_value": "실험 설정값", "selected": "조건부 최소비용안",
    "reference_year": "기준연도", "source_url": "출처 주소", "source_title": "자료명",
    "retrieved_at": "확인일", "geography": "지역", "waste_scope": "대상 범위",
    "unit": "단위", "status": "확인 상태", "notes": "해석 및 제한", "source_id": "출처 식별자",
    "parameter_path": "설정 항목", "parameter_name": "입력 항목", "value": "입력값",
    "evidence_type": "자료 성격", "source_locator": "원문 위치",
}
PARAMETERS = {"processing_yield": "최종 재처리 수율 가정", "collection_budget_multiplier": "수거운반 예산 배율", "sorting_budget_multiplier": "선별처리 예산 배율"}

def korean_table(table):
    result = table.copy()
    for column in ("sorting_rate", "processing_yield", "final_rate", "requested_target", "effective_target"):
        if column in result:
            result[column] = (result[column] * 100).round(3)
    for column in ("fully_verified", "recycling_ok", "feasible"):
        if column in result:
            result[column] = result[column].map({True: "예", False: "아니오"})
    if "parameter" in result:
        result["parameter"] = result.parameter.map(PARAMETERS)
    return result.rename(columns=LABELS)

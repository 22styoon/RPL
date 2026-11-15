# 조건부 정책 실험 사용법

대시보드를 실행하고 **조건부 정책 실험** 탭을 엽니다.

```powershell
.\.venv\Scripts\python -m streamlit run app.py
```

## KOSIS 지역별 4품목

1. 실험 대상을 **KOSIS 지역별 4품목**으로 둡니다.
2. 지역과 품목별 최종수율 가정을 선택합니다.
3. B/C/D 표에서 처리비율·수율 변화(%p), 비용 배율·투자·추가용량을 편집합니다. A는 고정 기준선입니다.
4. 비용 비교가 필요하면 단가 4개를 입력합니다. 빈칸 상태에서도 물량·목표 충족 여부는 확인할 수 있지만 비용 순위는 보류합니다.
5. 가계비를 포함하려면 해당 범위의 가구 수와 주간 시간을 입력합니다.
6. 목표 전환비율·공공지출 상한·물질처리 단계 용량을 설정합니다. 도입비중 탐색을 켜면 13개 후보를 비교합니다.
7. 정책 비교·물질수지·목표곡선·민감도를 확인하고 현재 실험 ZIP을 저장합니다.

화면에서 +3%p는 기준 처리비율에 0.03을 더한다는 뜻입니다. B/C/D는 실제 관측된 정책 효과가 아닙니다. 물질재활용 외 경로는 모두 매립이나 선별 잔재가 아닙니다.

미입력 비용과 0원은 다릅니다. 비용이 입력돼도 법규·기술·시설 실행 가능성이 자동 검증되는 것은 아닙니다. 실제 지역 원가를 확보하기 전에는 총사회비용 최적정책으로 해석하지 않습니다.

## 구로구 시설·예산

실험 대상을 **구로구 시설·예산**으로 바꿉니다. 기준 수율을 설정한 뒤 B/C/D의 선별률·수율·예산 배율·추가투자·연간용량을 편집합니다. E 추가 또는 빈 행을 이용해 새 대안을 넣을 수 있습니다.

목표·비교비용 상한·용량 조건에 따른 탈락 이유와 최소비용곡선을 확인합니다. 빈 용량은 미확인이고 0톤은 처리할 수 없다는 입력입니다. 저장 ZIP은 편집된 현재 설정을 포함합니다.

## 명령행 재현

지역별 입력은 configs/policy_experiment.yaml, 구로구 기본 입력은 configs/scenarios.yaml입니다. 결과 CSV를 수정해도 입력은 바뀌지 않습니다.

```powershell
.\.venv\Scripts\python run_policy.py
.\.venv\Scripts\python run_policy.py --region 서울 --target 0.40 --scan-adoption
.\.venv\Scripts\python run_policy.py --config configs/policy_experiment.yaml --budget 1000000000 --capacity 100000
```

지역별 결과는 outputs/policy_runs/latest/에 저장합니다. policy_results.csv, material_flows.csv, target_curve.csv, sensitivity.csv, inputs.json, policy_run.zip을 제공합니다. 비용 미입력 시 순위가 없는 결과도 정상적인 실행 결과입니다.

중간 개발 보고서는 docs/interim_development_report_2026-11-16.md에 있으며 **입력 근거와 출처** 탭에서도 내려받을 수 있습니다.

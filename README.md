# Recycling Policy Lab

분리배출 정책의 최종 재활용 성과와 연간 사회적 실물비용을 비교하는 Python MVP입니다.

**정책 계산 입력은 전부 합성·가정(D등급)입니다. 실제 정책 우위를 입증하지 않습니다.** 공식 생활계폐기물 추세는 별도 화면에 표시하며 모델 입력으로 사용하지 않습니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python run_analysis.py
.\.venv\Scripts\python -m streamlit run app.py
.\.venv\Scripts\python -m pytest -q
```

설치 전에도 기존 pandas/PyYAML 환경에서 `python run_analysis.py`, `python -m unittest discover -s tests -v`로 계산 및 검증이 가능합니다.

- `configs/scenarios.yaml`: A/B/C/D, 종이·플라스틱·금속·유리의 합성 입력 및 공통 출처 메타데이터.
- `src/model.py`: 물질수지, 투자비 연간화, 비용 분해, 용량·재활용률 제약, 3개 변수 민감도.
- `app.py`: 비교표, 비용·물질수지·민감도·공식 추세, CSV 다운로드.
- `data/sources.csv`: 확인한 통계 출처와 적용 범위.
- `docs/research.md`: 통계 검증 결과와 미확인 항목.
- `outputs/tables/`: CLI 실행 결과. Git 추적 제외.

최적화는 등록된 유한 시나리오 중 최소비용 선택입니다. 연속 투자 최적화나 기업 반응을 추정하지 않습니다. D의 수율·생산자 실물비용은 외생 가정이며 EPR 이전지출은 총비용에서 제외합니다. C는 안전·법규 검증이 없는 탐색안으로 추천에서 제외합니다.

GitHub: https://github.com/22styoon/RPL

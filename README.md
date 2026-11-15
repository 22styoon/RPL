# 분리배출 정책 실험실

KOSIS 국가통계포털의 실제 전국 생활폐기물 추세를 기본 현황 자료로 사용합니다. 구로구 처리실적·예산은 별도의 시설 사례 실험에 사용합니다. 화면, 그래프, 다운로드 CSV는 한글입니다.

## 실행

기존 가상환경이 있으면 프로젝트 폴더에서 실행합니다.

```powershell
.\.venv\Scripts\python -m streamlit run app.py
```

브라우저에서 http://localhost:8501 에 접속합니다. 터미널에서 Ctrl+C로 종료합니다.

새 환경 설치 및 재현:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python scripts/prepare_data.py
.\.venv\Scripts\python scripts/register_evidence.py
.\.venv\Scripts\python run_analysis.py
.\.venv\Scripts\python -m pytest -q
```

## 국가통계포털 API 연결

KOSIS 공개 지표에서 직접 수집한 2020~2024 전국 생활폐기물 발생량을 바로 확인할 수 있습니다. 지역·품목·처리방법별 상세 OpenAPI에는 사용자 인증키가 필요합니다.

[KOSIS 활용신청](https://kosis.kr/openapi/serviceUse/serviceUseUnityReg_01Detail.do) 후 프로젝트 .env에 KOSIS_API_KEY를 저장하세요. 빈 형식은 .env.example에 있습니다. 키는 Git 추적에서 제외하며 요청 URL·로그에도 저장하지 않습니다.

```powershell
.\.venv\Scripts\python collect_kosis.py --metadata
.\.venv\Scripts\python collect_kosis.py
```

공개 전국 지표만 갱신할 때는 인증키 없이 다음을 실행합니다.

```powershell
.\.venv\Scripts\python collect_kosis.py --public-summary
```

현재 프로젝트는 인증 조회에 성공해 2024년 상세 통계 5,292행을 저장했습니다. 지역·배출방식·처리방법 필터와 중복 없는 4품목 집계를 제공합니다. 새 환경의 갱신 작업에는 본인의 로컬 키가 필요합니다. [설정 및 출처](docs/kosis_setup.md)를 참고하세요.

한글 품목 결과는 outputs/tables/kosis_materials_2024.csv에 저장됩니다. 저장된 상세 자료와 메타데이터로 집계를 재현하려면 실행합니다.

```powershell
.\.venv\Scripts\python scripts/prepare_kosis.py
```

## 무엇이 실제 자료인가

구로구의회 2025년 12월 최종보고서 표5·6에 수록된 2024년 처리대상량 13,195t, 선별량 7,733t, 잔재량 5,462t 및 수거운반·선별처리 예산을 사용합니다. 보고서의 원표명은 '재활용 발생량'이나 구 전체 가정 발생량으로 해석하지 않습니다.

구로구는 이미 혼합 배출 재활용품을 선별합니다. 이번 모형은 혼합수거 도입의 효과가 아니라 현행 처리 흐름의 개선 목표를 실험합니다. 품목별 구성 미공표로 4품목을 임의 배분하지 않고 합계 흐름으로 계산합니다. 지역별 4품목은 별도 KOSIS 기준선으로 분석합니다. 구로구 예산을 전국 비용으로 외삽하지 않습니다.

## 사용법

1. **국가통계포털(KOSIS)**: 전국 실제 추세와 API 상세 수집을 확인합니다. **구로구 실제 실적**에서는 구로구 2022~2024 실적·예산과 별도 전국 추세를 확인합니다.
2. **조건부 정책 실험**: KOSIS 지역별 4품목 또는 구로구 시설·예산을 선택합니다. 지역 실험은 처리비율·수율 효과, 비용 4단가, 가계 범위, 예산·용량, 적용 비중을 편집합니다. 시설 실험은 개별 수율·선별률·예산 배율과 새 대안을 편집합니다. 목표곡선·탈락 이유·민감도와 현재 실행 ZIP을 확인합니다.
3. **가구당 시간 비용**: 2024 최저임금 9,860원/시간을 기준으로 주당 절약 시간의 연간 가치를 계산합니다.
4. **입력 근거와 출처**: 관측·외생 가정·미확인과 중간 개발 보고서를 확인합니다. 실제 변경값은 각 실험의 JSON·ZIP에 보존됩니다.

지역별 정책 입력은 `configs/policy_experiment.yaml`, 구로구 기본 입력은 `configs/scenarios.yaml`에서 수정합니다. CSV는 결과이므로 수정해도 모형 입력이 바뀌지 않습니다. 현재 지원하는 사례연도는 2024년입니다.

`python run_analysis.py`는 `outputs/tables/`에 한글 비교표·민감도·입력근거·시나리오별 물질수지를 저장합니다. 비율은 한글 결과 CSV에서 % 단위입니다. 빈 비용은 0이 아니라 미확인입니다.

지역별 실험을 명령행으로 재현할 수 있습니다.

```powershell
.\.venv\Scripts\python run_policy.py
.\.venv\Scripts\python run_policy.py --region 서울 --target 0.40 --scan-adoption
```

결과는 outputs/policy_runs/latest/에 저장합니다. 단가 미입력 시 물량·제약 결과는 계산하지만 비용 순위는 보류합니다.

[정책 실험 사용법](docs/policy_experiment_guide.md) · [중간 개발 보고서](docs/interim_development_report_2026-11-16.md)

## 해석 범위

- 관측 선별률과 가정 재처리 수율을 구분합니다. 최종 재생원료량은 관측값이 아닙니다.
- 구로구는 공공예산 대리값, 지역 4품목은 입력 단가에 따른 범위 내 비교비용입니다. 관측 총사회적 비용·순후생이 아닙니다.
- 지역 4품목의 단가 4개는 미입력으로 시작합니다. 가계비를 포함할 때에는 범위가 맞는 가구 수·시간 입력이 필요합니다. 구로구 미확인 비용은 별도 가산하지 않습니다.
- 연간 시설용량과 법규를 검증하지 않아 결과는 조건부 최소비용안입니다.
- B의 과거 선별률 재사용, 대안별 예산 배율, 추가 투자비·수명·할인율은 정책효과 관측이 아닌 가정입니다.

세부 내용은 [가정](docs/assumptions.md), [자료 조사](docs/research.md), [데이터 사전](docs/data_dictionary.md)을 확인하세요.

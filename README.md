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

실제 인증 성공과 상세 응답 검증은 키 설정 후 가능합니다. [설정 및 출처](docs/kosis_setup.md)를 참고하세요.

## 무엇이 실제 자료인가

구로구의회 2025년 12월 최종보고서 표5·6에 수록된 2024년 처리대상량 13,195t, 선별량 7,733t, 잔재량 5,462t 및 수거운반·선별처리 예산을 사용합니다. 보고서의 원표명은 '재활용 발생량'이나 구 전체 가정 발생량으로 해석하지 않습니다.

구로구는 이미 혼합 배출 재활용품을 선별합니다. 이번 모형은 혼합수거 도입의 효과가 아니라 현행 처리 흐름의 개선 목표를 실험합니다. 품목별 구성 미공표로 4품목을 임의 배분하지 않고 합계 흐름으로 계산합니다. 기존 설계안의 전국·4품목 분석은 자료 확보 후 확장 과제입니다.

## 사용법

1. **국가통계포털(KOSIS)**: 전국 실제 추세와 API 상세 수집을 확인합니다. **구로구 실제 실적**에서는 구로구 2022~2024 실적·예산과 별도 전국 추세를 확인합니다.
2. **조건부 정책 실험**: 목표 전환비율, 최종 재처리 수율, B의 선별예산 증감을 조절합니다. A/B/C/D 중 재생원료 기준을 만족하는 대안의 포함비용을 비교합니다.
3. **가구당 시간 비용**: 2024 최저임금 9,860원/시간을 기준으로 주당 절약 시간의 연간 가치를 계산합니다.
4. **입력 근거와 출처**: 관측·외생 가정·미확인을 확인합니다. 바꾼 설정은 입력 근거 CSV에 반영됩니다.

정책 입력은 `configs/scenarios.yaml`에서 수정합니다. CSV는 결과이므로 수정해도 모형 입력이 바뀌지 않습니다. 현재 지원하는 사례연도는 2024년입니다.

`python run_analysis.py`는 `outputs/tables/`에 한글 비교표·민감도·입력근거·시나리오별 물질수지를 저장합니다. 비율은 한글 결과 CSV에서 % 단위입니다. 빈 비용은 0이 아니라 미확인입니다.

## 해석 범위

- 관측 선별률과 가정 재처리 수율을 구분합니다. 최종 재생원료량은 관측값이 아닙니다.
- 비교 포함비용은 공공예산 대리값과 추가 투자 연간화의 합입니다. 집행액·총사회적 비용·순후생이 아닙니다.
- 대상 가구 수, 최종 재처리비, 별도 처분비는 미확인 또는 중복 여부 불명으로 합계에서 제외합니다.
- 연간 시설용량과 법규를 검증하지 않아 결과는 조건부 최소비용안입니다.
- B의 과거 선별률 재사용, 대안별 예산 배율, 추가 투자비·수명·할인율은 정책효과 관측이 아닌 가정입니다.

세부 내용은 [가정](docs/assumptions.md), [자료 조사](docs/research.md), [데이터 사전](docs/data_dictionary.md)을 확인하세요.

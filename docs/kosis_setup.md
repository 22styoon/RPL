# 국가통계포털 KOSIS 연결

## 필요한 API

현재 필요한 인증정보는 **KOSIS OpenAPI 인증키 1개**입니다. 공공데이터포털의 일반 서비스키와 다른 키입니다.

1. [KOSIS 공유서비스](https://kosis.kr/openapi/)에 로그인합니다.
2. 메뉴 **활용신청**에서 신청합니다. [공식 신청 페이지](https://kosis.kr/openapi/serviceUse/serviceUseUnityReg_01Detail.do)
3. 프로젝트 루트에 `.env` 파일을 만들고 아래 형식으로 저장합니다.

```dotenv
KOSIS_API_KEY=본인이_발급받은_키
```

키 원문은 대화·YAML·Git에 넣지 않습니다. `.env`는 이미 Git 추적에서 제외됩니다. `.env.example`에는 빈 형식만 제공합니다. 환경변수 KOSIS_API_KEY를 사용해도 됩니다.

## 인증키 없이 이미 적용한 자료

KOSIS 공식 100대지표 공개 차트 응답에서 2020~2024년 전국 생활폐기물 발생량을 직접 수집했습니다. 원응답·수집조건·해시를 보존했으며, 인증 OpenAPI로 수집했다고 표시하지 않습니다.

```powershell
.\.venv\Scripts\python collect_kosis.py --public-summary
```

지역·품목·처리방법 상세 분류에는 아래 인증 API를 사용합니다.

## 수집 대상

[폐기물 발생량 및 처리현황_생활폐기물](https://kosis.kr/statHtml/statHtml.do?orgId=106&tblId=DT_106N_29_2020005&conn_path=I2)

- 기관: 106
- 통계표: DT_106N_29_2020005
- 항목: 13103134417I119
- 분류: 구분·항목별의 두 차원. 지역·품목 계층을 임의 합산하지 않습니다.
- 기본 조회: 2024년 연간 자료. 통계표가 공개되어 있다는 사실과 OpenAPI 실조회 성공은 별개입니다.

`configs/kosis.yaml`은 비밀키를 포함하지 않는 조회조건입니다. 인증 후 메타데이터와 응답을 확인해 분류를 필요한 지역·품목으로 좁힙니다. 4만 셀 초과면 오류가 표시되며 자동으로 일부 결과만 사용하는 동작은 하지 않습니다.

## 실행

```powershell
.\.venv\Scripts\python collect_kosis.py --metadata
.\.venv\Scripts\python collect_kosis.py
```

대시보드의 **국가통계포털(KOSIS)** 탭에서도 공식 자료 불러오기 버튼을 사용할 수 있습니다. 실제 HTTP 인증과 수집은 키 설정 후 검증할 수 있습니다.

원응답 JSON·조회조건·SHA-256은 `data/raw/kosis/`, 정리된 CSV는 `data/processed/kosis/`에 저장합니다. 인증키와 키가 포함된 요청 URL은 저장하지 않습니다. 수집된 통계의 분류 코드·명칭·단위·통계부호를 보존합니다.

## 해석

발생량·재활용 처리량은 선별 후 최종 재생원료 생산량과 다릅니다. KOSIS 통계는 국가 현황의 주자료로 사용하고, 구로 시설 실험은 별도 보조 분석으로 유지합니다. 원표의 단위·발생원·연도가 맞는지 확인하기 전에는 시설 실험의 물량이나 수율에 자동으로 덮어쓰지 않습니다.

[공식 개발가이드](https://kosis.kr/openapi/devGuide/devGuide_0201List.do), [공식 서비스 소개](https://kosis.kr/openapi/introduce/introduce_01List.do)를 기준으로 구현했습니다.

# 법제처 자치법규 API 설정과 수집

## 신청 정보

1. [국가법령정보 공동활용 가입·신청](https://open.law.go.kr/LSO/usrJoin.do)에서 회원가입 후 `OPEN API를 신청합니다`를 선택합니다.
2. API 인증값(OC)은 서비스 가입자가 직접 정하는 값입니다. `.env`에 넣을 때도 `LAW_OC` 이름을 사용합니다. KOSIS 키와 별개입니다.
3. 시스템명·설명에는 RPL의 지역 재활용 정책 연구를 적고, 도메인과 서버 IP는 실제 호출 환경과 맞게 등록합니다. API는 등록된 IP와 도메인 정보를 확인할 수 있으므로, `law.go.kr`처럼 제공기관의 주소를 본인 시스템 주소로 적지 않습니다.
4. 자치법규 목록·본문 JSON API를 신청합니다. 신청 후 자동 승인으로 안내되어 있으나, 실제 호출에서 사용자 검증 오류가 나면 마이페이지의 API 인증키·IP 접속이력과 등록정보를 확인하고 법제처 기술지원에 문의합니다.
5. 발급값과 실제 서비스 도메인을 프로젝트 루트의 `.env`에 저장합니다. 키 원문은 대화나 저장소에 올리지 않습니다.

```dotenv
LAW_OC=가입할 때_정한_OC값
LAW_API_DOMAIN=http://localhost
```

### 도메인과 서버 IP 입력

현재 RPL은 Streamlit을 로컬 PC의 `localhost:8501`에서 실행합니다. 신청서 도메인 URL에서 프로토콜을 `http://`로 고르고 도메인 칸에는 `localhost`를 입력합니다. 포털이 이 값을 거부하거나 실제 호출에서 도메인 검증 오류를 내면, 법제처 기술지원(02-2109-6446)에 로컬 Python/Streamlit 개발 서비스의 허용값을 확인합니다. 그 경우 실제 인터넷 서비스 도메인을 배포해 등록해야 할 수 있습니다. `law.go.kr`은 API 제공기관 주소이고 GitHub 저장소 URL은 배포 도메인이 아니므로 입력하지 않습니다.

서버 IP에는 API 요청을 보내는 이 PC 네트워크의 **공인 IPv4 주소**를 입력합니다. 같은 PC의 PowerShell에서 아래 명령으로 확인할 수 있습니다.

```powershell
(Invoke-RestMethod https://api4.ipify.org).Trim()
```

`192.168.x.x`, `10.x.x.x`, `127.0.0.1` 같은 사설·루프백 주소는 등록하지 않습니다. 학교·회사 Wi-Fi, 집, 테더링 등 네트워크가 바뀌거나 공인 IP가 동적으로 변경되면 API 인증 설정의 서버 IP도 갱신해야 합니다.

## 실행 순서

키 설정 전에는 네트워크 호출 없이 계획을 확인합니다.

```powershell
.\.venv\Scripts\python scripts/collect_law_ordinances.py --dry-run
```

설정이 끝나면 시행일이 2024년인 자치법규 연혁 버전을 검색합니다. 2024년에 유효했던 모든 법규나 정책 노출기간을 포괄하는 검색은 아닙니다. 기본 검색어는 재활용·분리수거·폐기물·자원순환·생활폐기물·재활용가능자원이며, 목록 페이지 요청 예산은 전체 30회입니다. 본문은 호출량을 제한하기 위해 기본 수집하지 않습니다.

```powershell
.\.venv\Scripts\python scripts/collect_law_ordinances.py --limit-pages 30
.\.venv\Scripts\python scripts/collect_law_ordinances.py --keyword 재활용 --keyword 분리수거 --details 20
.\.venv\Scripts\python scripts/collect_law_ordinances.py --limit-pages 30 --details 60
```

OC가 들어간 상세링크는 로컬 저장 전에 인증 파라미터를 제거합니다. 이 정제 JSON·해시·요청조건·수집시각은 `data/raw/regional_2024/law_ordinances/`에, 검색결과는 `data/processed/regional_2024/policy_ordinance_candidates.csv`에 저장합니다. OC 값은 로그·manifest·저장파일에 포함하지 않습니다.

2024년 후보 기관명을 2024년 12월 MOIS 코드목록과 대조하려면 다음을 실행합니다. 정확히 연결되는 기관명을 교차표에 기록하고, 검증한 본문 텍스트의 조문 위치·원문 해시·공개 열람 링크를 별도 CSV에 연결합니다. 운영정책 검증이나 성과 결합은 하지 않습니다.

```powershell
.\.venv\Scripts\python scripts/link_law_ordinances.py
.\.venv\Scripts\python scripts/link_law_ordinances.py --check-only
```

`--check-only`는 네트워크 요청·파일 수정 없이 현재 원문과 입력의 연결을 확인합니다. 원문·후보·코드·조문 CSV가 바뀌면 다시 수집·연결해야 합니다. 법규명·기관·조문 검색과 다운로드는 지역 연구 메뉴에 있으며, [실자료 연결 결과와 해석 범위](regional_ordinance_candidate_review_2026-11-19.md)를 함께 확인합니다.

## 해석 경계

목록·본문 API가 확인하는 것은 자치법규의 제목·연혁·시행일·조문 등 법률자료입니다. 이것만으로 해당 지자체가 2024년에 실제 사업을 운영했거나, 시군구 전체 주민에게 적용했거나, 해당 정책으로 재활용 처리량이 변했다는 사실은 확인되지 않습니다. API 결과는 모두 `ordinance_history_only_operational_policy_unverified` 후보로 취급합니다. 실측 결과와 결합하기 전에는 사업 시행계획·실적·계약서 등에서 실제 시행일, 운영주체, 수거방식, 대상 재질, 전체 시군구 범위를 별도 확인해야 합니다.

공식 문서: [자치법규 목록 API 가이드](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=ordinListGuide), [자치법규 본문 API 가이드](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=ordinInfoGuide), [회원가입·API 신청](https://open.law.go.kr/LSO/usrJoin.do).

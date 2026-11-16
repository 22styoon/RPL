# 공공데이터 API 목록과 수집 범위

확인일: 2026-11-16(한국시간). 공식 페이지의 내장 Swagger 및 나라장터 계약 참고문서 2026-11-10판을 확인했다. 시설은 실제 인증된 JSON 정상 응답과 8페이지·786건 전체 조회 및 정규화를 확인했다. 계약 전용 `JODAL` 키로 용역 현황 JSON의 첫 100행과 비용 후보 100개를 보존했으며 계약 수집은 `partial`이다.

| 검증 항목 | 현재 상태 |
|---|---|
| 공식 base URL·operation·요청/응답 필드 확인 | 두 API 모두 확인 |
| 계약 조회기간 7일 제한 | 공식 페이지 공지와 2026-11-10 DOCX 개정이력으로 확인 |
| 실제 서비스키 확인 | 시설과 계약 현황 모두 `true`; 계약은 전용 `JODAL`로 정상 인증 확인 |
| 인증된 정상 호출 및 실제 응답 확인 | 시설 JSON: 루트 `header/body`, 코드 문자열 `200`; 계약 현황 JSON: `response.header/body`, 코드 `00` |
| 미검증 operation·형식 | 계약 변경·삭제 JSON 및 두 서비스 전체 XML은 정상 호출 미검증 |
| 정상 실데이터 수집 성공 | 시설: 786건/8페이지 `complete`; 계약: 2024-01-01~07 등록일 조회, 현황 첫 100행 `partial` |
| 키 없는 오류 요청 | 두 API 모두 HTTP 401, `SERVICE_KEY_IS_NULL` 확인; 정상 수집과 별개 |
| 이전 키의 계약 요청 실패 | 시설용 키 사용 요청은 HTTP 403; 정확한 원인 미확정. 이후 계약 전용 `JODAL` 키의 현황 JSON 정상 수집 성공과 구분 |

실제 수집 manifest의 `schema_status`는 시설과 계약 모두 `live_success_verified`다. 계약의 이 표시는 확인한 현황 JSON에 한정하며 변경·삭제·XML까지 검증했다는 뜻이 아니다. 공식 명세 확인과 정상 응답 확인, 지역·연도 완전 수집, 비용 근거 검증을 서로 구분한다. 합성 테스트나 `--dry-run` 성공으로 실제 수집 상태를 바꾸지 않는다.

## 출처·경로·허용범위

| 구분 | 시설 명부 | 용역 계약 |
|---|---|---|
| 포털 식별자 | 15172490 | 15129427 |
| 설정 `source_id` | `DATA_GO_15172490` | `DATA_GO_15129427` |
| 제공기관 | 한국환경공단 | 조달청 |
| 공식 페이지 | [생활폐기물정보관리시스템 처리시설 정보](https://www.data.go.kr/data/15172490/openapi.do) | [나라장터 계약정보서비스](https://www.data.go.kr/data/15129427/openapi.do) |
| HTTPS base URL | `https://apis.data.go.kr/B552584/rwBzentyInfoService` | `https://apis.data.go.kr/1230000/ao/CntrctInfoService` |
| 기본 operation | `getList` | 아래 용역 현황·변경·삭제 세 operation |
| 형식 지정 파라미터 | `returnType` | `type` |
| 공개 형식 | JSON, XML | JSON, XML |
| 과거 연도 조회 | 명세에 연도·기간 필터 없음 | operation별 등록·변경·삭제일시 범위 조회 |
| 이용허락 | 포털 표시: 이용허락범위 제한 없음 | 포털 표시: 이용허락범위 제한 없음 |

공식 명세와 구현 설정은 `configs/public_data_apis.yaml`에 대응한다. 나라장터 전체 서비스는 물품·공사·외자·용역 및 별도 상세 operation도 제공하지만 현재 CLI의 기본 대상은 용역 세 operation이다. 이를 나라장터 모든 업무의 전수 계약자료로 표시하지 않는다. 시설 서비스의 `rwBzentyInfoService`는 공식 base URL이며, 임의로 시설 의미의 다른 서비스명으로 교체하지 않는다.

계약의 세 경로는 다음과 같이 확정됐다. 모두 REST `GET`이다.

| 종류 | operation | `inqryDiv=1`의 날짜 의미 |
|---|---|---|
| 현황 | `getCntrctInfoListServc` | 등록일시 |
| 변경 | `getCntrctInfoListServcChgHstry` | 변경일시 |
| 삭제 | `getCntrctInfoListServcDltHstry` | 삭제일시 |

[공식 계약 참고문서 2026-11-10판](https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000007761074&fileDetailSn=1)의 파일명은 `조달청_OpenAPI참고자료_나라장터_계약정보서비스_1.0_261110.docx`다. 개정이력은 전체 operation의 조회기간을 기존 1개월에서 7일로 변경했다. 문서 안에 남아 있는 과거 한 달 요청 예시는 최신 제한을 대체하지 않는다.

## 요청·페이징·연도

| 파라미터 | 시설 | 계약 |
|---|---|---|
| `serviceKey` | 필수 | 필수 |
| `pageNo` | 필수, 1부터 요청 | 필수, 1부터 요청 |
| `numOfRows` | 필수 | 필수 |
| `returnType` | 형식 선택; CLI가 명시 | 사용하지 않음 |
| `type` | 사용하지 않음 | 형식 선택; CLI가 명시 |
| `inqryDiv` | 없음 | 필수; 1=날짜 범위, 2=통합계약번호 |
| `inqryBgnDt`, `inqryEndDt` | 없음 | `YYYYMMDDHHMM`; `inqryDiv=1`일 때 조건부 필수 |
| `untyCntrctNo` | 없음 | `inqryDiv=2`일 때 조건부 필수 |

시설 Swagger는 `returnType`을 옵션으로 표시하면서 누락 오류 설명에도 언급하므로 구현은 형식을 명시한다. CLI 기본 페이지 크기 100과 구현의 1~1000 범위 검사는 구현 선택이며 공식 최대 허용값이 확인됐다는 뜻이 아니다. 공식 문서에서 최대 페이지 크기의 명시적 수치 한도는 확정하지 않았다.

계약 조회는 `inqryDiv=1`과 최대 7일의 달력 구간으로 분할한다. 일 단위 입력은 시작일 00:00부터 종료일 23:59까지의 분 단위 요청으로 만든다. 날짜 필터는 위 표의 operation별 사건일 기준이다. `--year 2024`는 2024년에 등록·변경·삭제된 기록의 조회 범위를 지정하며 2024년 체결 계약·2024년 서비스 실적을 완전하게 뜻하지 않는다.

시설에는 연도 필터가 없다. `--year 2024`를 함께 사용해도 2024년의 시설 명부를 복원하지 못한다. 요청연도는 `requested_reference_period` 등에 조회 의도로 남기고, 외부 근거 없이 `reference_period`를 2024년으로 확정하지 않는다. 수집일과 원자료의 기준연도도 구분한다.

응답의 `totalCount`, `pageNo`, `numOfRows`로 페이지 진행과 관측 행수를 확인한다. 전체 행수를 확인할 `totalCount`가 없거나 응답 구조가 다르면 성공한 빈 자료로 대체하지 않고 스키마 오류로 처리한다. 페이지 예산 소진이나 일부 operation 미실행은 전체 수집 완료가 아니다.

## 공개 응답 필드와 정규화

시설 item의 공식 필드는 아래 10개다. `bzentyNm`의 공식 항목명은 업체명이다.

| 원필드 | 정규화 필드 | 의미 |
|---|---|---|
| `bzentyId` | `business_id` | 업체아이디 |
| `bzentyNm` | `business_name` | 업체명 |
| `fcltTypeCd`, `fcltTypeNm` | `facility_type_code`, `facility_type_name` | 시설유형 코드·명 |
| `fcltSeCd`, `fcltSeNm` | `facility_category_code`, `facility_category_name` | 시설구분 코드·명 |
| `lctnCtpyCd`, `lctnCtpyNm` | `province_code`, `province_name` | 소재지 시도 코드·명 |
| `lctnSggCd`, `lctnSggNm` | `district_code`, `district_name` | 소재지 시군구 코드·명 |

공식 item에 별도 시설 ID·시설명·상세주소·용량·등록일 필드가 없어 정규화의 해당 확장 속성은 결측으로 둔다. 시도·시군구를 상세주소로 만들거나 업체 ID를 시설 ID로 단정하지 않는다. 추가 필드를 쓰려면 정확한 필드명과 검증 출처를 갖춘 명시적 매핑이 필요하다. 검토하지 않은 응답 필드는 정규화·보존 허용목록에 자동 추가하지 않는다.

계약 현황·변경의 주요 공개 필드는 다음과 같다.

| 원필드 | 의미·주의 |
|---|---|
| `untyCntrctNo` | 통합계약번호; 공식 계약현황 식별자 |
| `dcsnCntrctNo`, `cntrctRefNo` | 확정계약번호, 계약참조번호; 원문 문자열 보존 |
| `cntrctNm` | 용역 계약명 |
| `cntrctInsttCd`, `cntrctInsttNm` | 계약기관 코드·명; 실제 서비스 지역의 증거와 구분 |
| `bsnsDivNm`, `lngtrmCtnuDivNm` | 업무구분명, 장기계속구분명 |
| `cntrctCnclsDate` | 계약체결일자 |
| `cntrctPrd` | 계약기간 자유문자열; 임의 연간화 금지 |
| `totCntrctAmt`, `thtmCntrctAmt` | 장기계속 총계약금액, 금차계약금액; 서로 합산하지 않음 |
| `rgstDt`, `chgDt` | 등록일시, 변경일시 |
| `wbgnDate`, `thtmScmpltDate`, `ttalScmpltDate` | 착수일자, 금차완수일자, 총완수일자 |

삭제 item은 `dcsnCntrctNo`, `cntrctRefNo`, `dltDt`, `chgDivNm`, `untyCntrctNo`, `rgstDt`, `chgDt`다. `chgDivNm=DEL`은 삭제를 뜻한다. 별도 변경차수 필드는 공개 schema에 없다. 번호 정의에 수정차수가 포함돼 있더라도 과거 번호체계가 다양해 접미부에서 차수를 추정하지 않는다.

계약 병합은 출처·통합계약번호를 기준으로 동일 관측을 중복 제거하고 버전 이력을 보존한다. 등록·변경·삭제일시로 순서를 확인하며 수집일을 변경일로 대신하지 않는다. 삭제·충돌·순서 미확인 시 대표 금액을 비우고 수동 검토로 넘긴다. 최신 관측 버전의 대표 금액도 계약 생애 전체 지출 합계가 아니다.

## envelope·결과코드·미검증 항목

공식 Swagger의 성공 schema는 `header`와 `body`를 가지며 XML 루트 이름은 `response`다. 계약 DOCX의 정상 예시는 XML `response/header`, `response/body/items/item`와 `numOfRows`, `pageNo`, `totalCount`를 제시한다. 시설의 실제 정상 JSON은 루트 `header/body`를 사용하는 것으로 확인했다. 계약 현황의 실제 정상 JSON은 `response.header/body`로 확인했다. 계약 변경·삭제 및 각 API의 모든 item 개수별 표현은 아직 확인하지 않았다.

클라이언트는 JSON의 `response.header/body`와 루트 `header/body` 두 형태를 명시적으로 지원하며 XML도 처리한다. item의 단일 객체·목록·명시적 빈 응답을 처리하되 정상 결과코드와 페이지 메타데이터를 확인한다. 시설의 루트 `header/body`와 계약 현황의 `response.header/body`는 실제 관측했고, 다른 operation·표현·XML은 지원하는 파서의 범위다. 두 API에서 모든 형태가 실제 관측됐다는 주장이 아니다.

| 응답 | 확인·처리 범위 |
|---|---|
| 계약 `resultCode=00` | 공식 DOCX 및 실제 용역 현황 JSON 정상 응답에서 확인 |
| 계약 `03` | 공식 No Data; 명시적 빈 조회로 처리 |
| 계약 `02`, `05` | DB·서비스 시간초과 등 제공기관 오류 |
| 계약 `06`, `07`, `08` | 날짜 형식·입력범위 초과·필수값 오류 |
| 계약 `10`, `11` | 가이드상 키 파라미터·필수 요청 파라미터 누락 |
| 시설 `91`, `93`, `unknown` | Swagger에 잘못된 파라미터·필수값·`pageNo`/`returnType` 누락 오류 설명 존재 |
| 시설 `resultCode=200` | 2026-11-16 실제 JSON 정상 응답과 보존 snapshot의 메타데이터에서 확인 |
| 시설 설정의 `200` | 실제 확인한 정상 코드만 허용; 계약의 `00`과 구분 |

키 없이 만든 오류 확인용 요청에서는 두 API 모두 HTTP 401과 JSON `OpenAPI_ServiceResponse.cmmMsgHeader`를 반환했다. `errMsg=SERVICE_KEY_IS_NULL`, `returnReasonCode=20`이며 가이드의 서비스별 정상 `header/body`와 별도 gateway envelope다. 이 관측은 서비스키·활용승인·정상 schema·관측 행수를 검증하지 않는다. 오류 원문이나 키가 포함된 전체 요청 URL을 결과 자료로 출력하지 않는다.

시설의 최종 실제 근거는 실행 `20261115T223446-c71433c0`의 [수집 manifest](../data/raw/public_data/facilities/20261115T223446-c71433c0/manifest.json), [정규화 JSON](../data/processed/public_data/facilities/20261115T223446-c71433c0/records.json), [전체 조회 완료 포인터](../data/processed/public_data/facilities/latest_complete.json)다. UTC 수집시각 2026-11-15 22:34:46~22:34:48은 한국시간 2026-11-16이다. `authentication_success=true`, `schema_status=live_success_verified`, `status=complete`, `record_count=786`, `complete=true`를 확인했다. 8개 snapshot의 저장 파일 SHA-256이 manifest와 모두 일치하고 정규화 행수도 786건이다. 이는 수집 시점 API 명부의 전체 조회이며 2024년 등 과거 연도 명부 복원이나 별도 시설 786개의 확정을 뜻하지 않는다. 시설 인증과 계약 인증은 별도로 확인한다.
계약의 실제 정상 근거는 실행 `20261115T223854-3d8afb71`의 [수집 manifest](../data/raw/public_data/contracts/20261115T223854-3d8afb71/manifest.json), [정규화 JSON](../data/processed/public_data/contracts/20261115T223854-3d8afb71/records.json), [비용 후보 JSON](../data/processed/public_data/contracts/20261115T223854-3d8afb71/cost_candidates.json)이다. 조회조건은 `getCntrctInfoListServc`, `inqryDiv=1`, 2024-01-01 00:00~2024-01-07 23:59, JSON, 첫 페이지 100행이다. 현황 응답 `totalCount=12511` 중 100행을 보존했고 `authentication_success=true`, `schema_status=live_success_verified`, `status=partial`, `complete=false`, `candidate_count=100`이다. 이 100행은 일반 용역 현황의 첫 페이지이며 폐기물 관련 계약 100건을 확보했다는 뜻이 아니다. 변경·삭제 operation은 이 실행에서 실제 수집되지 않았다. snapshot 해시와 정규화 100행을 확인했으며 후보 100개는 모두 `candidate`, `computed_krw_per_t=None`이다.

이전 실행 `20261115T223538-bd587e2e`의 [실패 manifest](../data/raw/public_data/contracts/20261115T223538-bd587e2e/manifest.json)는 시설용 키로 계약 요청을 시도해 HTTP 403 접근 실패가 발생한 이력이다. 정확한 거부 원인은 확정하지 않았다. 당시에는 활용신청·승인과 서비스별 키 권한 확인이 필요했고, 이후 별도 `JODAL` 키로 위 현황 JSON 정상 응답을 확인했다. 이전 403을 현재 전용 키의 실패 상태로 표시하거나 변경·삭제까지 접근이 확인됐다고 확대하지 않는다.
## 인증과 실행

공공데이터포털에서 각 서비스를 활용신청하고 승인 상태를 확인한 뒤 발급된 키를 프로젝트 `.env`의 아래 이름 또는 같은 환경변수에 설정한다. 키 값은 공개 설정 YAML·명령행 인자·로그·문서·Git에 넣지 않는다. 기존 KOSIS 인증과 별도 설정이다. 아래는 변수명과 자리표시자만 보여 주며 실제 키 값은 포함하지 않는다.

```dotenv
DATA_GO_KR_SERVICE_KEY=시설_API에_승인된_서비스키_값
JODAL=나라장터_계약_API에_승인된_서비스키_값
```

시설은 `DATA_GO_KR_SERVICE_KEY`를 읽는다. 계약은 `JODAL`을 먼저 읽고, 사용할 수 있는 `JODAL` 설정을 읽지 못하면 공통 `DATA_GO_KR_SERVICE_KEY`로 대체한다. 각 변수는 환경변수 값을 프로젝트 `.env`보다 우선한다. HTTP 403 등 서버 인증 실패 시 다른 키로 자동 재시도하는 동작은 없다. `all`도 데이터셋마다 키를 선택하므로 두 키를 각각 설정할 수 있다. 공통 키 사용 가능 여부는 해당 서비스의 활용신청·승인에 따라 확인해야 한다.

아래 명령은 현재 구현을 사용하는 예시이며 공식 API의 정상 응답 예시나 실제 수집 성공 기록이 아니다. 프로젝트 루트에서 실행한다.

```powershell
python scripts/collect_public_data.py --dataset all --year 2024 --dry-run
python scripts/collect_public_data.py --dataset facilities --year 2024 --limit-pages 1 --page-size 100
python scripts/collect_public_data.py --dataset contracts --begin 2024-01-01 --end 2024-01-07 --limit-pages 1 --page-size 100 --format json --operation getCntrctInfoListServc
```

| CLI 옵션 | 의미 |
|---|---|
| `--dataset facilities\|contracts\|all` | 시설·용역 계약·둘 다 선택 |
| `--year 2024` | 계약 사건일 조회의 연도 범위; 시설은 요청연도 기록만 남김 |
| `--begin YYYY-MM-DD --end YYYY-MM-DD` | 연도 대신 명시적 날짜 범위 지정 |
| `--limit-pages 1` | 기본값 1. 전체 데이터셋·기간·operation에 걸쳐 보존할 페이지 예산. HTTP 재시도 횟수는 별도이며 연결 시도 총횟수의 상한이 아님 |
| `--page-size 100` | 기본 요청 페이지 크기 |
| `--dry-run` | 키 없이 계획만 표시. HTTP 호출·파일 저장 없음. 실제 수집으로 표시하지 않음 |
| `--format json\|xml` | 요청 형식 선택; 결과 보존 snapshot은 별도 JSON 구조 |
| `--output-root PATH` | 출력 기준 루트; 기본값은 프로젝트 루트 |
| `--operation NAME` | 정확한 operation 선택; 반복 가능. 생략하면 데이터셋의 기본 operation 모두 선택 |
| `--region TEXT` | 수집 후 로컬 문자열 검색. 시설은 시도·시군구, 계약은 계약명·기관명이며 계약의 서비스 지역을 확정하지 않음 |

`--year`와 `--begin/--end`는 함께 사용할 수 없고 시작일·종료일은 둘 다 지정해야 한다. 계약 수집에는 날짜 범위가 필요하다. 전체 연도·세 operation을 선택해도 기본 예산 1로 전수 수집되지 않는다. `--dataset all`은 시설부터 실행하므로 기본 예산 1을 시설에서 소진하면 계약은 `not_started`와 `global_page_budget_exhausted` 사유로 표시된다. 7일 구간 분할과 페이지 진행, 실행 예산, 수집 완료 여부를 함께 확인한 뒤 필요한 예산을 명시한다. 키가 없으면 실제 호출은 인증 설정 안내로 종료하며, 키 없는 상태를 정상 0건으로 기록하지 않는다. `--dry-run`의 계획 확인과 실제 수집을 구분한다.

## 산출물과 재처리

`--output-root`를 지정하지 않으면 아래 경로는 프로젝트 루트 기준이다. 실행마다 고유 `run_id`를 사용하며 같은 실행 경로를 덮어쓰지 않는다.

| 경로 | 내용 |
|---|---|
| `data/raw/public_data/<dataset>/<run_id>/manifest.json` | 출처·요청범위·페이지·해시·상태를 기록한 수집 manifest |
| 같은 디렉터리의 `page-00001.redacted.json` 등 | 공개 필드 허용목록을 적용한 페이지 snapshot; 원문 전체 응답 아님 |
| `data/processed/public_data/<dataset>/<run_id>/records.json`, `records.csv` | 정규화 결과; CSV는 UTF-8 BOM 사용 |
| 계약 디렉터리의 `cost_candidates.json`, `cost_candidates.csv` | 처리량·포함비용 미확인 상태를 보존한 비용 후보; 계산된 단가가 자동 생기지 않음 |
| 정규화 디렉터리의 `manifest.json` | 해당 산출물의 수집 manifest |
| `data/processed/public_data/<dataset>/latest_sample.json` | 마지막 부분 수집(`partial`)의 manifest |
| `data/processed/public_data/<dataset>/latest_complete.json` | 모든 계획 구간·페이지를 마친 수집(`complete`)의 manifest |

manifest의 `query_count`, `completed_queries`, `limit_pages`, `pages`, `record_count`, `unfiltered_record_count`, `candidate_count`, `status`, `complete`, `authentication_success`, `schema_status`를 함께 읽는다. `complete=true`는 그 실행에서 계획한 API 조회가 끝났다는 뜻이며 국가 전체 과거 계약의 완전성·서비스 지역의 정확성·비용 근거 검증을 뜻하지 않는다. `partial`을 전체 연도 집계로 사용하지 않는다. `all`에서 예산 때문에 시작하지 못한 데이터셋은 CLI 보고에 남고 해당 데이터셋의 성공 manifest는 생성되지 않는다.

정상 API 응답을 해석한 실제 실행은 `authentication_success=true`, `schema_status=live_success_verified`를 기록할 수 있다. 이 상태에도 `complete=false`일 수 있다. 합성 실행은 `synthetic_fixture_verified`로 구분한다. 실패는 `status=failed`, `complete=false`, `failure_stage`, `error_type`으로 기록하며 정상·부분수집 포인터를 갱신하지 않는다. 인증값·서버 오류 원문·키가 붙은 URL·예외 원문은 manifest에 저장하지 않는다.

각 페이지에는 `original_response_sha256`과 `snapshot_sha256`이 별도로 있다. 앞 해시는 저장하지 않은 원문 응답 바이트의 식별용이고 뒤 해시는 실제 `.redacted.json` 파일의 무결성 검증용이다. 원문 바이트를 보존하지 않으므로 원문 해시만으로 원문 전체를 재현하거나 검증했다고 주장하지 않는다.

저장한 공개 snapshot의 정규화는 키·네트워크 없이 다음과 같이 재현할 수 있다. 아래 경로의 `<dataset>`와 `<run_id>`는 실제 실행 값으로 바꾼다.

```powershell
python scripts/prepare_public_data.py data/raw/public_data/<dataset>/<run_id>/manifest.json
```

재처리는 `partial` 또는 `complete` manifest의 snapshot 해시·파일명을 검증하고 새 `<run_id>-reprepared-...` 정규화 디렉터리를 만든다. 실패 manifest나 변조된 snapshot을 성공 자료로 재처리하지 않으며, 재처리만으로 실제 수집 범위를 늘리거나 비용 후보를 승인하지 않는다. CSV만으로 생략된 근거 객체를 복원하지 않고 JSON과 manifest를 함께 보존한다.

## 보존·재현과 비용 적용 경계

보존본은 **개인정보와 인증정보를 제외한 redacted snapshot**이다. 원문 응답 전체를 그대로 공개하는 raw dump가 아니다. 허용된 공개 필드와 페이지 메타데이터, 제외한 필드명으로 보존 범위를 확인한다. 원문 응답 바이트의 SHA-256을 기록하더라도 redacted 파일의 해시와 서로 다른 대상임을 구분한다.

계약의 담당자명·전화·팩스와 `corpList`, `dminsttList`, `dmndInsttList` 같은 묶음 문자열은 제외한다. 이 문자열은 공개 schema에서 수요기관·업체 목록으로 불리지만 담당자·대표자·연락처를 함께 담을 수 있어 단순히 전체를 보존하지 않는다. 미검토 필드와 중첩 객체·목록도 허용목록 밖이면 보존하지 않는다. 원문 스키마에 존재하는 것과 공개 snapshot에 남기는 것은 다르다.

수집 메타데이터에서는 출처 URL·operation, 비밀정보를 뺀 요청조건·조회구간·수집시각, 응답 형식·결과코드·행수·페이지 진행 및 해시·완료 상태를 대조한다. 전체 요청 URL의 서비스키, 실제키 유무를 추정할 비밀 값, 담당자 개인정보를 기록하지 않는다. 정규화 자료에는 출처·수집일·요청 기준기간과 검증 여부·실제 또는 합성 데이터 구분을 보존한다. 테스트 fixture는 `synthetic`으로 구분하고 실제 관측치 집계에서 제외한다.

수집 API는 처리단가 API가 아니다. 계약금액과 같은 기간·지역·대상 폐기물·처리 단계의 실적 톤수 및 포함비용을 대조하기 전에는 원/톤을 산출하지 않는다. `candidate → proxy → validated`의 근거 검토, 이전지출·중복 비용의 배제와 수동 적용 경계는 [비용 경계](cost_boundary.md)를 따른다. 수집 결과와 비용 후보를 기존 모형 단가·정책 입력에 자동 반영하지 않는다.
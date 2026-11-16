"""OECD 출처 문서 보존. 검증하지 않은 SDMX 주소나 숫자는 만들지 않는다."""
from .common import fetch,save_records
PAGE="https://www.oecd.org/en/publications/2022/02/global-plastics-outlook_a653d1c9/full-report/component-7.html"

def collect(*,root,year=2019):
    raw,meta=fetch("oecd",PAGE,"global_plastics_outlook_flows.html",root=root,
        license="OECD publication reuse conditions; attribution; third-party material may differ",
        redistribution="check_source_publication_terms")
    # A report is not a validated SDMX table. The catalog exposes this gap.
    return save_records([],dict(meta,unavailable_reason="플라스틱 흐름 모형 추정치의 구조화 테이블·SDMX 식별자 미검증"),root=root)

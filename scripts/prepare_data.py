"""수동 전사한 공식 원표를 검증하고 단위 변환한다. 외부 접속은 하지 않는다."""
import csv
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://www.guroc.go.kr/kr/bbs/download.do?bbs_id=memnotice&uid=10C5C2B6918247C7947B3A54914B8714"

def main():
    raw = ROOT / "data/raw/guro_table_5_6.csv"
    with raw.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    converted = []
    for source in rows:
        row = {key: int(value) for key, value in source.items()}
        if row["handled_t"] != row["residue_t"] + row["sorted_t"]:
            raise ValueError("원표 물질수지 불일치")
        if row["total_budget_thousand_krw"] != row["collection_budget_thousand_krw"] + row["sorting_budget_thousand_krw"]:
            raise ValueError("원표 예산 합계 불일치")
        record = {key: row[key] for key in ("reference_year", "handled_t", "residue_t", "sorted_t")}
        for part in ("total", "collection", "sorting"):
            record[f"{part}_budget_krw"] = row[f"{part}_budget_thousand_krw"] * 1000
        record.update(source_url=SOURCE, source_title="구로구 생활폐기물 재활용 활성화 정책 연구",
                      retrieved_at="2026-11-15", geography="서울특별시 구로구",
                      waste_scope="보고서의 재활용 수거·선별 행정처리 흐름(원표명: 발생량)",
                      unit="수량 t/년; 예산 원/년", evidence_grade="B",
                      source_locator="PDF 71~72쪽(0부터 70~71), 인쇄 57~58쪽 표5·6")
        converted.append(record)
    target = ROOT / "data/processed/guro_recycling.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(converted[0]))
        writer.writeheader(); writer.writerows(converted)
    manifest = ROOT / "data/raw/transcription_manifest.csv"
    with manifest.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["file", "sha256", "note"])
        writer.writeheader()
        for filename in ("guro_table_5_6.csv", "minimum_wage.csv"):
            path = ROOT / "data/raw" / filename
            writer.writerow(dict(file=filename, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                 note="공식 원표의 수동 전사본이며 원문 PDF/HTML 자체의 해시가 아님"))
    print("공식 원표 전사값 검증 및 천원→원 변환 완료")

if __name__ == "__main__":
    main()

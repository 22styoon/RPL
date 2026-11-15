"""KOSIS 공개 지표 차트의 실제 전국 시계열. 인증 OpenAPI와 구분한다."""
import json
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError
import pandas as pd
from src.model import ROOT
from src.kosis import KosisError

SOURCE = "https://kosis.kr/visual/nsportalStats/detailContents.do?listId=C&statJipyoId=3664&vStatJipyoId=5061"
ENDPOINT = "https://kosis.kr/visual/nsportalStats/selectDetailJipyoInfo.do"
PARAMETERS = dict(listId="C", vStatJipyoId="5061", statJipyoId="3664", relation="")

def prepare_public_summary(raw, retrieved_at):
    try:
        records = json.loads(raw.decode("utf-8-sig"))["detailIxValList"]
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise KosisError("KOSIS 공개 지표 응답 형식이 변경되었습니다.") from None
    if not isinstance(records, list) or not records:
        raise KosisError("KOSIS 공개 지표가 비어 있습니다.")
    rows = []
    for record in records:
        if str(record.get("V_STAT_JIPYO_ID")) != "5061" or record.get("ITM_NM") != "전국":
            raise KosisError("예상한 생활폐기물 전국 지표가 아닙니다.")
        try:
            year, value = int(record["PRD_DE"]), int(record["VAL"])
        except (KeyError, ValueError, TypeError):
            raise KosisError("공개 지표의 연도·수치가 올바르지 않습니다.") from None
        if value < 0:
            raise KosisError("폐기물 발생량은 음수일 수 없습니다.")
        rows.append(dict(reference_year=year, value=value, unit="톤/년", geography="전국",
                         source_title="KOSIS 100대지표 생활폐기물 발생량",
                         source_url=SOURCE, retrieved_at=retrieved_at, evidence_grade="A",
                         waste_scope="전국 생활폐기물; 사업장비배출을 포함한 생활계 전체와 구별",
                         collection_method="KOSIS 공개 지표 차트 응답; 인증 OpenAPI 조회 아님",
                         table_id="DT_106N_29_2020005"))
    frame = pd.DataFrame(rows).sort_values("reference_year")
    if frame.reference_year.duplicated().any():
        raise KosisError("공개 지표에 중복 시점이 있습니다.")
    return frame

def save_public_summary(raw, root=ROOT):
    stamp = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    frame = prepare_public_summary(raw, stamp)
    raw_dir = Path(root)/"data/raw/kosis"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir/"public_waste_summary.json").write_bytes(raw)
    target = Path(root)/"data/processed/kosis_public_waste.csv"
    frame.to_csv(target, index=False, encoding="utf-8-sig")
    manifest = dict(source_url=SOURCE, endpoint=ENDPOINT, parameters=PARAMETERS,
                    unit="톤/년(출처 화면에서 확인)", method="공개 차트 POST; 인증키 미사용",
                    retrieved_at=stamp, rows=len(frame), sha256=hashlib.sha256(raw).hexdigest())
    (raw_dir/"public_waste_summary_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return frame

def collect_public_summary(root=ROOT):
    request = Request(ENDPOINT, data=urlencode(PARAMETERS).encode("ascii"), headers={"Content-Type":"application/x-www-form-urlencoded"}, method="POST")
    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read()
    except (URLError, OSError, TimeoutError):
        raise KosisError("KOSIS 공개 지표에 연결하지 못했습니다.") from None
    return save_public_summary(raw, root)

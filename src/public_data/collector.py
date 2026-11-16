"""공식 API의 제한된 페이지 수집과 재현 가능한 검토 자료 저장."""
from datetime import date, datetime, timedelta, timezone
import csv
import hashlib
import io
import json
from pathlib import Path
import re
from uuid import uuid4
import yaml

from src.model import ROOT
from src.cost_candidate import create_cost_candidate
from src.evidence_validation import CSV_FIELDS
from .client import PublicDataError, ResponseSchemaError, public_snapshot, safe_parameters
from .facilities import normalize_facilities
from .contracts import normalize_contracts, merge_contract_versions


class CollectionFailure(PublicDataError):
    def __init__(self, manifest_path, manifest):
        super().__init__("수집에 실패했습니다. 인증정보 없는 manifest에서 실패 단계를 확인하세요: "+str(manifest_path))
        self.manifest_path = manifest_path
        self.manifest = manifest


def load_specs():
    return yaml.safe_load((ROOT/"configs/public_data_apis.yaml").read_text(encoding="utf-8"))["datasets"]


def date_windows(begin, end):
    if not isinstance(begin,date) or not isinstance(end,date) or begin > end:
        raise ValueError("시작일과 종료일을 올바르게 입력하세요.")
    windows = []
    cursor = begin
    while cursor <= end:
        last = min(cursor+timedelta(days=6),end)
        windows.append((cursor,last))
        if last == end:
            break
        cursor = last+timedelta(days=1)
    return windows


def build_queries(dataset, begin=None, end=None, page_size=100, response_format="json", operations=None, specs=None):
    specs = load_specs() if specs is None else specs
    if dataset not in specs:
        raise ValueError("지원 데이터셋: facilities, contracts")
    if isinstance(page_size,bool) or not isinstance(page_size,int) or not 1 <= page_size <= 1000:
        raise ValueError("page_size는 1~1000 정수입니다.")
    if response_format not in ("json","xml"):
        raise ValueError("응답 형식은 json 또는 xml입니다.")
    spec = specs[dataset]
    selected = spec["operations"] if operations is None else list(operations)
    if not selected or len(selected) != len(set(selected)) or not set(selected) <= set(spec["operations"]):
        raise ValueError("명세에 등록된 중복 없는 operation 목록이 필요합니다.")
    if (begin is None) != (end is None):
        raise ValueError("시작일과 종료일을 함께 입력하세요.")
    if begin is not None:
        date_windows(begin,end)
    windows = date_windows(begin,end) if dataset == "contracts" else [(None,None)]
    result = []
    for operation in selected:
        for first,last in windows:
            params = {"pageNo":1,"numOfRows":page_size,spec["response_format_parameter"]:response_format}
            period = None
            if dataset == "contracts":
                params.update(inqryDiv=1,inqryBgnDt=first.strftime("%Y%m%d")+"0000",inqryEndDt=last.strftime("%Y%m%d")+"2359")
                period = first.isoformat()+"/"+last.isoformat()
            result.append({"endpoint":spec["base_url"].rstrip("/")+"/"+operation,
                           "parameters":safe_parameters(params),"operation":operation,"query_period":period})
    return result


def _dump(value):
    return json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+"\n"


def _atomic_text(path, text, encoding="utf-8"):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_name(path.name+".tmp-"+uuid4().hex)
    temporary.write_bytes(text.encode(encoding))
    temporary.replace(path)


def _csv_text(rows, fields=None):
    fields = list(fields or sorted({key for row in rows for key in row}))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream,fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(row.get(key),ensure_ascii=False,sort_keys=True) if isinstance(row.get(key),(dict,list)) else row.get(key) for key in fields})
    return stream.getvalue()


def _prepare(pages, dataset, manifest, region=None):
    records = []
    for entry,snapshot in pages:
        context = {"source_id":manifest["source_id"],"source_url":manifest["source_url"],
                   "retrieved_at":entry["retrieved_at"],"reference_period":manifest["requested_period"],
                   "reference_period_verified":False,"data_kind":manifest["data_kind"],
                   "operation":entry["operation"],"region":None}
        normalizer = normalize_facilities if dataset == "facilities" else normalize_contracts
        records.extend(normalizer(snapshot["items"],context))
    if dataset == "contracts":
        records = merge_contract_versions(records)
    else:
        # Registry IDs can identify businesses with several facility types.
        # Deduplicate exact observations only, never merge on business_id alone.
        unique = {}
        for row in records:
            unique[json.dumps(row,sort_keys=True,ensure_ascii=False)] = row
        records = list(unique.values())
    before_filter = len(records)
    if region:
        fields = ("province_name","district_name") if dataset == "facilities" else ("title","contract_agency_name")
        records = [row for row in records if any(region in str(row.get(field) or "") for field in fields)]
    candidates = []
    if dataset == "contracts":
        for row in records:
            candidate = create_cost_candidate(row)
            candidate["data_kind"] = manifest["data_kind"]
            candidate["unified_contract_id"] = row.get("unified_contract_id")
            candidates.append(candidate)
    return records,candidates,before_filter


def _save_prepared(records,candidates,directory,dataset):
    _atomic_text(directory/"records.json",_dump(records))
    _atomic_text(directory/"records.csv",_csv_text(records),encoding="utf-8-sig")
    if dataset == "contracts":
        _atomic_text(directory/"cost_candidates.json",_dump(candidates))
        _atomic_text(directory/"cost_candidates.csv",_csv_text(candidates,CSV_FIELDS),encoding="utf-8-sig")


def collect_dataset(dataset, *, client, begin=None, end=None, limit_pages=1, page_size=100,
                    response_format="json", region=None, output_root=ROOT, run_id=None,
                    data_kind="live", operations=None):
    """limit_pages는 모든 기간·operation을 통틀어 허용하는 실제 페이지 수이다."""
    if isinstance(limit_pages,bool) or not isinstance(limit_pages,int) or limit_pages < 1:
        raise ValueError("limit_pages는 1 이상 정수입니다.")
    if data_kind not in ("live","synthetic"):
        raise ValueError("data_kind는 live 또는 synthetic입니다.")
    if region is not None and (not isinstance(region,str) or not region.strip()):
        raise ValueError("지역 검색어는 빈 문자열일 수 없습니다.")
    queries = build_queries(dataset,begin,end,page_size,response_format,operations)
    spec = load_specs()[dataset]
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")+"-"+uuid4().hex[:8]
    if not re.fullmatch(r"[A-Za-z0-9_-]+",run_id):
        raise ValueError("run_id에는 영문·숫자·밑줄·하이픈만 사용할 수 있습니다.")
    root = Path(output_root).resolve()
    raw_directory = root/"data/raw/public_data"/dataset/run_id
    if raw_directory.exists():
        raise ValueError("기존 수집 실행은 덮어쓰지 않습니다.")
    raw_directory.mkdir(parents=True)
    manifest_path = raw_directory/"manifest.json"
    normalized = root/"data/processed/public_data"/dataset/run_id
    manifest = {"schema_version":"1.0","dataset":dataset,"source_id":spec["source_id"],
        "source_url":spec["source_url"],"license":spec["license"],"run_id":run_id,
        "data_kind":data_kind,"status":"collecting","complete":False,
        "requested_period":None if begin is None else begin.isoformat()+"/"+end.isoformat(),
        "reference_period":None,"date_filter":spec.get("date_filter"),
        "region_filter":region,"region_filter_basis":"registry_administrative_area" if dataset=="facilities" else "title_or_agency_text_only",
        "schema_status":spec["schema_status"],"authentication_success":False,
        "query_count":len(queries),"completed_queries":0,"limit_pages":limit_pages,
        "pages":[],"record_count":0,"raw_directory":str(raw_directory),
        "normalized_path":None,"started_at":datetime.now(timezone.utc).isoformat(),
        "response_retention":"public_fields_only_redacted_snapshot_original_bytes_not_saved"}
    _atomic_text(manifest_path,_dump(manifest))
    saved = []
    stage = "request"
    try:
        for query in queries:
            page_no,total,seen = 1,None,set()
            fetched_rows = 0
            while len(saved) < limit_pages:
                parameters = dict(query["parameters"],pageNo=page_no)
                stage = "request"
                page,raw = client.fetch(query["endpoint"],parameters,
                    success_codes=spec["success_codes"],no_data_codes=spec.get("no_data_codes",()))
                manifest["authentication_success"] = data_kind == "live"
                stage = "pagination"
                if total is not None and page.total_count != total:
                    raise ResponseSchemaError("수집 중 totalCount가 바뀌었습니다. 재수집이 필요합니다.")
                total = page.total_count
                if page.page_no != page_no or page.page_size != page_size or (total > 0 and not page.items):
                    raise ResponseSchemaError("요청 페이지와 응답/총량이 맞지 않습니다.")
                snapshot = public_snapshot(page,dataset,client.key)
                digest = hashlib.sha256(json.dumps(snapshot["items"],ensure_ascii=False,sort_keys=True).encode("utf-8")).hexdigest()
                if snapshot["items"] and digest in seen:
                    raise ResponseSchemaError("동일 응답 페이지가 반복되어 수집을 중단했습니다.")
                seen.add(digest)
                payload = _dump(snapshot)
                filename = "page-"+str(len(saved)+1).zfill(5)+".redacted.json"
                entry = {"file":filename,"operation":query["operation"],"endpoint":query["endpoint"],
                    "parameters":parameters,"query_period":query["query_period"],
                    "retrieved_at":datetime.now(timezone.utc).isoformat(),
                    "original_response_sha256":hashlib.sha256(raw).hexdigest(),
                    "snapshot_sha256":hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                    "row_count":len(snapshot["items"]),"total_count":total}
                _atomic_text(raw_directory/filename,payload)
                saved.append((entry,snapshot))
                manifest["pages"].append(entry)
                fetched_rows += len(snapshot["items"])
                expected = min(page_size,max(total-(page_no-1)*page_size,0))
                if len(page.items) != expected:
                    raise ResponseSchemaError("페이지 행수가 총량과 일치하지 않습니다.")
                if fetched_rows >= total:
                    manifest["completed_queries"] += 1
                    break
                page_no += 1
            if len(saved) >= limit_pages:
                break
        stage = "normalization"
        records,candidates,before_filter = _prepare(saved,dataset,manifest,region)
        manifest.update(complete=manifest["completed_queries"]==len(queries),
                        record_count=len(records),unfiltered_record_count=before_filter,
                        candidate_count=len(candidates),normalized_path=str(normalized))
        manifest["status"] = "complete" if manifest["complete"] else "partial"
        manifest["schema_status"] = "live_success_verified" if data_kind=="live" else "synthetic_fixture_verified"
        stage = "save"
        _save_prepared(records,candidates,normalized,dataset)
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_text(manifest_path,_dump(manifest))
        _atomic_text(normalized/"manifest.json",_dump(manifest))
        pointer = normalized.parent/("latest_complete.json" if manifest["complete"] else "latest_sample.json")
        _atomic_text(pointer,_dump(manifest))
        return manifest
    except (PublicDataError,ValueError,TypeError,KeyError,OSError) as error:
        manifest.update(status="failed",complete=False,failure_stage=stage,
                        error_type=type(error).__name__,normalized_path=None,
                        finished_at=datetime.now(timezone.utc).isoformat())
        # Server messages, URLs with keys, raw response bytes and exception text are not persisted.
        _atomic_text(manifest_path,_dump(manifest))
        raise CollectionFailure(manifest_path,manifest) from None


def prepare_saved_run(manifest_path, *, output_root=ROOT):
    """저장한 공개 응답으로 정규화를 재현한다. 네트워크와 인증키는 필요 없다."""
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") not in ("partial","complete"):
        raise ValueError("성공 또는 부분 성공한 manifest가 필요합니다.")
    if manifest.get("dataset") not in load_specs() or not re.fullmatch(r"[A-Za-z0-9_-]+",str(manifest.get("run_id",""))):
        raise ValueError("저장 manifest의 데이터셋 또는 실행 ID가 올바르지 않습니다.")
    pages = []
    for entry in manifest["pages"]:
        filename = entry["file"]
        if Path(filename).name != filename or not filename.endswith(".redacted.json"):
            raise ValueError("저장 페이지 경로가 올바르지 않습니다.")
        payload = (manifest_path.parent/filename).read_bytes()
        if hashlib.sha256(payload).hexdigest() != entry["snapshot_sha256"]:
            raise ValueError("저장 응답의 해시가 일치하지 않습니다.")
        snapshot = json.loads(payload.decode("utf-8"))
        if snapshot.get("schema") != "privacy-redacted-api-snapshot-v1":
            raise ValueError("저장 응답의 형식이 일치하지 않습니다.")
        pages.append((entry,snapshot))
    records,candidates,_ = _prepare(pages,manifest["dataset"],manifest,manifest.get("region_filter"))
    directory = Path(output_root)/"data/processed/public_data"/manifest["dataset"]/(manifest["run_id"]+"-reprepared-"+uuid4().hex[:8])
    _save_prepared(records,candidates,directory,manifest["dataset"])
    _atomic_text(directory/"manifest.json",_dump(dict(manifest,reprepared_from=str(manifest_path),normalized_path=str(directory))))
    return directory

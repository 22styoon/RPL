"""공식 공개 자료의 보존·해시·메타데이터."""
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import os
import ssl
import subprocess
from urllib.error import URLError
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
import pandas as pd
from src.model import ROOT

HOSTS={"ec.europa.eu","environment.data.gov.uk","www.data.gov.uk","www.nea.gov.sg","www.epa.gov","www.oecd.org"}
MAX_BYTES=100_000_000

class ExternalDataError(ValueError):
    pass

def check_url(url):
    parts=urlsplit(url)
    if parts.scheme!="https" or parts.hostname not in HOSTS or parts.username or parts.password:
        raise ExternalDataError("등록한 공식 HTTPS 출처만 수집할 수 있습니다.")
    if any(word in parts.query.lower() for word in ("servicekey=","apikey=","token=")):
        raise ExternalDataError("공개 자료 보존 URL에 인증키를 넣지 않습니다.")

class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        check_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(source_id,url,filename,*,root=ROOT,license="별도 확인",redistribution="check_source"):
    check_url(url)
    if Path(filename).name!=filename or not source_id.replace("_","").isalnum():
        raise ExternalDataError("잘못된 보존 경로입니다.")
    request=Request(url,headers={"User-Agent":"RPL-Statistics/1.0 (academic data analysis)"})
    try:
        with build_opener(OfficialRedirect()).open(request,timeout=40) as response:
            raw=response.read(MAX_BYTES+1)
    except URLError as error:
        if os.name=="nt" and isinstance(error.reason,ssl.SSLCertVerificationError):
            # Windows Schannel completes trusted certificate chains using the OS store.
            # TLS verification stays enabled; do not use -k/--insecure.
            result=subprocess.run(["curl.exe","--fail","--silent","--show-error","--max-time","40","--max-filesize",str(MAX_BYTES),url],
                                  capture_output=True,timeout=45)
            if result.returncode:
                raise ExternalDataError("Windows 인증서 저장소를 이용한 다운로드도 실패했습니다.") from None
            raw=result.stdout
        else:
            raise ExternalDataError("공식 자료 다운로드 실패: "+type(error).__name__) from None
    if len(raw)>MAX_BYTES:
        raise ExternalDataError("자료가 100 MB 상한을 초과했습니다. 범위를 좁히세요.")
    stamp=datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    digest=hashlib.sha256(raw).hexdigest()
    directory=Path(root)/"data/raw/international"/source_id/digest[:16]
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/filename
    path.write_bytes(raw)
    meta=dict(source_id=source_id,source_url=url,retrieved_at=stamp,sha256=digest,bytes=len(raw),
              raw_file=path.relative_to(root).as_posix(),license=license,redistribution=redistribution,
              status="source_downloaded",reference_date=stamp[:10])
    (directory/"manifest.json").write_bytes((json.dumps(meta,ensure_ascii=False,indent=2)+"\n").encode("utf-8"))
    return raw,meta

def save_records(rows,meta,*,root=ROOT,filename="records.csv"):
    directory=Path(root)/"data/processed/international"/meta["source_id"]
    directory.mkdir(parents=True,exist_ok=True)
    frame=pd.DataFrame(rows)
    frame.to_csv(directory/filename,index=False,encoding="utf-8-sig")
    manifest=dict(meta,status="normalized" if rows else "source_document_only",record_count=len(rows),
                  processed_file=(directory/filename).relative_to(root).as_posix(),
                  processed_sha256=hashlib.sha256((directory/filename).read_bytes()).hexdigest())
    (directory/"manifest.json").write_bytes((json.dumps(manifest,ensure_ascii=False,indent=2)+"\n").encode("utf-8"))
    return manifest

def metadata(meta,**values):
    row=dict(country=None,geography=None,year=None,waste_scope=None,material=None,
             collection_mode="not_reported",process_stage=None,numerator_definition=None,
             denominator_definition=None,mass_unit="t",currency=None,price_year=None,
             measurement_type="official_statistic",uncertainty="출처의 반올림·결측·국가별 정의 확인",
             source_locator=None,evidence_grade="A",comparability_flag="not_harmonized")
    row.update({key:meta[key] for key in ("source_id","source_url","retrieved_at","license")})
    row.update(values)
    return row

import json
from pathlib import Path
import pytest
from src.public_data.client import load_service_key
from scripts import collect_public_data as cli

@pytest.mark.parametrize("name,expected",[("DATA_GO_KR_SERVICE_KEY","facility-key"),("JODAL","contract-key")])
def test_separate_api_credentials_are_loaded_without_substitution(tmp_path,monkeypatch,name,expected):
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY",raising=False)
    monkeypatch.delenv("JODAL",raising=False)
    (tmp_path/".env").write_text("DATA_GO_KR_SERVICE_KEY=facility-key\nJODAL=contract-key\n",encoding="utf-8")
    assert load_service_key(tmp_path,name=name)==expected

def test_unrelated_credential_name_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_service_key(tmp_path,name="UNRELATED_SECRET")

def test_dry_run_requires_neither_key_nor_network(monkeypatch,capsys,tmp_path):
    def forbidden(*args,**kwargs):
        raise AssertionError("dry-run must not access credentials")
    monkeypatch.setattr(cli,"load_service_key",forbidden)
    assert cli.main(["--dataset","all","--year","2024","--dry-run","--output-root",str(tmp_path)])==0
    report=json.loads(capsys.readouterr().out)
    assert len(report["plan"]["facilities"])==1
    assert len(report["plan"]["contracts"])==159
    assert not list(tmp_path.iterdir())

def test_contract_cli_selects_jodal_key(monkeypatch,capsys,tmp_path):
    requested=[]
    monkeypatch.setattr(cli,"load_service_key",lambda **kwargs: requested.append(kwargs.get("name")) or "synthetic")
    monkeypatch.setattr(cli,"PublicDataClient",lambda key:object())
    monkeypatch.setattr(cli,"collect_dataset",lambda *args,**kwargs:dict(dataset="contracts",status="partial",complete=False,record_count=0,candidate_count=0,normalized_path=None,pages=[{}]))
    assert cli.main(["--dataset","contracts","--year","2024","--output-root",str(tmp_path)])==0
    assert requested==["JODAL"]
    assert json.loads(capsys.readouterr().out)[0]["status"]=="partial"

def test_all_cli_stops_at_global_page_budget(monkeypatch,capsys,tmp_path):
    calls=[]
    monkeypatch.setattr(cli,"load_service_key",lambda **kwargs:"synthetic")
    monkeypatch.setattr(cli,"PublicDataClient",lambda key:object())
    def collect(dataset,**kwargs):
        calls.append(dataset)
        return dict(dataset=dataset,status="complete",complete=True,record_count=0,candidate_count=0,normalized_path=None,pages=[{}])
    monkeypatch.setattr(cli,"collect_dataset",collect)
    assert cli.main(["--dataset","all","--year","2024","--output-root",str(tmp_path)])==0
    assert calls==["facilities"]
    assert json.loads(capsys.readouterr().out)[1]["status"]=="not_started"

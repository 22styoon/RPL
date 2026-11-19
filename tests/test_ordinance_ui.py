"""Current legal evidence controls displayed counts and article access."""
from copy import deepcopy
from types import SimpleNamespace

import pandas as pd

from src import statistics_ui as ui


def test_current_legal_evidence_overrides_cached_counts_without_changing_policy(monkeypatch):
    cached={"law_ordinance_version_candidates":659,"law_ordinance_detail_json_count":20,
            "policy_verified_rows":4,"verified_join_rows":12,"cached_report_stale":False}
    before=deepcopy(cached)
    calls=[]
    def current(root,cached_summary=None):
        calls.append((root,cached_summary))
        return {"law_linkage_verified":False,"law_linkage_status":"input_changed",
                "law_linkage_reasons":["candidate_csv_changed"],
                "law_ordinance_version_candidates":0,"law_ordinance_detail_json_count":0,
                "cached_law_ordinance_version_candidates":659}
    monkeypatch.setattr(ui,"current_ordinance_fields",current)
    view=ui.live_ordinance_view(cached)
    assert view["law_ordinance_version_candidates"]==0
    assert view["law_linkage_verified"] is False
    assert view["cached_law_report_stale"] is True
    assert view["cached_report_stale"] is True
    assert view["policy_verified_rows"]==4 and view["verified_join_rows"]==12
    assert cached==before
    assert len(calls)==1 and calls[0][1] is cached


def test_legal_view_rechecks_each_time_instead_of_reusing_success(monkeypatch):
    cached={"law_ordinance_version_candidates":2,"law_ordinance_detail_json_count":1}
    responses=iter([
        {"law_linkage_verified":True,"law_ordinance_version_candidates":2,"law_ordinance_detail_json_count":1},
        {"law_linkage_verified":False,"law_ordinance_version_candidates":0,"law_ordinance_detail_json_count":0},
    ])
    monkeypatch.setattr(ui,"current_ordinance_fields",lambda *args,**kwargs:next(responses))
    first=ui.live_ordinance_view(cached)
    second=ui.live_ordinance_view(cached)
    assert first["law_linkage_verified"] is True and first["cached_report_stale"] is False
    assert second["law_linkage_verified"] is False and second["cached_report_stale"] is True


def test_article_search_matches_title_locality_and_exact_text_without_regex():
    articles=pd.DataFrame([
        {"policy_name":"재활용 조례","locality":"서울특별시 중구","article_text":"제[3]조 분리배출","raw_detail_sha256":"a"*64},
        {"policy_name":"폐기물 관리","locality":"부산광역시 중구","article_text":"제3조 수집운반","raw_detail_sha256":"b"*64},
    ])
    before=articles.copy(deep=True)
    for query in ("재활용","서울특별시","[3]"):
        selected=ui.filter_ordinance_articles(articles,query)
        assert len(selected)==1 and selected.iloc[0].raw_detail_sha256=="a"*64
    assert ui.filter_ordinance_articles(articles,".*").empty
    assert len(ui.filter_ordinance_articles(articles,"  "))==2
    pd.testing.assert_frame_equal(articles,before)


class Capture:
    column_config=SimpleNamespace(LinkColumn=lambda *args,**kwargs:None)
    def __init__(self,query=""):
        self.query=query
        self.frames=[]
        self.downloads=[]
        self.messages=[]
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def subheader(self,*args,**kwargs):pass
    def caption(self,value,**kwargs):self.messages.append(value)
    def warning(self,value,**kwargs):self.messages.append(value)
    def info(self,value,**kwargs):self.messages.append(value)
    def code(self,*args,**kwargs):pass
    def expander(self,*args,**kwargs):return self
    def text_input(self,*args,**kwargs):return self.query
    def dataframe(self,frame,**kwargs):self.frames.append(frame)
    def download_button(self,*args,**kwargs):self.downloads.append((args,kwargs))


def test_unverified_legal_linkage_does_not_read_or_download_old_tables(monkeypatch):
    captured=Capture()
    monkeypatch.setattr(ui,"st",captured)
    def disallowed(*args,**kwargs):raise AssertionError("stale legal table read")
    monkeypatch.setattr(ui.pd,"read_csv",disallowed)
    ui.render_ordinance_evidence({"law_linkage_verified":False,"cached_law_report_stale":True,
                                 "law_linkage_reasons":["raw_detail_changed"]})
    assert not captured.downloads and not captured.frames
    assert any("과거 건수를 현재 검증 결과로 표시하지" in message for message in captured.messages)


def test_verified_legal_view_keeps_article_provenance_and_temporal_limit(tmp_path,monkeypatch):
    directory=tmp_path/"data/processed/regional_2024"
    directory.mkdir(parents=True)
    pd.DataFrame([
        {"policy_name":"재활용 조례","locality":"서울특별시 중구","ordinance_serial":"123",
         "effective_date":"20240501","article_number":"제3조","article_title":"분리배출",
         "article_text":"종이류를 분리배출한다.","source_url":"https://www.law.go.kr/ordinInfoP.do?ordinSeq=123",
         "source_locator":"MST=123","json_pointer":"/조문/0/조내용","raw_detail_sha256":"a"*64,
         "legal_version_status":"version_metadata_matched"},
        {"policy_name":"폐기물 조례","locality":"부산광역시 중구","article_text":"수거한다."},
    ]).to_csv(directory/"policy_ordinance_article_evidence.csv",index=False,encoding="utf-8-sig")
    captured=Capture("분리배출")
    monkeypatch.setattr(ui,"ROOT",tmp_path)
    monkeypatch.setattr(ui,"st",captured)
    ui.render_ordinance_evidence({"law_linkage_verified":True,"law_article_evidence_rows":2,
                                 "law_verified_document_version_rows":1})
    assert len(captured.frames)==1 and len(captured.frames[0])==1
    assert captured.frames[0].iloc[0]["원문 SHA-256"]=="a"*64
    assert captured.frames[0].iloc[0]["조문 위치"]=="/조문/0/조내용"
    assert len(captured.downloads)==1
    assert b"MST=123" in captured.downloads[0][0][1]
    assert any("유효했던 모든 조례" in message for message in captured.messages)
    assert any("실제 사업 시행" in message for message in captured.messages)

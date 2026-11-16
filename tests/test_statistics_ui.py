from pathlib import Path
from streamlit.testing.v1 import AppTest
from src.model import ROOT
from src.statistics_ui import MENU,artifact_path
import pytest

def test_artifacts_cannot_escape_output_directory():
    with pytest.raises(ValueError):
        artifact_path("../.env")

def test_every_public_menu_renders_without_external_calls(monkeypatch):
    from src.external_data import common
    from src.public_data.client import PublicDataClient
    def forbidden(*args,**kwargs):
        raise AssertionError("Opening menus must not collect remote data")
    monkeypatch.setattr(common,"fetch",forbidden)
    monkeypatch.setattr(PublicDataClient,"fetch",forbidden)
    app=AppTest.from_file(str(ROOT/"app.py"),default_timeout=45).run()
    assert not app.exception
    assert "RPL |" in app.title[0].value
    for page in MENU:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, page

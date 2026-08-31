import pytest
from audio_controller import settings


@pytest.fixture
def tmp_settings_file(tmp_path, monkeypatch):
    """Point settings persistence at a temp file so tests never touch the real
    ~/.audio_controller_settings.* files."""
    json_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "file", json_file)
    legacy = tmp_path / "settings.pickle"
    monkeypatch.setattr(settings, "_legacy_pickle_file", legacy)
    return json_file

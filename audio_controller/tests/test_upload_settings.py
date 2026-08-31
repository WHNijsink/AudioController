import json
import os
import pickle
from audio_controller import settings


def _evil_function():
    """This function would be called if the pickle were unpickled."""
    os.environ["PWNED"] = "yes"


class _Evil:
    def __reduce__(self):
        return (_evil_function, ())


def test_set_binary_rejects_malicious_pickle(tmp_settings_file):
    # S2: uploaded settings must be parsed as json, never unpickled.
    os.environ.pop("PWNED", None)
    settings.settings.title = "Before"
    payload = pickle.dumps(_Evil())
    settings.set_binary(payload)  # must NOT execute the pickle
    assert "PWNED" not in os.environ
    assert settings.settings.title == "Before"  # unchanged


def test_set_binary_accepts_valid_json(tmp_settings_file):
    store = {
        "settings": {"version": 11, "title": "Uploaded"},
        "sources": [],
        "destinations": [],
        "psalmbord": {"fontfamily": "Samsung", "fontsize": 8, "fontweight": 400,
                      "active": 1, "screens": [], "refreshrate": 10},
        "cameras": [],
        "users": [],
    }
    settings.set_binary(json.dumps(store).encode("utf-8"))
    assert settings.settings.title == "Uploaded"
    assert tmp_settings_file.exists()


def test_set_binary_rejects_non_settings_json(tmp_settings_file):
    settings.settings.title = "Keep"
    settings.set_binary(json.dumps({"foo": "bar"}).encode("utf-8"))
    assert settings.settings.title == "Keep"  # missing required keys -> ignored


def test_get_binary_returns_json_bytes(tmp_settings_file):
    settings.settings.title = "Bin"
    settings.save()
    raw = settings.get_binary()
    parsed = json.loads(raw)
    assert parsed["settings"]["title"] == "Bin"

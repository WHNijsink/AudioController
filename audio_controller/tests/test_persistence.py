import json
import pickle
from audio_controller import settings


def test_save_writes_valid_json_no_tmp_left(tmp_settings_file):
    settings.settings.title = "TestKerk"
    settings.save()
    assert tmp_settings_file.exists()
    data = json.loads(tmp_settings_file.read_text(encoding="utf-8"))
    assert data["settings"]["title"] == "TestKerk"
    assert set(data.keys()) == {"settings", "sources", "destinations",
                                "psalmbord", "cameras", "users"}
    # atomic write must not leave a temp file behind
    leftovers = list(tmp_settings_file.parent.glob("*.tmp"))
    assert leftovers == []


def test_save_then_load_roundtrip(tmp_settings_file):
    settings.settings.title = "RoundTrip"
    settings.pb.refreshrate = 15
    settings.save()
    # mutate in memory, then load should overwrite from disk
    settings.settings.title = "changed"
    settings.pb.refreshrate = 3
    assert settings.load() is True
    assert settings.settings.title == "RoundTrip"
    assert settings.pb.refreshrate == 15


def test_load_migrates_legacy_pickle(tmp_settings_file):
    # no json yet, but a legacy pickle exists (pre-json format, version 9,
    # and crucially WITHOUT the cameras/users keys - upgrade() must backfill them)
    store = {
        "settings": {"version": 9, "title": "Legacy"},
        "sources": [],
        "destinations": [],
        "psalmbord": {"fontfamily": "Samsung", "fontsize": 8,
                      "fontweight": 400, "active": True},
    }
    settings._legacy_pickle_file.write_bytes(pickle.dumps(store))
    assert settings.load() is True
    assert settings.settings.title == "Legacy"
    # migration must have written the json file
    assert tmp_settings_file.exists()
    data = json.loads(tmp_settings_file.read_text(encoding="utf-8"))
    # backfilled keys are present after migration
    assert "cameras" in data and "users" in data

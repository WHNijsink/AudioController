"""Migratie van een v1.4-store (versie 9): het oude psalmbord-model had 'title' en
'regels'. upgrade() voegde 'screens' toe maar liet die oude sleutels staan, waardoor
Psalmbord.__init__(**store['psalmbord']) een TypeError gaf, load() False teruggaf en
de app stilzwijgend alle instellingen naar defaults resette."""
import json

from audio_controller import settings


def _v9_store():
    return {
        "settings": {**{k: v for k, v in json.loads(json.dumps(settings.asdict(settings.Settings()))).items()},
                     "version": 9, "title": "GG Rijssen-West"},
        "sources": [{"name": "Kerkzaal West", "enabled": True, "port_url": "IN1", "scan_prio": 1,
                     "db_level": -45, "selected": True, "id": 0}],
        "destinations": [],
        "psalmbord": {"title": "", "regels": [{"text": "Ps 25:4"}, {"text": "Ps 84:4"}],
                      "fontfamily": "Arial", "fontsize": 9.0, "fontweight": 400, "active": True},
    }


def test_v9_store_with_old_psalmbord_loads(tmp_settings_file):
    settings.use_from_store(_v9_store())
    assert settings.settings.version == 11
    assert settings.settings.title == "GG Rijssen-West"
    assert [s.name for s in settings.sources] == ["Kerkzaal West"]
    assert settings.pb.fontfamily == "Arial" and settings.pb.fontweight == 400
    assert settings.pb.active == 1
    assert len(settings.pb.screens) > 0
    assert not hasattr(settings.pb, "regels")


def test_v9_pickle_style_file_loads_instead_of_resetting(tmp_settings_file):
    tmp_settings_file.write_text(json.dumps(_v9_store()))
    assert settings.load() is True
    assert settings.settings.title == "GG Rijssen-West"
    saved = json.loads(tmp_settings_file.read_text())
    assert saved["settings"]["version"] == 11
    assert "regels" not in saved["psalmbord"] and "title" not in saved["psalmbord"]

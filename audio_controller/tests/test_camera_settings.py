"""Camera-instellingen: poorten zijn integers, ongeldige poorten worden geweigerd.

Aanleiding: op een Pi stond port_http opgeslagen als de string "37710" (de
router-forward van buiten), terwijl de code die poort alleen intern gebruikt.
De admin-UI levert getallen als string aan; de opslag moet ze als int bewaren
en onzin (tekst, 0, > 65535) weigeren i.p.v. stilzwijgend opslaan.
"""
import json
import pytest

from audio_controller import settings


def _cam(**override):
    base = {"name": "Kerk", "url_intern": "10.0.0.5", "url_extern": "x.example",
            "port_http": 80, "port_onvif": 2000, "port_ws": 8088,
            "username": "u", "password": "p", "config_presets": [], "active": "0"}
    base.update(override)
    return base


def test_port_strings_from_ui_are_stored_as_int(tmp_settings_file):
    settings.update_cameras([_cam(port_http="37710", port_onvif="2000", port_ws="8087")])
    cam = settings.cameras[0]
    assert (cam.port_http, cam.port_onvif, cam.port_ws) == (37710, 2000, 8087)
    assert all(isinstance(p, int) for p in (cam.port_http, cam.port_onvif, cam.port_ws))
    stored = json.loads(tmp_settings_file.read_text())["cameras"][0]
    assert stored["port_http"] == 37710 and isinstance(stored["port_http"], int)


@pytest.mark.parametrize("bad", ["abc", "", 0, -1, 65536, "80.5", None])
def test_invalid_port_is_rejected_and_cameras_unchanged(tmp_settings_file, bad):
    settings.update_cameras([_cam(name="Bestaand")])
    with pytest.raises(ValueError):
        settings.update_cameras([_cam(name="Nieuw", port_http=bad)])
    assert [c.name for c in settings.cameras] == ["Bestaand"]


@pytest.mark.parametrize("host", ["192.168.1.9", "10.0.0.5", "172.16.0.4", "camera-kerk.local"])
def test_url_intern_accepts_lan_hosts(host):
    # S-M4: cameras live on the private LAN, so private IPs and plain hostnames
    # must stay valid; only a bare host/IP is allowed (it is spliced into
    # http://{url_intern}/ajaxcom).
    assert settings.validate_camera_attribute("url_intern", host) == host


@pytest.mark.parametrize("bad", [
    "127.0.0.1",                       # loopback -> could hit the app's own ports
    "::1",
    "169.254.1.1",                     # link-local
    "127.0.0.1:5000/general/reboot",   # port/path injection into the url
    "evil.example/path",               # path injection
    "http://192.168.1.9",              # scheme injection
    "192.168.1.9 --arg",               # whitespace
    "a@b",                             # userinfo
])
def test_url_intern_rejects_ssrf_and_injection(bad):
    with pytest.raises(ValueError):
        settings.validate_camera_attribute("url_intern", bad)


def test_setting_ssrf_url_intern_leaves_cameras_unchanged(tmp_settings_file):
    settings.update_cameras([_cam(url_intern="10.0.0.5")])
    with pytest.raises(ValueError):
        settings.update_cameras([_cam(url_intern="127.0.0.1")])
    assert settings.cameras[0].url_intern == "10.0.0.5"  # prior config kept


def test_validate_camera_port_attribute_casts_and_bounds():
    assert settings.validate_camera_attribute("port_http", "8080") == 8080
    assert settings.validate_camera_attribute("port_ws", 65535) == 65535
    for bad in ("x", 0, 65536):
        with pytest.raises(ValueError):
            settings.validate_camera_attribute("port_onvif", bad)


def test_load_coerces_legacy_string_ports_to_int(tmp_settings_file):
    # bestaand json-bestand van een oudere versie met poorten als string
    settings.update_cameras([_cam()])
    store = json.loads(tmp_settings_file.read_text())
    store["cameras"][0]["port_http"] = "37710"
    store["cameras"][0]["port_ws"] = "8087"
    tmp_settings_file.write_text(json.dumps(store))
    assert settings.load() is True
    cam = settings.cameras[0]
    assert (cam.port_http, cam.port_ws) == (37710, 8087)
    assert isinstance(cam.port_http, int)


def test_load_survives_unparseable_port(tmp_settings_file):
    # een onherstelbare poort mag niet de hele config (en dus alle settings) laten vallen
    settings.update_cameras([_cam()])
    store = json.loads(tmp_settings_file.read_text())
    store["cameras"][0]["port_http"] = "kapot"
    store["settings"]["title"] = "Behouden"
    tmp_settings_file.write_text(json.dumps(store))
    assert settings.load() is True
    assert settings.settings.title == "Behouden"
    assert settings.cameras[0].port_http == "kapot"

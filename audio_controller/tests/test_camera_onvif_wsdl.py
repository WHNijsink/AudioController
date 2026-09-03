"""ONVIF: de WSDL-map van onvif-zeep moet gevonden en meegegeven worden.

Aanleiding (west): de onvif-zeep wheel zet zijn wsdl-bestanden onder
<venv>/lib/python3.4/site-packages/wsdl, ook op Python 3.7, terwijl ONVIFCamera
standaard naast het onvif-package zoekt. Bovendien verwees is_onvif_available
naar settings.ONVIF_WSDL_DIR, dat nergens bestond: ONVIF was dus altijd 'niet
beschikbaar' en connect() faalde met 'No such file: .../wsdl/devicemgmt.wsdl'.
"""
import os
import pytest

from audio_controller import camera


def _make_wsdl(dirpath):
    dirpath.mkdir(parents=True)
    (dirpath / "devicemgmt.wsdl").write_text("<wsdl/>")
    return str(dirpath)


def test_find_onvif_wsdl_dir_prefers_dir_next_to_package(tmp_path):
    pkg = tmp_path / "site" / "onvif"
    pkg.mkdir(parents=True)
    expected = _make_wsdl(tmp_path / "site" / "wsdl")
    _make_wsdl(tmp_path / "prefix" / "lib" / "python3.4" / "site-packages" / "wsdl")
    assert camera.find_onvif_wsdl_dir(package_dir=str(pkg), prefix=str(tmp_path / "prefix")) == expected


def test_find_onvif_wsdl_dir_falls_back_to_other_python_version_dir(tmp_path):
    pkg = tmp_path / "prefix" / "lib" / "python3.7" / "site-packages" / "onvif"
    pkg.mkdir(parents=True)
    expected = _make_wsdl(tmp_path / "prefix" / "lib" / "python3.4" / "site-packages" / "wsdl")
    assert camera.find_onvif_wsdl_dir(package_dir=str(pkg), prefix=str(tmp_path / "prefix")) == expected


def test_find_onvif_wsdl_dir_returns_none_when_missing(tmp_path):
    pkg = tmp_path / "site" / "onvif"
    pkg.mkdir(parents=True)
    assert camera.find_onvif_wsdl_dir(package_dir=str(pkg), prefix=str(tmp_path / "prefix")) is None


def test_installed_onvif_wsdl_dir_is_usable():
    assert os.path.isfile(os.path.join(camera.ONVIF_WSDL_DIR, "devicemgmt.wsdl"))


class _FakeService:
    def GetProfiles(self):
        return [type("P", (), {"token": "0"})()]

    def GetDeviceInformation(self):
        return {}


class _FakeONVIFCamera:
    calls = []

    def __init__(self, host, port, user, passwd, wsdl_dir=None, **kw):
        _FakeONVIFCamera.calls.append(wsdl_dir)

    def create_media_service(self):
        return _FakeService()

    create_ptz_service = create_media_service
    create_devicemgmt_service = create_media_service


@pytest.fixture
def fake_onvif(monkeypatch):
    _FakeONVIFCamera.calls.clear()
    monkeypatch.setattr(camera, "ONVIFCamera", _FakeONVIFCamera)
    return _FakeONVIFCamera


def _cam():
    return camera.Camera(name="Kerk", url_intern="10.0.0.5", url_extern="x", port_http=80,
                         port_onvif=2000, port_ws=8088, username="u", password="p")


def test_connect_passes_wsdl_dir(fake_onvif):
    _cam().connect()
    assert fake_onvif.calls == [camera.ONVIF_WSDL_DIR]


def test_is_onvif_available_passes_wsdl_dir_and_reports_true(fake_onvif):
    assert _cam().is_onvif_available() is True
    assert fake_onvif.calls == [camera.ONVIF_WSDL_DIR]

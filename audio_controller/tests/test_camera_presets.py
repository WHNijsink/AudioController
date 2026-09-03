"""Presets uit de camera: preset 0 (de home-positie) hoort niet in het bedieningspaneel."""
from audio_controller import camera


class _Preset:
    def __init__(self, token, name=""):
        self.token = token
        self.Name = name


class _FakePTZ:
    def __init__(self, presets):
        self._presets = presets

    def GetPresets(self, _args):
        return self._presets


def _connected_cam(presets):
    cam = camera.Camera(name="Kerk", url_intern="10.0.0.5", url_extern="x", port_http=80,
                        port_onvif=2000, port_ws=8088, username="u", password="p",
                        config_presets=[camera.Preset("0", "Home"), camera.Preset("1", "Podium")])
    cam._ptz = _FakePTZ(presets)
    cam._profile = type("P", (), {"token": "prof0"})()
    return cam


def test_load_presets_hides_preset_0():
    cam = _connected_cam([_Preset(0), _Preset(1), _Preset(2, "Kansel")])
    tokens = [p.token for p in cam.load_presets()]
    assert tokens == ["1", "2"]
    assert [p.token for p in cam.presets] == ["1", "2"]


def test_load_presets_keeps_labels_for_remaining_presets():
    cam = _connected_cam([_Preset(0), _Preset(1), _Preset(2, "Kansel")])
    labels = {p.token: p.label for p in cam.load_presets()}
    assert labels == {"1": "Podium", "2": "Kansel"}

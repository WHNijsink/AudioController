from audio_controller import __main__ as m


def test_valid_volume_accepts_percent():
    assert m.valid_volume("80%") == "80%"
    assert m.valid_volume("100%") == "100%"
    assert m.valid_volume("0%") == "0%"


def test_valid_volume_accepts_bare_number():
    assert m.valid_volume("75") == "75%"


def test_valid_volume_rejects_injection():
    assert m.valid_volume("80%; reboot") == "100%"
    assert m.valid_volume("$(reboot)") == "100%"
    assert m.valid_volume("") == "100%"
    assert m.valid_volume(None) == "100%"

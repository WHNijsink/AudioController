from audio_controller import settings


def test_settings_module_imports():
    # The module runs init_settings() at import; the dataclasses must exist.
    assert isinstance(settings.settings.title, str)
    # psalmbord rendering now lives on the Psalmbord dataclass (settings.pb)
    assert hasattr(settings.pb, "psalmbord_as_html")
    assert callable(settings.pb.psalmbord_as_html)

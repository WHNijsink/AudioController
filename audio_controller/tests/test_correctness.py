from audio_controller import controller


def test_config_has_url_in():
    # C1: config.url_in must exist (was referenced in scan_ports but never assigned)
    assert hasattr(controller.config, "url_in")
    assert controller.config.url_in is None


def test_stop_all_clears_url_in():
    # C1: after stopping everything, url_in is cleared
    controller.config.url_in = "http://example/live"
    controller.config.sources = []
    controller.config.stop_all()
    assert controller.config.url_in is None

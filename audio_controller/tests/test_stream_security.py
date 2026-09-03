from audio_controller import stream


def test_sanitize_bitrate_valid():
    assert stream.sanitize_bitrate("64K") == "64K"
    assert stream.sanitize_bitrate("128k") == "128k"
    assert stream.sanitize_bitrate("192") == "192"
    assert stream.sanitize_bitrate("1M") == "1M"


def test_sanitize_bitrate_rejects_injection():
    assert stream.sanitize_bitrate("64K; rm -rf ~") == "64K"
    assert stream.sanitize_bitrate("") == "64K"
    assert stream.sanitize_bitrate("$(reboot)") == "64K"


def test_ffmpeg_input_is_argv_with_url_single_token():
    # no shell is used; the url is one argv element and cannot be split/injected
    raw = "http://host/live; rm -rf ~"
    out = stream.ffmpeg_input_for_url(raw)
    assert out == ["-i", raw]
    assert isinstance(out, list)


def test_ffmpeg_output_is_argv_with_url_single_token():
    raw = "icecast://h/m`reboot`"
    out = stream.ffmpeg_output_for_url(raw)
    assert isinstance(out, list)
    assert out[-1] == raw                       # url is a single trailing argv token
    i = out.index("-b:a")
    assert out[i + 1] == "64K"                  # default bitrate as its own token


def test_ffmpeg_output_bitrate_after_semicolon():
    out = stream.ffmpeg_output_for_url("icecast://h/mount;128K")
    assert out[-1] == "icecast://h/mount"
    i = out.index("-b:a")
    assert out[i + 1] == "128K"

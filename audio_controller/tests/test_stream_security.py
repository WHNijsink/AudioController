import shlex
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


def test_ffmpeg_input_quotes_url():
    raw = "http://host/live; rm -rf ~"
    out = stream.ffmpeg_input_for_url(raw)
    assert shlex.quote(raw) in out          # dangerous chars are inside a shell-quoted token
    assert out.startswith("-i ")


def test_ffmpeg_output_neutralizes_injection():
    out = stream.ffmpeg_output_for_url("icecast://h/m`reboot`")
    assert shlex.quote("icecast://h/m`reboot`") in out
    assert "-b:a 64K" in out


def test_ffmpeg_output_bitrate_after_semicolon():
    out = stream.ffmpeg_output_for_url("icecast://h/mount;128K")
    assert "-b:a 128K" in out
    assert shlex.quote("icecast://h/mount") in out

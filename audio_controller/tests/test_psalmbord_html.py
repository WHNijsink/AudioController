from audio_controller import psalmbord


def _board(text):
    pb = psalmbord.Psalmbord()
    pb.screens = [{"index": 0, "text": text, "size": 8}]
    pb.active = 0
    return pb.psalmbord_as_html()


def test_title_line_is_escaped():
    # S3: a leading '_' marks a title line; its text must be html-escaped
    html = _board("_<img src=x onerror=alert(1)>")
    assert "<img" not in html
    assert "&lt;img" in html


def test_no_column_line_is_escaped():
    html = _board("<script>bad()</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_column_line_is_escaped():
    # a line with ':' renders as columns; both sides must be escaped
    html = _board("<b>Ps 45</b> : <i>1</i>")
    assert "<b>" not in html
    assert "<i>" not in html
    assert "&lt;b&gt;" in html


def test_empty_screens_returns_empty_string():
    # bounds guard: no screens / out-of-range active index must not raise
    pb = psalmbord.Psalmbord()
    pb.screens = []
    pb.active = 0
    assert pb.psalmbord_as_html() == ""


def test_board_renders_with_dataclass_screens():
    # settings.restore() builds screens as PsalmbordScreen dataclasses (not
    # dicts), so the board must render those too instead of crashing with 500
    pb = psalmbord.Psalmbord()
    pb.screens = [psalmbord.PsalmbordScreen(index=0, text="Ps 45 : 1", size=8)]
    pb.active = 0
    html = pb.psalmbord_as_html()
    assert "Ps" in html

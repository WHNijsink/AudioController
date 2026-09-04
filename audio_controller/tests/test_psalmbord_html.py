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


# --- content-hash refresh (Guis f9e284c), hardened during the merge ---

def _valid_update(pb, screens, active=0):
    return pb.update_psalmbord(
        fontfamily="Samsung", fontsize=8, fontweight=400,
        active=active, screens=screens, refreshrate=10,
    )


def test_update_psalmbord_hash_survives_dataclass_screens(tmp_settings_file):
    # regression: the content-hash used screens[active]["text"], which crashes on
    # the PsalmbordScreen dataclasses that load()/restore() build.
    pb = psalmbord.Psalmbord()
    result = _valid_update(pb, [psalmbord.PsalmbordScreen(index=0, text="Ps 84 : 1", size=8)])
    assert result is not None
    assert len(pb.html_hash) == 64  # sha256 hex


def test_update_psalmbord_hash_survives_out_of_range_active(tmp_settings_file):
    # bounds guard: an out-of-range active index must not raise (mirrors
    # psalmbord_as_html's guard).
    pb = psalmbord.Psalmbord()
    result = _valid_update(pb, [{"index": 0, "text": "Ps 1", "size": 8}], active=5)
    assert result is not None
    assert len(pb.html_hash) == 64


def test_default_board_hash_is_not_empty_string(tmp_settings_file):
    # the client starts with html_hash == ""; if the server's hash were also ""
    # the first poll would report "unchanged" and the board would stay blank.
    pb = psalmbord.Psalmbord()
    _valid_update(pb, [{"index": 0, "text": "", "size": 8}])
    assert pb.html_hash != ""


def test_hash_changes_with_content_and_is_stable_when_unchanged(tmp_settings_file):
    pb = psalmbord.Psalmbord()
    _valid_update(pb, [{"index": 0, "text": "Ps 100 : 1", "size": 8}])
    h1 = pb.html_hash
    _valid_update(pb, [{"index": 0, "text": "Ps 100 : 1", "size": 8}])
    assert pb.html_hash == h1                       # same content -> same hash
    _valid_update(pb, [{"index": 0, "text": "Ps 118 : 1", "size": 8}])
    assert pb.html_hash != h1                       # changed content -> new hash

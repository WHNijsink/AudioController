"""Performance-hardening regression tests.

P1: a zero auto-switch timeout must not turn the auto_switch task into a
    100%-CPU busy loop (await asyncio.sleep(0) in a tight while True).
"""
import json

from tornado.testing import AsyncHTTPTestCase

from audio_controller import settings, controller
from audio_controller import __main__ as appmod


def test_zero_timeout_auto_switch_is_clamped_to_at_least_one_minute():
    s = settings.Settings()
    s.timeout_auto_switch = 0
    settings.validate_settings(s)
    assert s.timeout_auto_switch >= 1


def test_auto_switch_interval_never_zero_even_for_bad_stored_value():
    # Defence in depth: even if a 0 slips through, the loop's sleep interval has
    # a floor so it cannot spin the CPU.
    assert controller.auto_switch_interval_seconds(0) >= 1
    assert controller.auto_switch_interval_seconds(15) == 15 * 60


class TestKioskPageIsLean(AsyncHTTPTestCase):
    def get_app(self):
        return appmod.make_app(internal=True)  # kiosk reaches the board without login

    def setUp(self):
        super().setUp()
        settings.restore()
        settings.settings.enable_psalmbord = True

    def test_kiosk_page_drops_unused_libraries(self):
        # P4: the board's inline script uses only jQuery core; jQuery-UI, the
        # Bootstrap css+bundle, FontAwesome and bootstrap-toggle were ~750 KB of
        # dead weight loaded on a low-power kiosk. They must no longer be linked.
        body = self.fetch("/psalmbord", method="GET").body.decode()
        for dead in ("jquery-ui", "bootstrap-4.1.3-dist", "fontawesome", "bootstrap-toggle"):
            self.assertNotIn(dead, body, f"kiosk page still loads {dead}")

    def test_kiosk_page_keeps_what_it_uses(self):
        body = self.fetch("/psalmbord", method="GET").body.decode()
        self.assertIn("jquery-3.3.1.min.js", body)  # jQuery core is used ($.ajax etc.)
        self.assertIn("psalmbord.css", body)


class TestStaticCachingAndCompression(AsyncHTTPTestCase):
    def get_app(self):
        return appmod.make_app(internal=False)

    def test_static_files_allow_revalidation_not_no_store(self):
        # P2: no-store forced a full re-download of the ~1.3 MB bundle on every
        # load; a revalidatable policy lets the browser get a 304 instead.
        r = self.fetch("/static/css/index.css", method="GET")
        self.assertEqual(r.code, 200)
        cc = r.headers.get("Cache-Control", "")
        self.assertNotIn("no-store", cc)

    def test_static_files_return_304_on_conditional_get(self):
        # P2: with an ETag + revalidation, an unchanged asset costs 0 bytes.
        r = self.fetch("/static/css/index.css", method="GET")
        etag = r.headers.get("Etag")
        self.assertIsNotNone(etag)
        r2 = self.fetch("/static/css/index.css", method="GET",
                        headers={"If-None-Match": etag})
        self.assertEqual(r2.code, 304)

    def test_responses_are_gzip_compressed(self):
        # P3: enabling compress_response shrinks the large JS/CSS/HTML payloads.
        r = self.fetch("/static/css/index.css", method="GET",
                       headers={"Accept-Encoding": "gzip"},
                       decompress_response=False)
        self.assertEqual(r.headers.get("Content-Encoding"), "gzip")

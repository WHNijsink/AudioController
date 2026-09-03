"""The psalmbord is free on the internal listener (LAN kiosk screens) but
requires login on the external listener (8080, internet-facing)."""
import json
import re

from tornado.testing import AsyncHTTPTestCase

from audio_controller import __main__ as appmod
from audio_controller import settings


def _xsrf(h):
    for c in h.get_list("Set-Cookie"):
        m = re.match(r"_xsrf=([^;]+)", c)
        if m:
            return m.group(1)
    return None


def _auth(h):
    for c in h.get_list("Set-Cookie"):
        m = re.match(r"(audio_controller_user=[^;]+)", c)
        if m:
            return m.group(1)
    return None


class _PsalmbordBase(AsyncHTTPTestCase):
    INTERNAL = False

    def setUp(self):
        super().setUp()
        settings.restore()
        settings.update_users([
            {"username": "admin", "password": "AdminPw", "admin": True, "camera": True},
        ])
        settings.settings.enable_psalmbord = True

    def get_app(self):
        return appmod.make_app(self.INTERNAL)

    def _login_cookie(self):
        """Log in through the real flow; return the combined cookie header value."""
        r = self.fetch("/", method="GET")
        token = _xsrf(r.headers)
        headers = {"Content-Type": "application/json", "X-Xsrftoken": token,
                   "Cookie": f"_xsrf={token}", "Referer": "http://x/"}
        r = self.fetch("/login/login", method="POST", headers=headers,
                       body=json.dumps({"username": "admin", "password": "AdminPw"}))
        auth = _auth(r.headers)
        assert auth, "login must set the auth cookie"
        return f"_xsrf={token}; {auth}"


class ExternalPsalmbordTest(_PsalmbordBase):
    INTERNAL = False

    def test_get_without_login_redirects_to_login_page(self):
        r = self.fetch("/psalmbord", follow_redirects=False)
        self.assertEqual(r.code, 302)
        self.assertEqual(r.headers.get("Location"), "/")

    def test_post_without_login_is_403(self):
        r = self.fetch("/psalmbord", method="POST", body='{"html": true}')
        self.assertEqual(r.code, 403)

    def test_get_with_login_renders_board(self):
        r = self.fetch("/psalmbord", headers={"Cookie": self._login_cookie()})
        self.assertEqual(r.code, 200)
        self.assertIn(b"psalmbord.css", r.body)

    def test_post_with_login_returns_board_state(self):
        r = self.fetch("/psalmbord", method="POST", body='{"html": true}',
                       headers={"Cookie": self._login_cookie()})
        self.assertEqual(r.code, 200)
        result = json.loads(r.body)
        for key in ("html", "css", "active"):
            self.assertIn(key, result)


class InternalPsalmbordTest(_PsalmbordBase):
    INTERNAL = True

    def test_get_without_login_renders_board(self):
        r = self.fetch("/psalmbord")
        self.assertEqual(r.code, 200)
        self.assertIn(b"psalmbord.css", r.body)

    def test_post_without_login_returns_board_state(self):
        r = self.fetch("/psalmbord", method="POST", body='{"html": true}')
        self.assertEqual(r.code, 200)
        result = json.loads(r.body)
        for key in ("html", "css", "active"):
            self.assertIn(key, result)

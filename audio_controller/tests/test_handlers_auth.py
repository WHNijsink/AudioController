"""End-to-end handler tests for the auth/xsrf hardening (S4/S5/S7 + forced change).

Uses Tornado's AsyncHTTPTestCase so the real make_app() wiring is exercised.
"""
import json
import re
from tornado.testing import AsyncHTTPTestCase

from audio_controller import __main__ as appmod
from audio_controller import settings, user


def _xsrf_from(headers):
    """Extract the _xsrf cookie value from a response's Set-Cookie header(s)."""
    for _, v in headers.get_all():
        pass
    cookies = headers.get_list("Set-Cookie")
    for c in cookies:
        m = re.match(r"_xsrf=([^;]+)", c)
        if m:
            return m.group(1)
    return None


class _Base(AsyncHTTPTestCase):
    INTERNAL = False

    def setUp(self):
        super().setUp()
        # fresh default users (forced-change admin) for every test
        settings.restore()

    def get_app(self):
        return appmod.make_app(internal=self.INTERNAL)

    def _prime_xsrf(self):
        """GET / to obtain an _xsrf cookie; return (token, cookie_header)."""
        r = self.fetch("/", method="GET")
        token = _xsrf_from(r.headers)
        assert token, "no _xsrf cookie issued"
        return token, f"_xsrf={token}"

    def _post(self, path, body, token=None, cookie=None, extra_cookie=""):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Xsrftoken"] = token
        ck = cookie or ""
        if extra_cookie:
            ck = (ck + "; " + extra_cookie) if ck else extra_cookie
        if ck:
            headers["Cookie"] = ck
        return self.fetch(path, method="POST", body=json.dumps(body), headers=headers)


class TestExternalAuth(_Base):
    INTERNAL = False

    def test_xsrf_required_on_post(self):
        # S5: a state-changing POST without an xsrf token is rejected (403)
        r = self.fetch("/audio/getSources", method="POST", body="{}",
                       headers={"Content-Type": "application/json"})
        self.assertEqual(r.code, 403)

    def test_audio_requires_login(self):
        # S7: even with a valid xsrf token, audio routing needs login
        token, cookie = self._prime_xsrf()
        r = self._post("/audio/setSources", {"sources": []}, token=token, cookie=cookie)
        self.assertEqual(r.code, 200)
        self.assertEqual(json.loads(r.body)["success"], False)

    def test_default_admin_login_forces_change_and_is_gated(self):
        token, cookie = self._prime_xsrf()
        # log in as the default admin (Referer required by check_app)
        r = self.fetch("/login/login", method="POST",
                       body=json.dumps({"username": "admin", "password": "admin"}),
                       headers={"Content-Type": "application/json",
                                "X-Xsrftoken": token, "Cookie": cookie,
                                "Referer": "http://localhost/"})
        self.assertEqual(r.code, 200)
        data = json.loads(r.body)
        self.assertTrue(data["success"])
        self.assertTrue(data["must_change_password"])
        # grab the auth cookie
        auth = None
        for c in r.headers.get_list("Set-Cookie"):
            m = re.match(r"(audio_controller_user=[^;]+)", c)
            if m:
                auth = m.group(1)
        self.assertIsNotNone(auth)
        # a gated action is refused until the password is changed
        r2 = self._post("/general/getSettings", {}, token=token,
                        cookie=cookie, extra_cookie=auth)
        self.assertEqual(r2.code, 200)
        self.assertEqual(json.loads(r2.body).get("must_change_password"), True)


class TestLocalNoLogin(_Base):
    INTERNAL = True

    def test_audio_allowed_without_login_on_local_port(self):
        # S4: trust follows the (loopback) listener, not the Host header
        token, cookie = self._prime_xsrf()
        r = self._post("/audio/getSources", {}, token=token, cookie=cookie)
        self.assertEqual(r.code, 200)
        # getSources returns a list, not a login failure
        self.assertIsInstance(json.loads(r.body), list)

    def test_psalmbord_post_is_xsrf_exempt(self):
        # S5: the read-only board endpoint stays reachable without a token, so
        # the kiosk board keeps polling (on the internal listener; the external
        # listener additionally requires login, see test_psalmbord_auth.py)
        r = self.fetch("/psalmbord", method="POST", body=json.dumps({"html": True}),
                       headers={"Content-Type": "application/json"})
        self.assertEqual(r.code, 200)

    def test_setusers_requires_login_even_on_local_port(self):
        # S-H1: account management is a privilege-escalation / persistence vector,
        # so it must require login even on the trusted loopback listener. An
        # unauthenticated local process must not be able to plant an admin.
        token, cookie = self._prime_xsrf()
        before = [u.username for u in settings.users]
        r = self._post("/login/setUsers",
                       {"users": [{"username": "backdoor", "password": "x",
                                   "admin": True, "camera": True}]},
                       token=token, cookie=cookie)
        self.assertEqual(r.code, 200)
        self.assertEqual(json.loads(r.body).get("success"), False)
        self.assertEqual([u.username for u in settings.users], before)

    def test_restore_settings_requires_login_even_on_local_port(self):
        # S-H1: restoreSettings resets every account back to admin/admin; it must
        # not be reachable without login on the loopback listener.
        settings.settings.title = "KeepMe"
        token, cookie = self._prime_xsrf()
        r = self._post("/general/restoreSettings", {}, token=token, cookie=cookie)
        self.assertEqual(r.code, 200)
        self.assertEqual(json.loads(r.body).get("success"), False)
        self.assertEqual(settings.settings.title, "KeepMe")

    def test_download_settings_requires_login_even_on_local_port(self):
        # S-H1: the settings blob carries password hashes and cleartext camera /
        # icecast credentials; downloading it must require login.
        token, cookie = self._prime_xsrf()
        r = self._post("/general/downloadSettings", {}, token=token, cookie=cookie)
        self.assertEqual(r.code, 200)
        self.assertEqual(json.loads(r.body).get("success"), False)

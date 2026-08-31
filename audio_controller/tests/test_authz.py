"""Regression tests for the authorization gaps found by critical review (S8/S9)."""
import json, re
from tornado.testing import AsyncHTTPTestCase
from audio_controller import __main__ as appmod
from audio_controller import settings, user


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


class AuthzExternal(AsyncHTTPTestCase):
    def setUp(self):
        super().setUp()
        settings.restore()
        # a real admin and a camera-only user
        settings.update_users([
            {"username": "admin", "password": "AdminPw", "admin": True, "camera": True},
            {"username": "cam", "password": "CamPw", "admin": False, "camera": True},
        ])

    def get_app(self):
        return appmod.make_app(local_no_login=False)

    def _prime(self):
        r = self.fetch("/", method="GET")
        t = _xsrf(r.headers)
        return t, f"_xsrf={t}"

    def _post(self, path, body, t, cookie, referer=None):
        h = {"Content-Type": "application/json", "X-Xsrftoken": t, "Cookie": cookie}
        if referer:
            h["Referer"] = referer
        return self.fetch(path, method="POST", body=json.dumps(body), headers=h)

    def _login(self, u, p, t, ck, referer="http://x/"):
        r = self._post("/login/login", {"username": u, "password": p}, t, ck, referer)
        return _auth(r.headers), json.loads(r.body)

    # ---- S8: user administration must require auth ----
    def test_getUsers_requires_login(self):
        t, ck = self._prime()
        r = self._post("/login/getUsers", {}, t, ck)
        self.assertIn("LoginException", r.body.decode())

    def test_setUsers_requires_login(self):
        t, ck = self._prime()
        r = self._post("/login/setUsers",
                       {"users": [{"username": "attacker", "password": "x",
                                   "admin": True, "camera": True}]}, t, ck)
        self.assertIn("LoginException", r.body.decode())
        self.assertEqual([u.username for u in settings.users], ["admin", "cam"])

    def test_admin_can_manage_users(self):
        t, ck = self._prime()
        auth, resp = self._login("admin", "AdminPw", t, ck)
        self.assertTrue(resp["success"])
        r = self._post("/login/getUsers", {}, t, ck + "; " + auth)
        self.assertEqual(r.code, 200)
        self.assertIsInstance(json.loads(r.body), list)

    # ---- S9: non-admin (camera) must not perform admin actions ----
    def test_camera_user_cannot_reboot(self):
        t, ck = self._prime()
        auth, _ = self._login("cam", "CamPw", t, ck, referer="http://x/camera")
        r = self._post("/general/reboot", {}, t, ck + "; " + auth)
        self.assertEqual(json.loads(r.body).get("success"), False)

    def test_camera_user_cannot_read_settings(self):
        t, ck = self._prime()
        auth, _ = self._login("cam", "CamPw", t, ck, referer="http://x/camera")
        r = self._post("/general/getSettings", {}, t, ck + "; " + auth)
        self.assertEqual(json.loads(r.body).get("success"), False)

    def test_camera_user_cannot_change_routing(self):
        t, ck = self._prime()
        auth, _ = self._login("cam", "CamPw", t, ck, referer="http://x/camera")
        r = self._post("/audio/setSources", {"sources": []}, t, ck + "; " + auth)
        self.assertEqual(json.loads(r.body).get("success"), False)

    def test_camera_passwords_hidden_from_non_admin(self):
        settings.update_cameras([{"name": "Kerk", "url_intern": "10.0.0.5", "url_extern": "x",
                                  "port_http": 80, "port_onvif": 2000, "port_ws": 8088,
                                  "username": "root", "password": "CAMSECRET",
                                  "config_presets": [], "active": "0"}])
        t, ck = self._prime()
        auth, _ = self._login("cam", "CamPw", t, ck, referer="http://x/camera")
        r = self._post("/camera/getCameras", {}, t, ck + "; " + auth, referer="http://x/camera")
        self.assertNotIn("CAMSECRET", r.body.decode())

    def test_admin_still_sees_camera_passwords(self):
        settings.update_cameras([{"name": "Kerk", "url_intern": "10.0.0.5", "url_extern": "x",
                                  "port_http": 80, "port_onvif": 2000, "port_ws": 8088,
                                  "username": "root", "password": "CAMSECRET",
                                  "config_presets": [], "active": "0"}])
        t, ck = self._prime()
        auth, _ = self._login("admin", "AdminPw", t, ck)
        r = self._post("/camera/getCameras", {}, t, ck + "; " + auth)
        self.assertIn("CAMSECRET", r.body.decode())

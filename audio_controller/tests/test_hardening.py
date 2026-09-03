"""Regression tests for the extra hardening (D: no hash exposure / keep-on-blank,
E: login throttling + weak-password rejection, F: version lockdown + SSRF host block)."""
import json
import re
from tornado.testing import AsyncHTTPTestCase
from audio_controller import __main__ as appmod
from audio_controller import settings
from audio_controller.handlers import handlers as H


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


class Hardening(AsyncHTTPTestCase):
    def get_app(self):
        return appmod.make_app(internal=False)

    def setUp(self):
        super().setUp()
        H._login_failures.clear()          # isolate the per-process throttle state
        settings.restore()
        settings.update_users([
            {"username": "admin", "password": "AdminPw", "admin": True, "camera": True},
            {"username": "cam", "password": "CamPw", "admin": False, "camera": True},
        ])

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

    # ---- D: password hashes must never reach the client ----
    def test_getusers_blanks_password(self):
        t, ck = self._prime()
        auth, _ = self._login("admin", "AdminPw", t, ck)
        r = self._post("/login/getUsers", {}, t, ck + "; " + auth)
        for u in json.loads(r.body):
            self.assertEqual(u["password"], "")

    def test_blank_password_keeps_existing_and_new_password_applies(self):
        t, ck = self._prime()
        auth, _ = self._login("admin", "AdminPw", t, ck)
        # client returns blank passwords for untouched users, new plaintext for a change
        self._post("/login/setUsers", {"users": [
            {"username": "admin", "password": "BrandNewPw", "admin": True, "camera": True},
            {"username": "cam", "password": "", "admin": False, "camera": True},
        ]}, t, ck + "; " + auth)
        # admin's new password works; the old one does not; cam (blank) is unchanged
        self.assertTrue(self._login("admin", "BrandNewPw", t, ck)[1]["success"])
        self.assertFalse(self._login("admin", "AdminPw", t, ck)[1].get("success"))
        self.assertTrue(self._login("cam", "CamPw", t, ck, referer="http://x/camera")[1]["success"])

    # ---- E: brute-force throttling + weak password rejection ----
    def test_login_locks_out_after_repeated_failures(self):
        t, ck = self._prime()
        for _ in range(H._LOGIN_MAX_FAILURES):
            self._login("admin", "wrong", t, ck)
        # even the correct password is now refused during the lockout window
        _, resp = self._login("admin", "AdminPw", t, ck)
        self.assertFalse(resp.get("success"))
        self.assertIn("error", resp)

    def test_setuser_rejects_weak_passwords(self):
        t, ck = self._prime()
        auth, _ = self._login("cam", "CamPw", t, ck, referer="http://x/camera")
        for weak in ("admin", "", "cam"):  # default, empty, == username
            r = self._post("/login/setUser", {"username": "cam", "password": weak},
                           t, ck + "; " + auth, referer="http://x/camera")
            self.assertFalse(json.loads(r.body).get("success"), f"weak pw accepted: {weak!r}")

    # ---- F: server-managed fields + SSRF host block ----
    def test_setsettings_cannot_change_version(self):
        t, ck = self._prime()
        auth, _ = self._login("admin", "AdminPw", t, ck)
        before = json.loads(self._post("/general/getSettings", {}, t, ck + "; " + auth).body)["version"]
        self._post("/general/setSettings", {"version": 1, "title": "Changed"},
                   t, ck + "; " + auth)
        after = json.loads(self._post("/general/getSettings", {}, t, ck + "; " + auth).body)
        self.assertEqual(after["version"], before)   # version untouched
        self.assertEqual(after["title"], "Changed")  # other fields still update

    def test_internal_host_stream_urls_rejected(self):
        assert settings.validate_source_attribute("port_url", "http://127.0.0.1:8000/x") is None
        assert settings.validate_source_attribute("port_url", "http://192.168.1.5/x") is None
        assert settings.validate_destination_attribute("port_url_file", "http://169.254.169.254/latest") is None
        # public hosts and ALSA ports remain valid
        assert settings.validate_source_attribute("port_url", "http://ro1.reformatorischeomroep.nl:8003/live")
        assert settings.validate_source_attribute("port_url", "IN1") == "IN1"

    # ---- camera role == what camera.js sends; only non-camera.js actions are admin ----
    def test_camera_role_matches_camera_app(self):
        t, ck = self._prime()
        auth, _ = self._login("cam", "CamPw", t, ck, referer="http://x/camera")
        # setPresetLabel is NOT called by camera.js (admin screen only) -> admin-only
        r1 = self._post("/camera/setPresetLabel", {"id": 0, "token": "1", "label": "x"},
                        t, ck + "; " + auth, referer="http://x/camera")
        self.assertEqual(json.loads(r1.body).get("error"), "Geen rechten")
        # setStreamPublish IS called by camera.js -> allowed for the camera role.
        # Stub the device call so we test the authz boundary, not the network.
        settings.cameras[0].set_stream_publish = lambda enable: True
        r2 = self._post("/camera/setStreamPublish", {"id": 0, "publish": True},
                        t, ck + "; " + auth, referer="http://x/camera")
        self.assertNotIn("Geen rechten", r2.body.decode())
        self.assertTrue(json.loads(r2.body).get("success"))

    def test_admin_can_set_preset_label(self):
        # restore() seeds default cameras, so id 0 exists; set_preset_label is a
        # local (non-network) config write -> succeeds for an admin.
        t, ck = self._prime()
        auth, _ = self._login("admin", "AdminPw", t, ck)
        r = self._post("/camera/setPresetLabel", {"id": 0, "token": "1", "label": "Kansel"},
                       t, ck + "; " + auth)
        self.assertTrue(json.loads(r.body).get("success"))

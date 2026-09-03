"""Regression tests for the camera-role -> admin privilege escalation.

Root cause: usernames were not unique and authorization resolves a user by the
FIRST username match, while setUser (login-only) let a user rename themselves to
collide with 'admin'. A camera user could then re-login against their own dup
entry and be treated as the real admin. These tests lock the fix.
"""
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


class Escalation(AsyncHTTPTestCase):
    def get_app(self):
        return appmod.make_app(internal=False)

    def setUp(self):
        super().setUp()
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

    def _login(self, u, p, t, ck, referer="http://x/camera"):
        r = self._post("/login/login", {"username": u, "password": p}, t, ck, referer)
        return _auth(r.headers), json.loads(r.body)

    # ---- the exploit must be blocked ----
    def test_camera_user_cannot_seize_admin_username(self):
        t, ck = self._prime()
        auth_cam, resp = self._login("cam", "CamPw", t, ck)
        self.assertTrue(resp["success"])

        r = self._post("/login/setUser", {"username": "admin", "password": "pwned"},
                       t, ck + "; " + auth_cam, referer="http://x/camera")
        self.assertEqual(json.loads(r.body).get("success"), False)

        # no duplicate 'admin' entry was created
        self.assertEqual(len([u for u in settings.users if u.username == "admin"]), 1)
        # the camera user still owns their original name
        self.assertIn("cam", [u.username for u in settings.users])

        # and the attacker cannot log in as admin with their chosen password
        _, resp2 = self._login("admin", "pwned", t, ck)
        self.assertFalse(resp2.get("success"))

    def test_setUsers_rejects_duplicate_usernames(self):
        t, ck = self._prime()
        auth, _ = self._login("admin", "AdminPw", t, ck, referer="http://x/")
        r = self._post("/login/setUsers", {"users": [
            {"username": "bob", "password": "p1", "admin": True, "camera": True},
            {"username": "bob", "password": "p2", "admin": False, "camera": True},
        ]}, t, ck + "; " + auth)
        self.assertEqual(json.loads(r.body).get("success"), False)
        # the existing user list is left untouched
        self.assertEqual(sorted(u.username for u in settings.users), ["admin", "cam"])

    # ---- legitimate behaviour must still work ----
    def test_legit_self_rename_succeeds_and_keeps_session(self):
        t, ck = self._prime()
        auth_cam, _ = self._login("cam", "CamPw", t, ck)
        r = self._post("/login/setUser", {"username": "cam2", "password": "CamPw2"},
                       t, ck + "; " + auth_cam, referer="http://x/camera")
        self.assertTrue(json.loads(r.body).get("success"))
        names = [u.username for u in settings.users]
        self.assertIn("cam2", names)
        self.assertNotIn("cam", names)
        # the session cookie was re-issued, so the renamed user is still logged in
        new_auth = _auth(r.headers)
        self.assertIsNotNone(new_auth)
        r2 = self._post("/camera/getCameras", {}, t, ck + "; " + new_auth,
                        referer="http://x/camera")
        self.assertNotIn("Niet ingelogd", r2.body.decode())

    def test_forced_password_change_via_setUser_still_clears_gate(self):
        settings.restore()  # default admin/admin, must_change_password=True
        t, ck = self._prime()
        auth, resp = self._login("admin", "admin", t, ck, referer="http://x/")
        self.assertTrue(resp["success"])
        self.assertTrue(resp["must_change_password"])
        # gated before the change
        r = self._post("/general/getSettings", {}, t, ck + "; " + auth)
        self.assertEqual(json.loads(r.body).get("must_change_password"), True)
        # change password (same username) via the self-service endpoint
        r2 = self._post("/login/setUser", {"username": "admin", "password": "NewStrongPw"},
                        t, ck + "; " + auth, referer="http://x/")
        self.assertTrue(json.loads(r2.body).get("success"))
        new_auth = _auth(r2.headers) or auth
        # gate is now cleared and admin settings are reachable
        r3 = self._post("/general/getSettings", {}, t, ck + "; " + new_auth)
        body = json.loads(r3.body)
        self.assertNotEqual(body.get("must_change_password"), True)
        self.assertIn("title", body)

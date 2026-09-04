# python standard lib
import os
import sys
import signal
import subprocess
import logging
import math
import datetime as dt
import time
import json
from json import dumps
from pathlib import Path
#import traceback
from dataclasses import asdict
import asyncio
from copy import deepcopy

# external libs
import socketio
import tornado
import tornado.web
import tornado.ioloop

# import tornado.websocket

# internals
from audio_controller import settings, controller, user, loggers, gpio, psalmbord, fonts, __version__

here = Path(os.path.dirname(__file__)).resolve()
main_logger = logging.getLogger("main")


async def _run_blocking(func):
    """Run a blocking device-I/O callable off the IOLoop, so one slow or
    unreachable camera cannot stall the whole server -- all listening ports share
    a single event loop. (C: event-loop starvation DoS)

    Any exception is logged with its traceback to the 'main' log file before it is
    re-raised, so a failing camera/ONVIF call is debuggable even though the caller
    turns it into a {"success": false} response. No detail is returned to the
    client (that would leak internals); the full traceback goes to the log only."""
    try:
        return await tornado.ioloop.IOLoop.current().run_in_executor(None, func)
    except Exception:
        main_logger.exception("camera device call failed")
        raise


# Actions that manage accounts or move the whole settings blob (with its
# password hashes and cleartext camera/icecast credentials). These are the
# privilege-escalation, persistence and secret-exfiltration vectors, so they
# require login + admin even on the trusted loopback listener, where ordinary
# operator actions (routing, psalmbord, camera control) stay open. (S-H1)
_AUTH_ALWAYS_GENERAL = frozenset(
    {"uploadSettings", "downloadSettings", "restoreSettings", "downloadLog"}
)
_AUTH_ALWAYS_LOGIN = frozenset({"setUsers", "getUsers", "setUser"})

_LOCAL_HOSTNAMES = ("localhost", "127.0.0.1", "::1", "ip6-localhost")


def _host_is_local(host):
    """True if an HTTP Host header names a loopback address (S-M2). Strips an
    optional :port and IPv6 brackets. Used only to confirm loopback trust, so it
    fails closed for anything it cannot parse."""
    if not host:
        return False
    host = host.strip()
    # strip a trailing :port, but not the colons inside a bracketed IPv6 literal
    if host.startswith("["):
        host = host.split("]", 1)[0].lstrip("[")
    else:
        host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    return host.lower() in _LOCAL_HOSTNAMES


# --- simple in-memory login throttling (E: brute-force hardening) ---
# PBKDF2 already slows guessing; this adds a temporary lockout after repeated
# failures. State is per-process (one process serves all ports); a successful
# login clears it.
_LOGIN_MAX_FAILURES = 10
_LOGIN_LOCKOUT_SECONDS = 60
_login_failures = {}  # username -> [failure_count, locked_until_ts]


def _login_locked(username):
    rec = _login_failures.get(username)
    return bool(rec) and rec[1] > time.time()


def _login_record_failure(username):
    rec = _login_failures.get(username, [0, 0.0])
    rec[0] += 1
    if rec[0] >= _LOGIN_MAX_FAILURES:
        rec[1] = time.time() + _LOGIN_LOCKOUT_SECONDS
        rec[0] = 0
    _login_failures[username] = rec


def _login_reset(username):
    _login_failures.pop(username, None)


def _lockout_key(username, remote_ip):
    """Throttle key for a login attempt. Keyed on the client address, NOT the
    (attacker-supplied) username, so a flood of failures for `admin` cannot lock
    the real admin out from a different client (remote DoS). (S-M5)"""
    return remote_ip or "unknown"


class BaseHandler(tornado.web.RequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def prepare(self):
        # Ensure the _xsrf cookie is issued to the client. Tornado only sets it
        # when xsrf_token is accessed; without this the SPA/mobile app has no
        # token to send and every state-changing POST would 403 (S5).
        self.xsrf_token

    def body_to_json(self):
        body = self.request.body
        if not body:
            body = b"{}"
        try:
            return json.loads(body)
        except (json.JSONDecodeError, ValueError):
            # malformed request body -> treat as empty instead of crashing 500 (C5)
            return {}

    def set_default_headers(self):
        # App is served same-origin; do not advertise a wildcard CORS policy (S5).
        self.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS, HEAD, PUT")
        self.set_header(
            "Access-Control-Allow-Headers",
            "Origin, X-Requested-With, Content-Type, Accept, Authorization, X-Xsrftoken",
        )
        # defense-in-depth headers (F): stop MIME sniffing and cross-origin framing
        # (clickjacking). A full CSP is intentionally not set here because the
        # camera page must load media from the camera device's own origin.
        self.set_header("X-Content-Type-Options", "nosniff")
        self.set_header("X-Frame-Options", "SAMEORIGIN")
        self.set_header("Referrer-Policy", "same-origin")

    def get_current_user(self):
        """Overrides method, gets called ones when accessing 'self.current_user'"""
        r = self.get_secure_cookie("audio_controller_user")
        if r is not None:
            return r.decode("utf-8")
        return r

    def set_cookie_username(self, username: str = ""):
        # httponly: the auth cookie is used server-side only, so keeping it out of
        # document.cookie limits session theft via any XSS; samesite=Lax is extra
        # CSRF hardening. (No secure=True: the app is served over plain HTTP.)
        self.set_secure_cookie("audio_controller_user", username.encode("utf-8"),
                               httponly=True, samesite="Lax")

    def logged_in(self):
        """Return True if user is logged in, False otherwise."""
        return bool(self.current_user)

    def login_required(self):
        """Check if login is required, which is always except when request comes from localhost"""
        return not self.is_localhost()

    def is_localhost(self):
        """Return True only for a loopback client on the trusted internal listener.
        Trust is decided by the app this handler runs in (set per listening port
        in make_app) AND the socket peer address — NOT by the client-controlled
        Host header (S4). The remote_ip comes straight from the socket (xheaders
        is off), so it cannot be spoofed via X-Real-IP/X-Forwarded-For. The
        internal port is LAN-reachable for the psalmbord, so a LAN client here
        gets the same login wall as the external port."""
        if not self.application.settings.get("internal", False):
            return False
        if self.request.remote_ip not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            return False
        # DNS-rebinding defence (S-M2): the kiosk browser runs on the Pi, so a
        # page an attacker lures it to connects from a loopback peer but carries
        # the attacker's Host header. Require the Host to be a loopback name too,
        # so a rebound request (foreign Host) falls back to the login wall.
        return _host_is_local(self.request.host)

    def write_login_exception(self):
        self.write(dumps({"LoginException": "Please login first"}))

    def must_change_password(self):
        """True if the logged-in user still has to set a new password before doing
        anything else (forced password change on first login)."""
        if not self.current_user:
            return False
        for usr in settings.users:
            if usr.username == self.current_user:
                return bool(usr.must_change_password)
        return False

    def current_user_is_admin(self):
        """True if the logged-in user has the admin role (used to gate system/config
        actions). On the trusted local port there is no user; callers guard with
        login_required() so that path stays open."""
        if not self.current_user:
            return False
        for usr in settings.users:
            if usr.username == self.current_user:
                return bool(usr.admin)
        return False


def get_action(path: str):
    """get action from path, where path is assumed to be '/{controller}/{action}.*'"""
    items = path.lstrip("/").split("/")
    if len(items) > 1:
        return items[1]
    return None


def get_js_filename():
    """Rename main.js to an unique file name, to force reload. Return latest file renamed from main.js."""
    js_dir = here.parent / "static" / "js"
    names = os.listdir(str(js_dir))
    names = [n for n in names if n.startswith("main") and n.endswith(".js")]
    if "main.js" in names:
        for n in names:
            if n != "main.js":
                os.remove(js_dir / n)
        new_name = f"main-{int(time.time())}.js"
        os.rename(js_dir / "main.js", js_dir / new_name)
        return new_name
    else:
        return sorted(names)[-1]


class StaticFileHandler(tornado.web.StaticFileHandler):
    def set_extra_headers(self, path):
        # Allow the browser to cache but always revalidate (P2). Tornado sends an
        # ETag and answers a matching If-None-Match with 304/0 bytes, so an
        # unchanged asset is not re-downloaded. main-<ts>.js is already
        # content-addressed, so a stale bundle is never served after an update.
        self.set_header("Cache-Control", "no-cache")


class Main(BaseHandler):
    def get(self):
        self.render("index.html", title="Title", page="home", js_filename=get_js_filename(), version=__version__)

    def post(self):
        self.write("")


class Login(BaseHandler):
    def check_user(self, username, password):
        """Check if user has provided correct password to login"""
        if username is None or password is None:
            return False
        else:
            usr = self.get_user(username, password)
            if usr is not False and self.check_app(usr):
                return True
        return False
    
    def check_app(self, usr):
        referer = (self.request.headers.get('Referer') or '').rsplit("/", 1)[-1]  # guard missing Referer (avoid 500)

        return (usr.admin or (usr.camera and referer == "camera"))
    
    def get_user(self, username, password = None):
        for usr in settings.users:
            if username != usr.username:
                continue
            if password is None or user.verify_password(password, usr.password):
                # transparently upgrade a legacy unsalted hash to a salted one on
                # a successful password login (one-time, per user).
                if password is not None and user.is_legacy_hash(usr.password):
                    usr.password = user.hash_password(password)
                    settings.save()
                return usr
            return False
        # No such username. Verify against a fixed dummy hash so an unknown user
        # costs the same PBKDF2 work as a real one and timing cannot enumerate
        # usernames. (S-M5)
        if password is not None:
            user.verify_password(password, user.DUMMY_HASH)
        return False

    async def post(self):
        action = get_action(self.request.path)

        # User administration must not be reachable without authentication (S8).
        # login / logout / login_required stay open; the rest needs login, and
        # listing or modifying users needs admin.
        if action in _AUTH_ALWAYS_LOGIN:
            # account management always needs login, even on the loopback port (S-H1)
            if not self.logged_in():
                self.write(dumps({"success": False, "LoginException": "Please login first"}))
                return
            if action in ("setUsers", "getUsers"):
                me = self.get_user(self.current_user) if self.current_user else False
                if me is False or not me.admin:
                    self.write(dumps({"success": False, "error": "Geen rechten"}))
                    return
                if self.must_change_password():
                    self.write(dumps({"success": False, "must_change_password": True}))
                    return

        if action == "login_required":
            self.write(dumps({"login_required": self.login_required()}))
            return

        def write_users():
            # Never expose password hashes to the client (D). The admin grid does
            # not prefill the password field; a blank password on the way back
            # means "keep existing" (see settings.update_users).
            out = []
            for obj in settings.users:
                d = asdict(obj)
                d["password"] = ""
                out.append(d)
            self.write(dumps(out))

        if action == "login":
            # check if already logged in (reading cookie)
            if self.current_user:  # not None and not empty string
                usr = self.get_user(self.current_user)
                if usr is not False and self.check_app(usr):
                    return self.write(dumps({"success": True, "username": self.current_user,
                                             "must_change_password": bool(usr.must_change_password)}))

            # else: try login if arguments are provided
            args = self.body_to_json()
            # if 'username' in args and 'password' in args:
            username = str(args.get("username"))
            password = str(args.get("password"))
            # brute-force throttling on the external port, keyed on the client
            # address so it cannot be abused to lock the admin account (E, S-M5)
            lock_key = _lockout_key(username, self.request.remote_ip)
            if self.login_required() and _login_locked(lock_key):
                msg = f"Login temporarily locked for client {self.request.remote_ip}"
                print(msg)
                main_logger.info(msg)
                self.write(dumps({"success": False,
                                  "error": "Te veel mislukte pogingen, probeer het later opnieuw"}))
                return
            if self.check_user(username, password):
                _login_reset(lock_key)
                msg = f"Login user {username}"
                print(msg)
                main_logger.info(msg)
                self.set_cookie_username(username)  # assumes unique usernames
                usr = self.get_user(username)
                self.write(dumps({"success": True,
                                  "must_change_password": bool(usr and usr.must_change_password)}))
            else:
                _login_record_failure(lock_key)
                msg = f"Login failed for user {username}"
                print(msg)
                main_logger.info(msg)
                self.write(dumps({
                    "success": False,
                    #"error": msg
                }))

        elif action == "logout":
            # remove cookie user
            self.set_cookie_username("")
            self.write(dumps({"success": True}))
            # self.redirect_relative("/")  # not used, implemented client side

        elif action == 'setUsers':
            args = self.body_to_json()
            users = args.get("users", [])
            try:
                settings.update_users(users)
            except Exception:
                # e.g. duplicate usernames are rejected by update_users
                self.write(dumps({"success": False, "error": "Ongeldige gebruikerslijst"}))
                return
            write_users()
            await notify_change()

        elif action == 'setUser':
            args = self.body_to_json()
            new_username = str(args.get("username", ""))
            new_password = str(args.get("password", ""))
            if not new_username or not new_password:
                self.write(dumps({"success": False}))
                return

            # Reject weak/default passwords so the forced first-login change (and
            # any self-service change) cannot re-set the shipped default. (E)
            if new_password.lower() in ("admin", "password") or new_password == new_username:
                self.write(dumps({"success": False,
                                  "error": "Kies een sterker wachtwoord"}))
                return

            # A user may only rename to a name not already owned by a DIFFERENT
            # account. Authorization resolves a user by username (first match), so
            # a duplicate would bind this session to another (possibly admin) row
            # -> privilege escalation. Fail closed. (security)
            for usr in settings.users:
                if usr.username == new_username and usr.username != self.current_user:
                    self.write(dumps({"success": False, "error": "Gebruikersnaam bestaat al"}))
                    return

            users = deepcopy(settings.users)
            for usr in users:
                if usr.username == self.current_user:
                    usr.username = new_username
                    usr.password = new_password

            try:
                settings.update_users([vars(u) for u in users])
                # keep the session valid after a self-rename (cookie holds the name)
                self.set_cookie_username(new_username)
                result = {"success": True}
            except Exception:
                result = {"success": False}
            self.write(dumps(result))
            await notify_change()

        elif action == "getUsers":
            write_users()
            return


class General(BaseHandler):
    async def post(self):
        action = get_action(self.request.path)

        # Account/whole-config actions require login even on the trusted loopback
        # listener (S-H1); ordinary operator actions keep the local no-login trust.
        force_auth = action in _AUTH_ALWAYS_GENERAL

        if (self.login_required() or force_auth) and not self.logged_in():
            self.write(dumps({"success": False}))
            return

        # system/config actions are admin-only; a camera-only session must not
        # reboot, change routing or upload settings (privilege escalation) (S9)
        if (self.login_required() or force_auth) and not self.current_user_is_admin():
            self.write(dumps({"success": False, "error": "Geen rechten"}))
            return

        if (self.login_required() or force_auth) and self.must_change_password():
            self.write(dumps({"success": False, "must_change_password": True}))
            return

        def write_settings():
            self.write(dumps(asdict(settings.settings)))

        if action == "restoreSettings":
            settings.restore()
            write_settings()
            return

        elif action == "getSettings":
            write_settings()
            return

        elif action == "setSettings":
            args = self.body_to_json()
            settings.update_settings(args)
            controller.set_routes()
            loggers.enable(settings.settings.enable_logging)
            write_settings()
            await notify_change()
            return

        elif action == "downloadLog":
            self.write(loggers.get_logs_as_binary())
            return

        elif action == "ifconfig":
            self.write(subprocess.run(["ifconfig"], capture_output=True, text=True).stdout)
            return

        elif action == "reboot":
            subprocess.run(["shutdown", "-r", "now"])
            return

        elif action == "shutdown":
            subprocess.run(["shutdown", "now"])
            return

        elif action == "downloadSettings":
            self.write(settings.get_binary())
            return

        elif action == "uploadSettings":
            file_content = self.request.files["file"][0]["body"]
            settings.set_binary(file_content)
            self.write(dumps({"success": True}))
            return

        elif action == "test_gpio":
            if gpio.is_enabled:
                await gpio.test_async()
            return

        # PSALMBORD
        elif action == "getPsalmbord":
            self.write(dumps(asdict(settings.pb)))
            return

        elif action == "setPsalmbord":
            args = self.body_to_json()
            settings.pb.update_psalmbord(
                args["fontfamily"], args["fontsize"], args["fontweight"], args["active"], args["screens"], args["refreshrate"]
            )
            self.write(dumps(asdict(settings.pb)))
            return


class Audio(BaseHandler):
    async def post(self):
        action = get_action(self.request.path)

        # Audio routing endpoints (setSources/setDestinations) are state-changing;
        # require login on the external port, same as General (S7 - was unguarded).
        if self.login_required() and not self.logged_in():
            self.write(dumps({"success": False}))
            return

        # routing configuration is admin-only (S9)
        if self.login_required() and not self.current_user_is_admin():
            self.write(dumps({"success": False, "error": "Geen rechten"}))
            return

        if self.login_required() and self.must_change_password():
            self.write(dumps({"success": False, "must_change_password": True}))
            return

        def write_sources():
            self.write(dumps([asdict(obj) for obj in settings.sources]))

        def write_destinations():
            self.write(dumps([asdict(obj) for obj in settings.destinations]))

        if action == "connected":
            if controller.itec.serial is None:
                raise tornado.web.HTTPError(503)  # 503 = Dienst niet beschikbaar
            self.write(dumps({"success": True}))
            return

        elif action == "getSources":
            write_sources()
            return

        elif action == "setSources":
            args = self.body_to_json()
            sources = args.get("sources", [])
            settings.update_sources(sources)
            controller.set_routes()
            write_sources()
            await notify_change()
            return

        elif action == "getDestinations":
            write_destinations()
            return

        elif action == "setDestinations":
            args = self.body_to_json()
            destinations = args.get("destinations", [])
            settings.update_destinations(destinations)
            controller.set_routes()
            write_destinations()
            await notify_change()
            return

        elif action == "getInputLevels":
            levels = controller.config.current_levels
            self.write(dumps(levels))
            return

        elif action == "soundcards":
            aplay = subprocess.run(["aplay", "-l"], capture_output=True, text=True).stdout
            arecord = subprocess.run(["arecord", "-l"], capture_output=True, text=True).stdout
            self.write(f"{aplay}\n{arecord}")
            return

        elif action == "getRoutes":
            self.write(controller.get_routes())
            return


class CameraApp(tornado.web.RequestHandler):
    def prepare(self):
        # issue the _xsrf cookie so camera.js can send it on its POSTs (S5)
        self.xsrf_token

    def get(self):
        # font-family is rendered into a <style> block on this unauthenticated
        # page; only an allowlisted font name may pass, otherwise a stored bad
        # value could inject CSS. Fall back to a safe default. (S-M7)
        font = 'Segoe UI'
        if settings.settings.enable_psalmbord and fonts.validate_font_name(settings.pb.fontfamily):
            font = settings.pb.fontfamily

        if settings.settings.enable_camera:
            self.render("camera.html", title=settings.settings.title, font=font)
        else:
            html = """<!DOCTYPE html><html><body style="background-color: black;"></body></html>"""
            self.write(html)

class Camera(BaseHandler):
    async def post(self):
        action = get_action(self.request.path)

        if self.login_required() and not self.logged_in():
            self.write(dumps({
                "success": False,
                "error": "Niet ingelogd"
            }))
            return

        if self.login_required() and self.must_change_password():
            self.write(dumps({"success": False, "must_change_password": True,
                              "error": "Wachtwoord wijzigen vereist"}))
            return

        def cam_dict(obj):
            d = obj.to_dict()
            # ONVIF credentials are only for admins (the settings grid); a
            # camera-only session lists/controls cameras but must not read the
            # stored passwords (S9)
            if self.login_required() and not self.current_user_is_admin():
                d.pop("username", None)
                d.pop("password", None)
                d.pop("url_intern", None)
                d.pop("port_onvif", None)
            return d

        def write_cameras(setCameras = False):
            if setCameras:
                self.write(dumps([cam_dict(obj) for obj in settings.cameras]))
            else:
                self.write(dumps({
                    "success": True,
                    "cameras": [cam_dict(obj) for obj in settings.cameras]
                }))

        # The camera-role user may do everything the camera app (camera.js) sends:
        # get/goto presets, PTZ (moveStart/moveStop), live, get/setStreamPublish
        # and reboot. Only actions that are NOT in camera.js are admin-only:
        # setCameras (add cameras / IPs / ONVIF credentials) and setPresetLabel
        # (rename a preset) -- both live in the admin settings screen.
        if action in ("setCameras", "setPresetLabel"):
            if self.login_required() and not self.current_user_is_admin():
                self.write(dumps({"success": False, "error": "Geen rechten"}))
                return

        if action == "getCameras":
            write_cameras()
            return

        elif action == "getPresets":
            result = {
                "err": None,
                "msg": None,
                "presets": []
            }

            try:
                args = self.body_to_json()
                cam = settings.cameras[args['id']]
                def _work():
                    cam.connect()
                    return [asdict(p) for p in cam.load_presets()]
                result['presets'] = await _run_blocking(_work)
            except ConnectionError as err:
                result['err'] = 'connection'
                #result['msg'] = str(err)
            except Exception as err:
                result['err'] = 'fout'
                #result['msg'] = str(err)

            self.write(dumps(result))
            return

        elif action == "getActivePreset":
            # return proper JSON with a json content-type (F: was raw text/html)
            self.set_header("Content-Type", "application/json")
            try:
                args = self.body_to_json()
                cam = settings.cameras[args['id']]
                self.write(dumps(cam.active))
            except Exception as err:
                self.write(dumps(""))

        elif action == "gotoPreset":
            try:
                args = self.body_to_json()
                cam = settings.cameras[args['id']]
                cam.active = str(args['preset'])
                def _work():
                    cam.goto_preset(cam.active)
                    settings.save()
                await _run_blocking(_work)
                result = {
                    "success": True
                }

            except Exception as err:
                result = {
                    "success": False,
                    #"error": str(err)
                }
            self.write(dumps(result))
            return

        elif action == "setPresetLabel":
            try:
                args = self.body_to_json()
                cam = settings.cameras[args['id']]
                token = str(args['token'])
                label = str(args['label'])

                cam.set_preset_label(token, label)
                settings.save()

                result = {
                    "success": True
                }

            except Exception:
                main_logger.exception("setPresetLabel failed")
                result = {
                    "success": False,
                }
            self.write(dumps(result))
            return

        elif action == "getLive":
            try:
                args = self.body_to_json()
                cam = settings.cameras[args['id']]
                live = await _run_blocking(cam.get_stream_uri)
                result = {
                    "success": True,
                    "uri": live
                }

            except Exception as err:
                result = {
                    "success": False,
                    #"error": str(err)
                }
            self.write(dumps(result))
            return

        elif action == "moveStart":
            try:
                args = self.body_to_json()
                cam = settings.cameras[args['id']]
                cam.active = "0"
                direction = args["direction"]
                def _work():
                    cam.set_focus_mode()
                    cam.move_direction(direction)
                await _run_blocking(_work)
                result = {
                    "success": True,
                }
            except Exception as err:
                result = {
                    "success": False,
                    #"error": str(err)
                }
            self.write(dumps(result))
            return

        elif action == "moveStop":
            try:
                args = self.body_to_json()
                cam = settings.cameras[args['id']]
                cam.active = "0"
                await _run_blocking(cam.move_stop)
                result = {
                    "success": True,
                }
            except Exception as err:
                result = {
                    "success": False,
                    #"error": str(err)
                }
            self.write(dumps(result))
            return

        elif action == "setCameras":
            args = self.body_to_json()
            cameras = args["cameras"]
            settings.update_cameras(cameras)
            write_cameras(True)
            await notify_change()

        elif action == "getStreamPublish":
            try:
                args = self.body_to_json()
                cam = settings.cameras[args['id']]
                result = {
                    "success": await _run_blocking(cam.get_stream_publish)
                }
            except Exception as err:
                result = {
                    "success": False,
                    #"error": str(err)
                }
            self.write(dumps(result))
            return

        elif action == "setStreamPublish":
            try:
                args = self.body_to_json()
                cam = settings.cameras[args['id']]
                publish = args['publish']
                await _run_blocking(lambda: cam.set_stream_publish(publish))
                result = {
                    "success": True,
                }
            except Exception as err:
                result = {
                    "success": False,
                    #"error": str(err)
                }
            self.write(dumps(result))
            return

        elif action == "reboot":
            try:
                args = self.body_to_json()
                cam = settings.cameras[args['id']]
                cam.active = "0"
                def _work():
                    settings.save()
                    cam.reboot()
                await _run_blocking(_work)
                result = {
                    "success": True,
                }
            except Exception as err:
                result = {
                    "success": False,
                    #"error": str(err)
                }
            self.write(dumps(result))
            return

class Psalmbord(BaseHandler):
    def check_xsrf_cookie(self):
        # The /psalmbord POST is read-only (returns board html/state only), so it
        # is exempt from XSRF. This lets the kiosk board keep polling without a
        # token (S5). State-changing endpoints (General/Login/Camera) stay protected.
        pass

    def psalmbord_login_required(self):
        """The board is free on the internal listener (LAN kiosk screens reach
        it without login); the external listener requires login. The remote_ip
        plays no role here - trust for the board follows the port alone."""
        return not self.application.settings.get("internal", False)

    def get_css(self):
        # Coerce to int: fontsize/fontweight are int-cast on the setPsalmbord
        # path, but a crafted settings *import* can store an arbitrary string.
        # Forcing int here prevents breaking out of the inline <style> and
        # injecting script on the public board (defense in depth for S3).
        try:
            fs = int(settings.pb.fontsize)
        except (TypeError, ValueError):
            fs = psalmbord.default_fontsize
        try:
            fw = int(settings.pb.fontweight)
        except (TypeError, ValueError):
            fw = psalmbord.default_fontweight
        return f"html {{ --regels: {fs}; }} \n .font_weight {{ font-weight: {fw}; }}"

    def get(self):
        if self.psalmbord_login_required() and not self.logged_in():
            self.redirect("/")
            return
        if settings.settings.enable_psalmbord:
            self.render("psalmbord.html", css=self.get_css())
        else:
            html = """<!DOCTYPE html><html><body style="background-color: black;"></body></html>"""
            self.write(html)

    def post(self):
        if self.psalmbord_login_required() and not self.logged_in():
            self.set_status(403)
            self.write_login_exception()
            return
        if settings.settings.enable_psalmbord:
            kwargs = self.body_to_json()
            if kwargs.get("html"):
                if kwargs.get("html_hash") != settings.pb.html_hash:
                    result = {
                        "html": settings.pb.psalmbord_as_html(),
                        "html_hash": settings.pb.html_hash,
                        "css": self.get_css(),
                        "refreshrate": settings.pb.refreshrate
                    }
                else:
                    result = {
                        "css": self.get_css(),
                        "refreshrate": settings.pb.refreshrate
                    }
                
                self.write(dumps(result))
            else:
                self.write(dumps(asdict(settings.pb)))
        else:
            self.write(dumps(asdict(psalmbord.Psalmbord())))


async def notify_change():
    """Notify clients that there has been changed something, like a setting"""
    for server in websocket_servers:
        await server.emit("event", "change")


websocket_servers: socketio.Server = []


def websocket_handlers(sio: socketio.Server):
    if sio in websocket_servers:
        return

    # multiple (tornado) applications run on different ports, so for each a server exists
    websocket_servers.append(sio)

    @sio.event
    async def connect(sid, environ):
        handler = environ["tornado.handler"]
        handler = BaseHandler(handler.application, handler.request)
        if handler.login_required() and not handler.logged_in():
            print("Unauthorized websocket usage, websocket closed.")
            return False
        # print('connect ', sid)

    @sio.event
    def disconnect(sid):
        pass  # print('disconnect ', sid)

    @sio.event
    def event(sid, data):
        pass  # print("event catched")
        # print(data)

    # @sio.on('my custom event')
    # def another_event(sid, data):
    #     print("custom event catched")

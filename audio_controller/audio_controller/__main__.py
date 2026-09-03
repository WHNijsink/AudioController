# python standard lib
import os
import sys
import time
from pathlib import Path
import traceback
import argparse
import asyncio
import logging
import subprocess
import re

# externals
import tornado.ioloop
import tornado.web
import socketio

# internals
from . import loggers  # load logging first, before other modules
from . import settings
from .handlers import handlers
from . import stream
from . import itec
from . import controller
from . import user
from . import gpio
from . import psalmbord

here = Path(os.path.dirname(__file__)).resolve()
main_logger = logging.getLogger("main")

_VOLUME_RE = re.compile(r"^\d+%?$")

# (port, bind address, internal) per listener. 5000 is the internal port: kiosk
# screens on the LAN reach /psalmbord without login and loopback clients keep
# full no-login trust (see BaseHandler.is_localhost). 8080 is the external port:
# login required for everything. The router must only forward 8080.
PORT_ADDRESS = [(5000, "0.0.0.0", True), (8080, "0.0.0.0", False)]


def valid_volume(raw) -> str:
    """Return a validated ALSA volume like '80%'. Defaults to '100%' for anything unsafe (S6)."""
    if not isinstance(raw, str):
        return "100%"
    raw = raw.strip()
    if not _VOLUME_RE.match(raw):
        return "100%"
    return raw if raw.endswith("%") else raw + "%"


def make_app(internal: bool = False):
    """Build the app for one listener. internal=True marks the trusted internal
    port (5000): loopback clients get full no-login trust and the psalmbord is
    served without login to the whole LAN. internal=False is the external port
    (8080): login required for everything, including the psalmbord."""
    template_dir = here / "views"
    static_dir = here / "static"
    settings = dict(
        debug=False,
        autoreload=False,
        cookie_secret=user.get_cookie_secret(),
        template_path=str(template_dir),
        internal=internal,
        xsrf_cookies=True,
    )

    sio = socketio.AsyncServer(async_mode="tornado")
    handlers.websocket_handlers(sio)

    _SioHandler = socketio.get_tornado_handler(sio)

    class WebSocketHandler(_SioHandler):
        def check_xsrf_cookie(self):
            # Socket.IO's long-polling transport POSTs carry no _xsrf token.
            # Exempt them: the handshake is a GET, engine.io already enforces a
            # same-origin check_origin, and the `connect` event runs the
            # login_required() gate. (S5)
            pass

    _handlers = [
        ("/", handlers.Main),
        ("/login/.*", handlers.Login),
        ("/general/.*", handlers.General),
        ("/audio/.*", handlers.Audio),
        ("/psalmbord", handlers.Psalmbord),
        ("/camera", handlers.CameraApp),
        ("/camera/.*", handlers.Camera),
        ("/(favicon.ico)", handlers.StaticFileHandler, {"path": str(static_dir)}),
        ("/static/(.*)", handlers.StaticFileHandler, {"path": str(static_dir)}),
        ("/websocket/", WebSocketHandler),
    ]

    return tornado.web.Application(handlers=_handlers, **settings)


def schedule_tasks(loop: asyncio.BaseEventLoop):
    """Add additional async tasks to the same event-loop as the running webserver."""
    if settings.settings.enable_audio:
        loop.create_task(controller.scan_ports())
        loop.create_task(controller.auto_switch())
    loop.create_task(set_gpio())


def init_system(args):
    """initialize system"""
    import getpass

    volume = "100%"
    try:
        if "--volume" in args:
            volume = valid_volume(args[args.index("--volume") + 1])
    except (ValueError, IndexError):
        pass
    # set the output volume to a fixed percentage (no shell; args are a list -> no injection) (S6)
    try:
        result = subprocess.run(["amixer", "-M", "sset", "PCM", volume],
                                capture_output=True, text=True)
        msg = result.stdout
    except FileNotFoundError:
        msg = "amixer not available"
    print(msg)
    main_logger.info(msg)

    # log user
    msg = f"Init system - user: {getpass.getuser()}"
    print(msg)
    main_logger.info(msg)


async def set_gpio():
    # activate leds on warnings / errors
    if gpio.is_enabled:
        gpio.power_button.handle_reboot = lambda: subprocess.run(["shutdown", "-r", "now"])
        interval_seconds = 4
        while True:
            try:
                connected = False
                # if there is at least 1 destination selected, connected becomes True
                if settings.settings.enable_audio and settings.settings.connect_source_destination:
                    for dest in settings.destinations:
                        if dest.enabled and dest.selected:
                            connected = True
                            break
                gpio.source_and_destination_connected(connected)
            except Exception as e:
                main_logger.warning(f"set_gpio error: {e}")
            await asyncio.sleep(interval_seconds)


def main():
    args = sys.argv[1:]
    try:
        init_system(args)
        # Cap request bodies so an unauthenticated client cannot exhaust memory on
        # the Pi via a huge POST (e.g. to /psalmbord). Settings uploads are a few
        # KB; 5 MB is generous. (DoS hardening)
        max_body_size = 5 * 1024 * 1024
        for port, address, internal in PORT_ADDRESS:
            app = make_app(internal)
            app.listen(port=port, address=address, max_body_size=max_body_size)
            msg = f"Listening on {address}:{port}"
            print(msg)
            main_logger.info(msg)

        ioloop = tornado.ioloop.IOLoop.current()
        schedule_tasks(ioloop.asyncio_loop)
        if settings.settings.enable_audio:
            controller.set_routes()
        if not settings.settings.enable_logging:
            main_logger.info("Logging is disabled")
            loggers.enable(False)
        ioloop.start()
    except Exception:
        msg = f"Application stopped with exception: \n{traceback.format_exc()}"
        print(msg)
        main_logger.error(msg)
    except KeyboardInterrupt:
        msg = "Application stopped"
        print(msg)
        main_logger.info(msg)


if __name__ == "__main__":
    stream.test()
    itec.test()
    settings.test()
    user.test()
    main()

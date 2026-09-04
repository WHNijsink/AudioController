"""Trust follows the port AND the socket peer address.

The internal listener (5000) is reachable from the LAN so kiosk screens can
show /psalmbord without login. Full no-login trust must therefore be limited
to genuine loopback clients; a LAN client on 5000 gets the same login wall as
the external listener (8080) for everything except the psalmbord.
"""
from types import SimpleNamespace

import tornado.httputil

from audio_controller.__main__ import make_app, PORT_ADDRESS
from audio_controller.handlers.handlers import BaseHandler, Psalmbord


def make_handler(app, remote_ip, cls=BaseHandler, host="localhost"):
    connection = SimpleNamespace(
        context=SimpleNamespace(remote_ip=remote_ip), set_close_callback=lambda cb: None
    )
    request = tornado.httputil.HTTPServerRequest(
        method="GET", uri="/", version="HTTP/1.1", host=host, connection=connection
    )
    return cls(app, request)


def test_internal_app_loopback_client_is_trusted():
    handler = make_handler(make_app(True), "127.0.0.1")
    assert handler.is_localhost() is True
    assert handler.login_required() is False


def test_internal_app_lan_client_requires_login():
    handler = make_handler(make_app(True), "192.168.2.50")
    assert handler.is_localhost() is False
    assert handler.login_required() is True


def test_internal_app_loopback_with_foreign_host_is_not_trusted():
    # DNS-rebinding defence (S-M2): the kiosk browser runs on the Pi, so a page
    # it loads from an attacker connects to 127.0.0.1 (a loopback peer) but sends
    # the attacker's Host header. Trust must require BOTH a loopback peer AND a
    # local Host, so a rebound request (foreign Host) gets the login wall.
    handler = make_handler(make_app(True), "127.0.0.1", host="evil.example.com")
    assert handler.is_localhost() is False
    assert handler.login_required() is True


def test_internal_app_loopback_with_local_host_and_port_is_trusted():
    # The real kiosk uses http://localhost:5000 / http://127.0.0.1:5000; a Host
    # with a port must still be recognised as local.
    for host in ("localhost:5000", "127.0.0.1:5000", "localhost", "[::1]:5000"):
        handler = make_handler(make_app(True), "127.0.0.1", host=host)
        assert handler.is_localhost() is True, host


def test_external_app_loopback_client_requires_login():
    handler = make_handler(make_app(False), "127.0.0.1")
    assert handler.is_localhost() is False
    assert handler.login_required() is True


def test_internal_app_lan_client_gets_psalmbord_without_login():
    handler = make_handler(make_app(True), "192.168.2.50", cls=Psalmbord)
    assert handler.psalmbord_login_required() is False


def test_external_app_psalmbord_requires_login():
    handler = make_handler(make_app(False), "127.0.0.1", cls=Psalmbord)
    assert handler.psalmbord_login_required() is True


def test_listener_wiring():
    # 5000: LAN-reachable internal listener (kiosk screens); 8080: external, login
    assert (5000, "0.0.0.0", True) in PORT_ADDRESS
    assert (8080, "0.0.0.0", False) in PORT_ADDRESS

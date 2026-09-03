__pragma__('alias', 'S', '$')  # to use jQuery library with 'S' instead of '$'

import random

import utils
from elements import Element, element, ElementWrapper, get_Element, get_elements, get_element
from pages import page_admin, page_overview, page_psalmbord, page_camera
import dialogs

E = Element

home = ElementWrapper(get_element("#home"))
home.inner_html("Audio Regelaar")
home.element.onclick = lambda evt: utils.redirect_relative("")


def set_title(title):
    home.text(title)
    window.document.title = title


# fullscreen = ElementWrapper(get_element("#a_fullscreen"))
#fullscreen.element.onclick = lambda evt: click_fullscreen()

is_fullscreen = False


def click_fullscreen():
    global is_fullscreen
    if is_fullscreen:
        elem = window.document
        attrs = "exitFullscreen mozCancelFullScreen webkitExitFullscreen msExitFullscreen".split()
    else:
        elem = window.document.documentElement
        attrs = "requestFullscreen mozRequestFullScreen webkitRequestFullscreen msRequestFullscreen".split()
    for attr in attrs:
        if hasattr(elem, attr):
            elem[attr].call(elem)
            break
    is_fullscreen = not is_fullscreen


# menu handling, to show correct page
main_menu = ElementWrapper(get_element('#main_menu'))
main = ElementWrapper(get_element("#main_container"))
menu_items = []


class MenuItem(ElementWrapper):
    def __init__(self):
        super().__init__(element('li'))
        self.title = E('a').attr('class', 'nav-link').attr('href', '#')
        self.attr('class', 'nav-item').append(self.title)
        menu_items.append(self)
        self.active = False

    def set_title(self, title):
        self.title.inner_html(title)
        return self

    def activate(self, active: bool):
        self.active = active
        if active:
            self.element.classList.add("active")
        else:
            self.element.classList.remove("active")
        return self

    def onclick(self, evt):
        for mi in menu_items:
            mi.activate(False)
        self.activate(True)
        self.page.show()

    def set_page(self, page):
        self.page = page
        self.element.onclick = self.onclick
        return self


# optional, refresh after disconnect
# not used, but only on websocket disconnect


async def refresh_after_disconnect():
    disconnected = False
    while True:
        await utils.sleep(5)
        try:
            await utils.post(utils.get_url("general/ping"), {})
            if disconnected:
                console.log("ping success, now refresh")
                utils.redirect_relative("")
        except:
            disconnected = True
            console.log("ping failed")


# refresh_after_disconnect()

def setup_websocket():
    socket = io({'path': '/websocket'})

    disconnected = False

    def on_connect():
        console.log("websocket connect")
        if disconnected:
            # was disconnected previously, so lets refresh now
            utils.redirect_relative("")

    socket.on('connect', on_connect)

    async def on_disconnect():
        nonlocal disconnected
        disconnected = True
        get_element('#warning_connection_lost').style.display = ''

    socket.on('disconnect', on_disconnect)

    def on_event(data):
        if data == 'change':
            for mi in menu_items:
                if mi.active:
                    mi.page.refresh()
        else:
            console.log("unrecognised websocket event:")
            console.log(data)

    socket.on('event', on_event)

    # to send an event:
    #socket.emit('event', 'im a client')


logged_in = False


async def create_main_menu():
    settings = await utils.post(utils.get_url('general/getSettings'), {})
    set_title(settings['title'])


    if settings["enable_audio"]:
        main_menu.append(
            MenuItem().set_title("Geluid").set_page(page_overview.Page())
        )
    if settings["enable_psalmbord"]:
        main_menu.append(
            MenuItem().set_title("Psalmbord").set_page(page_psalmbord.Page())
        )
    if settings["enable_camera"]:
        main_menu.append(
            MenuItem().set_title("Camera").set_page(page_camera.Page())
        )
    main_menu.append(
        MenuItem().set_title("Instellingen").set_page(page_admin.Page())
    )

    login = await utils.post(utils.get_url('login/login_required'), {})
    if login['login_required']:
        main_menu.append(logout_button())


async def login_and_view():
    login_required = await utils.post(utils.get_url("login/login_required"))
    login_required = login_required['login_required']
    if login_required:
        await login()
    setup_websocket()
    await create_main_menu()
    menu_items[0].onclick()


login_and_view()


async def check_logged_in():
    nonlocal logged_in
    if logged_in:
        return True
    else:
        r = await utils.post(utils.get_url('login/login'), {})
        logged_in = r['success']
        return logged_in


async def enforce_change_if_needed():
    """ If the server marks the logged-in user as must_change_password, force a
    password change before the app can be used (forced change on first login). """
    r = await utils.post(utils.get_url('login/login'), {})
    if not r['success']:
        return
    must = ('must_change_password' in r) and r['must_change_password']
    if not must:
        return
    username = r['username'] if 'username' in r else ''
    while True:
        newpw = await dialogs.dialog_change_password.get_new_password()
        res = await utils.post(utils.get_url('login/setUser'),
                               {'username': username, 'password': newpw})
        if res['success']:
            dialogs.dialog_change_password.hide()
            return


async def login():
    """ While not logged in, show login dialog. """
    nonlocal logged_in
    await check_logged_in()
    # dialogs.dialog_login.hide_login_failed()
    while not logged_in:
        try:
            user = await dialogs.dialog_login.get_value()
            if user is not None:
                # x = await utils.post2(utils.get_url('login/login'), user)
                r = await utils.post(utils.get_url('login/login'), user)
                if r['success']:
                    # login succeeded
                    logged_in = True
                    dialogs.dialog_login.hide()
                    break
                else:
                    dialogs.dialog_login.show_login_failed(r['error'])
        except:
            await utils.sleep(0.1)
    await enforce_change_if_needed()


async def logout():
    """ """
    nonlocal logged_in
    logged_in = False
    r = await utils.post(utils.get_url('login/logout'), {})
    if r['success']:
        utils.redirect_relative("")


def logout_button():
    r = E('li').attr('class', 'nav-item').attr('style', 'position:absolute; top:1em; right:1em;').append(
        E('a').attr('class', 'nav-link').attr('style', 'line-height:10px;').inner_html('Logout')
    )
    r.element.onclick = lambda evt: logout()
    return r

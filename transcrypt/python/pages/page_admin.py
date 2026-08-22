__pragma__("alias", "S", "$")  # to use jQuery library with 'S' instead of '$'
import utils
from elements import Element, element, ElementWrapper, get_Element, get_elements, get_element
from pages import page_admin, page_overview
from layout import home, main, set_title
from paged_list import PagedList
from dialogs import dialog_confirm

E = Element


class AccordionItem(ElementWrapper):
    def __init__(self, heading_title):
        super().__init__(element("div"))
        self.arrow_down = E("span").attr("class", "fas fa-chevron-down")
        self.arrow_up = E("span").attr("class", "fas fa-chevron-up")
        self.arrow_up.element.style.display = "none"
        self.heading = (
            E("div")
            .attr("class", "accordion_head bg-dark text-white")
            .append(
                self.arrow_down,
                self.arrow_up,
                E("span").inner_html(" "),
                E("span").inner_html(heading_title),
            )
        )
        self.body = E("div").attr("class", "accordion_body")
        self.body.element.style.display = "none"
        self.append(self.heading, self.body)
        self.heading.element.onclick = self.show_hide
        self.refresh = lambda: None

    def show_hide(self, evt):
        S(self.arrow_up.element).toggle(0)
        S(self.arrow_down.element).toggle(0)
        S(self.body.element).toggle(200)


class Settings(AccordionItem):
    def __init__(self):
        super().__init__("Instellingen")
        input_title = E("input").attr("class", "form-control").attr("type", "text")
        input_nr_in_ports = E("input").attr("class", "form-control").attr("type", "number")
        input_nr_out_ports = E("input").attr("class", "form-control").attr("type", "number")
        input_port_in_stream = E("input").attr("class", "form-control").attr("type", "text")
        input_port_out_stream = E("input").attr("class", "form-control").attr("type", "text")
        show_button_connect = E("input").attr("class", "form-control").attr("type", "checkbox")
        show_button_mute_sound = E("input").attr("class", "form-control").attr("type", "checkbox")
        input_auto_switch = E("input").attr("class", "form-control").attr("type", "checkbox")
        input_timeout = E("input").attr("class", "form-control").attr("type", "number")
        input_enable_audio = E("input").attr("class", "form-control").attr("type", "checkbox")
        input_enable_psalmbord = E("input").attr("class", "form-control").attr("type", "checkbox")
        input_enable_camera = E("input").attr("class", "form-control").attr("type", "checkbox")
        input_enable_logging = E("input").attr("class", "form-control").attr("type", "checkbox")

        width_1 = "col-sm-5"
        width_2 = "col-sm-3"
        self.body.append(
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label").attr("class", "{} col-form-label".format(width_1)).inner_html("Algemeen").attr('style','font-weight:bold; font-size: initial;'),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label").attr("class", "{} col-form-label".format(width_1)).inner_html("Titel"),
                E("div").attr("class", "{}".format(width_2)).append(input_title),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label")
                .attr("class", "{} col-form-label".format(width_1))
                .inner_html("Geluid functie inschakelen"),
                E("div").attr("class", "{}".format(width_2)).append(input_enable_audio),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label")
                .attr("class", "{} col-form-label".format(width_1))
                .inner_html("Psalmbord functie inschakelen"),
                E("div").attr("class", "{}".format(width_2)).append(input_enable_psalmbord),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label")
                .attr("class", "{} col-form-label".format(width_1))
                .inner_html("Camera functie inschakelen"),
                E("div").attr("class", "{}".format(width_2)).append(input_enable_camera),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label").attr("class", "{} col-form-label".format(width_1)).inner_html("Logging inschakelen"),
                E("div").attr("class", "{}".format(width_2)).append(input_enable_logging),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label").attr("class", "{} col-form-label".format(width_1)).inner_html("Geluid").attr('style','font-weight:bold; font-size: initial;'),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label")
                .attr("class", "{} col-form-label".format(width_1))
                .inner_html("Toon knop 'Bron en bestemmingen verbinden'"),
                E("div").attr("class", "{}".format(width_2)).append(show_button_connect),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label").attr("class", "{} col-form-label".format(width_1)).inner_html("Toon knop 'Geluid aan'"),
                E("div").attr("class", "{}".format(width_2)).append(show_button_mute_sound),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label")
                .attr("class", "{} col-form-label".format(width_1))
                .inner_html("Toon knop 'Automatisch bron kiezen'"),
                E("div").attr("class", "{}".format(width_2)).append(input_auto_switch),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label")
                .attr("class", "{} col-form-label".format(width_1))
                .inner_html("Wachttijd (minuten) voor 'Automatisch bron kiezen'"),
                E("div").attr("class", "{}".format(width_2)).append(input_timeout),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label").attr("class", "{} col-form-label".format(width_1)).inner_html("Geluid: ITEC instellingen").attr('style','font-weight:bold; font-size: initial;'),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label").attr("class", "{} col-form-label".format(width_1)).inner_html("Aantal IN poorten"),
                E("div").attr("class", "{}".format(width_2)).append(input_nr_in_ports),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label").attr("class", "{} col-form-label".format(width_1)).inner_html("Aantal OUT poorten"),
                E("div").attr("class", "{}".format(width_2)).append(input_nr_out_ports),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label").attr("class", "{} col-form-label".format(width_1)).inner_html("IN poort externe bronnen"),
                E("div").attr("class", "{}".format(width_2)).append(input_port_in_stream),
            ),
            E("div")
            .attr("class", "form-group row")
            .append(
                E("label").attr("class", "{} col-form-label".format(width_1)).inner_html("OUT poort externe bestemmingen"),
                E("div").attr("class", "{}".format(width_2)).append(input_port_out_stream),
            ),
        )

        def get_inputs() -> dict:
            return {
                "title": input_title.element.value,
                "nr_IN_ports": input_nr_in_ports.element.value,
                "nr_OUT_ports": input_nr_out_ports.element.value,
                "port_IN_for_streams": input_port_in_stream.element.value,
                "port_OUT_to_stream": input_port_out_stream.element.value,
                "show_button_connect": show_button_connect.element.checked,
                "show_button_mute_sound": show_button_mute_sound.element.checked,
                "enable_option_auto_switch": input_auto_switch.element.checked,
                "timeout_auto_switch": input_timeout.element.value,
                "enable_audio": input_enable_audio.element.checked,
                "enable_psalmbord": input_enable_psalmbord.element.checked,
                "enable_camera": input_enable_camera.element.checked,
                "enable_logging": input_enable_logging.element.checked,
            }

        def set_inputs(settings: dict):
            input_title.element.value = settings["title"]
            input_nr_in_ports.element.value = settings["nr_IN_ports"]
            input_nr_out_ports.element.value = settings["nr_OUT_ports"]
            input_port_in_stream.element.value = settings["port_IN_for_streams"]
            input_port_out_stream.element.value = settings["port_OUT_to_stream"]
            show_button_connect.element.checked = settings["show_button_connect"]
            show_button_mute_sound.element.checked = settings["show_button_mute_sound"]
            input_auto_switch.element.checked = settings["enable_option_auto_switch"]
            input_timeout.element.value = settings["timeout_auto_switch"]
            input_enable_audio.element.checked = settings["enable_audio"]
            input_enable_psalmbord.element.checked = settings["enable_psalmbord"]
            input_enable_camera.element.checked = settings["enable_camera"]
            input_enable_logging.element.checked = settings["enable_logging"]

        async def initialize():
            self.settings = await utils.post(utils.get_url("general/getSettings"), {})
            set_inputs(self.settings)
            set_title(self.settings["title"])

        # initialize()

        async def onchange(evt):
            settings = get_inputs()
            self.settings = await utils.post(utils.get_url("general/setSettings"), settings)
            set_inputs(self.settings)

        input_title.element.onchange = onchange
        input_nr_in_ports.element.onchange = onchange
        input_nr_out_ports.element.onchange = onchange
        input_port_in_stream.element.onchange = onchange
        input_port_out_stream.element.onchange = onchange
        show_button_connect.element.onchange = onchange
        show_button_mute_sound.element.onchange = onchange
        input_auto_switch.element.onchange = onchange
        input_timeout.element.onchange = onchange
        input_enable_audio.element.onchange = onchange
        input_enable_psalmbord.element.onchange = onchange
        input_enable_camera.element.onchange = onchange
        input_enable_logging.element.onchange = onchange

        self.refresh = initialize


def source(name, enabled, port_url, scan_prio, db_level, selected):
    return {
        "name": name,
        "enabled": enabled,
        "port_url": port_url,
        "scan_prio": scan_prio,
        "db_level": db_level,
        "selected": selected,
    }


class Sources(AccordionItem):
    def __init__(self):
        super().__init__("Geluid - Bronnen")
        plist = PagedList(self.body.element, "").hide_count().disable_pagination()
        plist.get_styling().table_class("table borderless")

        def text_element(attr, item):
            r = E("input").attr("type", "text")
            r.element.value = item[attr]

            def onchange(evt):
                item[attr] = r.element.value
                save_changes()

            r.element.onchange = onchange
            return r.element

        def checkbox_element(attr, item):
            r = E("input").attr("type", "checkbox")
            r.element.checked = item[attr]

            def onchange(evt):
                item[attr] = r.element.checked
                save_changes()

            r.element.onchange = onchange
            return r.element

        plist.add_column("name", "Naam").item_to_element(text_element.bind(None, "name"))
        plist.add_column("enabled", "Actief").item_to_element(checkbox_element.bind(None, "enabled"))
        plist.add_column("port_url", "Poort / Url").item_to_element(text_element.bind(None, "port_url"))
        plist.add_column("scan_prio", "Prio bij automatisch schakelen").item_to_element(text_element.bind(None, "scan_prio"))  # .add_style('width: 100px; max-width:100px;')
        plist.add_column("db_level", "dB level threshold").item_to_element(text_element.bind(None, "db_level"))

        async def delete_item(item):
            self.sources.remove(item)
            self.sources = await utils.post(utils.get_url("audio/setSources"), {"sources": self.sources})
            plist.get_server().data = self.sources
            plist.refresh()

        async def save_changes():
            self.sources = await utils.post(utils.get_url("audio/setSources"), {"sources": self.sources})
            plist.get_server().data = self.sources
            plist.refresh()

        plist.add_button("delete", "", "btn btn-danger btn-sm").use_element(
            lambda item: E("i").attr("class", "fas fa-trash-alt")
        ).onclick(delete_item)

        async def change_order(up: bool, item):
            i = self.sources.index(item)
            if not -1 < i < len(self.sources):
                return
            j = i - 1 if up else i + 1
            j = max(0, min(j, len(self.sources) - 1))
            self.sources.remove(item)
            self.sources.insert(j, item)
            self.sources = await utils.post(utils.get_url("audio/setSources"), {"sources": self.sources})
            plist.get_server().data = self.sources
            plist.refresh()

        plist.add_button("up", "", "btn btn-primary btn-sm").use_element(
            lambda item: E("i")
            .attr("class", "fas fa-sort-up")
            .attr("style", "font-size: 20px; vertical-align: bottom;")
        ).onclick(change_order.bind(None, True))

        plist.add_button("down", "", "btn btn-primary btn-sm").use_element(
            lambda item: E("i")
            .attr("class", "fas fa-sort-down")
            .attr("style", "font-size: 20px; vertical-align: bottom;")
        ).onclick(change_order.bind(None, False))

        def add_item(evt):
            self.sources.append(source("Naam", False, "IN1", 0, -60, False))
            plist.get_server().data = self.sources
            plist.refresh()

        button_add = E("button").attr("class", "btn btn-primary btn-sm").inner_html("Toevoegen")
        button_add.element.onclick = add_item

        self.body.append(button_add)

        async def initialize():
            self.sources = await utils.post(utils.get_url("audio/getSources"), {})
            self.sources = list(self.sources)
            plist.get_server().data = self.sources
            plist.refresh()

        self.refresh = initialize


def destination(name, enabled, port_url_file, selected):
    return {"name": name, "enabled": enabled, "port_url_file": port_url_file, "selected": selected}


class Destinations(AccordionItem):
    def __init__(self):
        super().__init__("Geluid - Bestemmingen")
        plist = PagedList(self.body.element, "").hide_count().disable_pagination()
        plist.get_styling().table_class("table borderless")

        def text_element(attr, item):
            r = E("input").attr("type", "text")
            r.element.value = item[attr]

            def onchange(evt):
                item[attr] = r.element.value
                save_changes()

            r.element.onchange = onchange
            return r.element

        def checkbox_element(attr, item):
            r = E("input").attr("type", "checkbox")
            r.element.checked = item[attr]

            def onchange(evt):
                item[attr] = r.element.checked
                save_changes()

            r.element.onchange = onchange
            return r.element

        plist.add_column("name", "Naam").item_to_element(text_element.bind(None, "name"))
        plist.add_column("enabled", "Actief").item_to_element(checkbox_element.bind(None, "enabled"))
        plist.add_column("port_url_file", "Poort / Url / File").item_to_element(
            text_element.bind(None, "port_url_file")
        )

        async def delete_item(item):
            self.destinations.remove(item)
            self.destinations = await utils.post(
                utils.get_url("audio/setDestinations"), {"destinations": self.destinations}
            )
            plist.get_server().data = self.destinations
            plist.refresh()

        async def save_changes():
            self.destinations = await utils.post(
                utils.get_url("audio/setDestinations"), {"destinations": self.destinations}
            )
            plist.get_server().data = self.destinations
            plist.refresh()

        plist.add_button("delete", "", "btn btn-danger btn-sm").use_element(
            lambda item: E("i").attr("class", "fas fa-trash-alt")
        ).onclick(delete_item)

        async def change_order(up: bool, item):
            i = self.destinations.index(item)
            if not -1 < i < len(self.destinations):
                return
            j = i - 1 if up else i + 1
            j = max(0, min(j, len(self.destinations) - 1))
            self.destinations.remove(item)
            self.destinations.insert(j, item)
            self.destinations = await utils.post(
                utils.get_url("audio/setDestinations"), {"destinations": self.destinations}
            )
            plist.get_server().data = self.destinations
            plist.refresh()

        plist.add_button("up", "", "btn btn-primary btn-sm").use_element(
            lambda item: E("i")
            .attr("class", "fas fa-sort-up")
            .attr("style", "font-size: 20px; vertical-align: bottom;")
        ).onclick(change_order.bind(None, True))

        plist.add_button("down", "", "btn btn-primary btn-sm").use_element(
            lambda item: E("i")
            .attr("class", "fas fa-sort-down")
            .attr("style", "font-size: 20px; vertical-align: bottom;")
        ).onclick(change_order.bind(None, False))

        def add_item(evt):
            self.destinations.append(destination("Naam", False, "OUT1", False))
            plist.get_server().data = self.destinations
            plist.refresh()

        button_add = E("button").attr("class", "btn btn-primary btn-sm").inner_html("Toevoegen")
        button_add.element.onclick = add_item

        self.body.append(button_add)

        async def initialize():
            self.destinations = await utils.post(utils.get_url("audio/getDestinations"), {})
            plist.get_server().data = self.destinations
            plist.refresh()

        self.refresh = initialize


def camera(name, url_intern, url_extern, port_http, port_onvif, port_ws, username, password):
    return {
        "name": name, 
        "url_intern": url_intern, 
        "url_extern": url_extern, 
        "port_http": port_http, 
        "port_onvif": port_onvif, 
        "port_ws": port_ws, 
        "username": username, 
        "password": password
    }


class Cameras(AccordionItem):
    def __init__(self):
        super().__init__("Camera's")
        plist = PagedList(self.body.element, "").hide_count().disable_pagination()
        plist.get_styling().table_class("table borderless")

        def text_element(attr, item):
            r = E("input").attr("type", "text")
            r.element.value = item[attr]

            def onchange(evt):
                item[attr] = r.element.value
                save_changes()

            r.element.onchange = onchange
            return r.element

        def number_element(attr, item):
            r = E("input").attr("type", "number")
            r.element.value = item[attr]

            def onchange(evt):
                item[attr] = r.element.value
                save_changes()

            r.element.onchange = onchange
            return r.element

        def password_element(attr, item):
            r = E("input").attr("type", "password")
            #r.element.value = item[attr]
            r.element.placeholder = "invullen om te wijzigen"

            def onchange(evt):
                item[attr] = r.element.value
                save_changes()

            r.element.onchange = onchange
            return r.element

        def checkbox_element(attr, item):
            r = E("input").attr("type", "checkbox")
            r.element.checked = item[attr]

            def onchange(evt):
                item[attr] = r.element.checked
                save_changes()

            r.element.onchange = onchange
            return r.element

        plist.add_column("name", "Naam").item_to_element(text_element.bind(None, "name"))
        plist.add_column("url_intern", "IP").item_to_element(text_element.bind(None, "url_intern"))
        plist.add_column("url_extern", "URL").item_to_element(text_element.bind(None, "url_extern"))
        plist.add_column("port_http", ":HTTP").item_to_element(number_element.bind(None, "port_http"))
        plist.add_column("port_onvif", ":ONVIF").item_to_element(number_element.bind(None, "port_onvif"))
        plist.add_column("port_ws", ":WS").item_to_element(number_element.bind(None, "port_ws"))
        plist.add_column("username", "Gebruikersnaam").item_to_element(text_element.bind(None, "username"))
        plist.add_column("password", "Wachtwoord").item_to_element(password_element.bind(None, "password"))

        async def delete_item(item):
            self.cameras.remove(item)
            self.cameras = await utils.post(
                utils.get_url("camera/setCameras"), {"cameras": self.cameras}
            )
            plist.get_server().data = self.cameras
            plist.refresh()

        async def save_changes():
            self.cameras = await utils.post(
                utils.get_url("camera/setCameras"), {"cameras": self.cameras}
            )
            plist.get_server().data = self.cameras
            plist.refresh()

        plist.add_button("delete", "", "btn btn-danger btn-sm").use_element(
            lambda item: E("i").attr("class", "fas fa-trash-alt")
        ).onclick(delete_item)

        async def change_order(up: bool, item):
            i = self.cameras.index(item)
            if not -1 < i < len(self.cameras):
                return
            j = i - 1 if up else i + 1
            j = max(0, min(j, len(self.cameras) - 1))
            self.cameras.remove(item)
            self.cameras.insert(j, item)
            self.cameras = await utils.post(
                utils.get_url("camera/setCameras"), {"cameras": self.cameras}
            )
            plist.get_server().data = self.cameras
            plist.refresh()

        plist.add_button("up", "", "btn btn-primary btn-sm").use_element(
            lambda item: E("i")
            .attr("class", "fas fa-sort-up")
            .attr("style", "font-size: 20px; vertical-align: bottom;")
        ).onclick(change_order.bind(None, True))

        plist.add_button("down", "", "btn btn-primary btn-sm").use_element(
            lambda item: E("i")
            .attr("class", "fas fa-sort-down")
            .attr("style", "font-size: 20px; vertical-align: bottom;")
        ).onclick(change_order.bind(None, False))

        def add_item(evt):
            self.cameras.append(camera("Naam", "192.168.1.1", "website.nl", 80, 2000, 8088, "username", "password"))
            plist.get_server().data = self.cameras
            plist.refresh()

        button_add = E("button").attr("class", "btn btn-primary btn-sm").inner_html("Toevoegen")
        button_add.element.onclick = add_item

        self.body.append(button_add)

        async def initialize():
            cameras = await utils.post(utils.get_url("camera/getCameras"), {})
            if cameras.success:
                self.cameras = cameras.cameras

            plist.get_server().data = self.cameras
            plist.refresh()

        self.refresh = initialize

def user(username, password, admin, camera):
    return {
        "username": username, 
        "password": password,
        "admin": admin,
        "camera": camera
    }

class Users(AccordionItem):
    def __init__(self):
        super().__init__("Gebruikers")

        plist = PagedList(self.body.element, "").hide_count().disable_pagination()
        plist.get_styling().table_class("table borderless")

        def text_element(attr, item):
            r = E("input").attr("type", "text")
            r.element.value = item[attr]

            def onchange(evt):
                item[attr] = r.element.value
                save_changes()

            r.element.onchange = onchange
            return r.element

        def password_element(attr, item):
            r = E("input").attr("type", "password")
            #r.element.value = item[attr]
            r.element.placeholder = "invullen om te wijzigen"

            def onchange(evt):
                item[attr] = r.element.value
                save_changes()

            r.element.onchange = onchange
            return r.element

        def checkbox_element(attr, item):
            r = E("input").attr("type", "checkbox")
            r.element.checked = item[attr]

            def onchange(evt):
                item[attr] = r.element.checked
                save_changes()

            r.element.onchange = onchange
            return r.element

        plist.add_column("username", "Naam").item_to_element(text_element.bind(None, "username"))
        plist.add_column("password", "Wachtwoord").item_to_element(password_element.bind(None, "password"))
        plist.add_column("admin", "Admin").item_to_element(checkbox_element.bind(None, "admin"))
        plist.add_column("camera", "Camera app").item_to_element(checkbox_element.bind(None, "camera"))

        async def delete_item(item):
            # todo
            return

        async def save_changes():
            self.users = await utils.post(
                utils.get_url("login/setUsers"), {"users": self.users}
            )
            plist.get_server().data = self.users
            plist.refresh()

        def add_item(evt):
            self.users.append(user("username", "password"))
            plist.get_server().data = self.users
            plist.refresh()

        button_add = E("button").attr("class", "btn btn-primary btn-sm").inner_html("Toevoegen")
        button_add.element.onclick = add_item

        self.body.append(button_add)

        async def initialize():
            self.users = await utils.post(utils.get_url("login/getUsers"), {})
            plist.get_server().data = self.users
            plist.refresh()

        self.refresh = initialize


class TestDebug(AccordionItem):
    def __init__(self):
        super().__init__("Test and debug")

        self.button_reboot = E("button").attr("class", "btn btn-primary btn-sm").inner_html("Herstarten")
        self.button_shutdown = E("button").attr("class", "btn btn-primary btn-sm").inner_html("Afsluiten")
        self.button_show_ip = E("button").attr("class", "btn btn-primary btn-sm").inner_html("Toon IP adres")
        self.button_show_soundcards = (
            E("button").attr("class", "btn btn-primary btn-sm").inner_html("Toon geluidskaarten")
        )
        self.button_show_routes = E("button").attr("class", "btn btn-primary btn-sm").inner_html("Toon ITEC routes")
        self.button_download_log = E("button").attr("class", "btn btn-primary btn-sm").inner_html("Download log")
        self.button_test_gpio = E("button").attr("class", "btn btn-primary btn-sm").inner_html("Test GPIO")
        buttons = [
            self.button_reboot,
            self.button_shutdown,
            self.button_show_ip,
            self.button_show_soundcards,
            self.button_show_routes,
            self.button_download_log,
            self.button_test_gpio,
        ]

        for b in buttons:
            b.attr("style", "margin-right: 5px;")

        self.button_reboot.element.onclick = self.reboot
        self.button_shutdown.element.onclick = self.shutdown
        self.button_show_ip.element.onclick = self.show_ip
        self.button_show_soundcards.element.onclick = self.show_soundcards
        self.button_show_routes.element.onclick = self.show_routes
        self.button_download_log.element.onclick = self.download_log
        self.button_test_gpio.element.onclick = self.test_gpio

        self.body.append(
            E("div")
            .attr("style", "padding: 5px;")
            .append(E("span").inner_html("Audiocontroller version: {}".format(window.audiocontroller_version)))
        )
        self.body.append(E("div").append(*buttons))
        self.div_info = E("div").attr("style", "white-space: pre-wrap;")
        self.body.append(self.div_info)

    async def reboot(self, evt):
        sure = await dialog_confirm.get_confirm("Systeem zal worden herstart. Weet u het zeker?")
        if sure:
            await utils.post(utils.get_url("general/reboot"), {})

    async def shutdown(self, evt):
        sure = await dialog_confirm.get_confirm("Systeem zal worden uitgeschakeld. Weet u het zeker?")
        if sure:
            await utils.post(utils.get_url("general/shutdown"), {})

    async def download_log(self, evt):
        self.button_download_log.disable()
        datetime = luxon.DateTime.local().toFormat("yyyyMMdd_HHmm")
        filename = "{}_logs.tar".format(datetime)
        await utils.post_download_file(utils.get_url("general/downloadLog"), {}, filename)
        self.button_download_log.enable()

    async def show_ip(self, evt):
        self.button_show_ip.disable()
        txt = await utils.post(utils.get_url("general/ifconfig"), {}, False)
        console.log(txt)
        self.div_info.inner_html(txt)
        self.button_show_ip.enable()

    async def show_soundcards(self, evt):
        self.button_show_soundcards.disable()
        txt = await utils.post(utils.get_url("audio/soundcards"), {}, False)
        console.log(txt)
        self.div_info.inner_html(txt)
        self.button_show_soundcards.enable()

    async def show_routes(self, evt):
        self.button_show_routes.disable()
        txt = await utils.post(utils.get_url("audio/getRoutes"), {}, False)
        console.log(txt)
        self.div_info.inner_html(txt)
        self.button_show_routes.enable()

    async def test_gpio(self, evt):
        self.button_test_gpio.disable()
        txt = await utils.post(utils.get_url("general/test_gpio"), {}, False)
        self.button_test_gpio.enable()


class Page(ElementWrapper):
    def __init__(self):
        super().__init__(element("div"))
        self.items = [Settings(), Sources(), Destinations(), Cameras(), Users(), TestDebug()]
        for i in self.items:
            self.append(i)

        self.button_download = E("button").attr("class", "btn btn-primary btn-sm").inner_html("Download")
        self.button_download.element.onclick = self.download_settings

        self.file_input = E("input").attr("type", "file").attr("style", "display: none;")
        self.file_input.element.onchange = self.upload_settings
        self.button_upload = E("button").attr("class", "btn btn-primary btn-sm").inner_html("Upload")
        self.button_upload.element.onclick = self.click_upload
        button_restore = (
            E("button").attr("class", "btn btn-secondary btn-sm").inner_html("Terug naar fabrieksinstellingen")
        )
        button_restore.element.onclick = self.restore_settings

        def space():
            return E("span").inner_html(" ")

        self.append(
            E("div")
            .attr("style", "margin-top: 15px;")
            .append(self.button_download, space(), self.file_input, self.button_upload, space(), button_restore)
        )

    async def restore_settings(self, evt):
        sure = await dialog_confirm.get_confirm("Terug naar fabrieksinstellingen. Weet u het zeker?")
        if sure:
            await utils.post(utils.get_url("general/restoreSettings"), {})
            self.refresh()

    async def download_settings(self, evt):
        self.button_download.disable()
        datetime = luxon.DateTime.local().toFormat("yyyyMMdd_HHmm")
        filename = "{}_audio_controller_settings.pickle".format(datetime)
        await utils.post_download_file(utils.get_url("general/downloadSettings"), {}, filename)
        self.button_download.enable()

    async def upload_settings(self, evt):
        file = self.file_input.element.files[0]
        self.file_input.element.value = None
        await utils.post_upload_file(utils.get_url("general/uploadSettings"), file)
        utils.redirect_relative("")

    def click_upload(self, evt):
        self.file_input.element.click()

    def refresh(self):
        for item in self.items:
            item.refresh()

    def show(self):
        main.remove_childs()
        main.append(self)
        self.refresh()

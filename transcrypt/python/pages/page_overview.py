__pragma__('alias', 'S', '$')  # to use jQuery library with 'S' instead of '$'
import utils
from elements import Element, element, ElementWrapper, get_Element, get_elements, get_element
from pages import page_admin, page_overview

from layout import home, main, set_title
E = Element


class ButtonsSettings(ElementWrapper):
    """ Buttons to enable/disable some settings """

    def __init__(self):
        super().__init__(element('table'))
        self.sources_destinations: SourcesDestinations = None

        checkbox_connect = E('input').attr('type', 'checkbox')
        self.checkbox_connect = checkbox_connect
        checkbox_sound_on = E('input').attr('type', 'checkbox')
        checkbox_auto_switch = E('input').attr('type', 'checkbox')

        tr_connect = E('tr').append(
            E('td').append(E('span').inner_html("Bron en bestemming(en) verbinden")),
            E('td').attr('style', 'padding: 10px 0px 0px 10px;').append(
                E('label').attr('class', 'switch').append(
                    checkbox_connect,
                    E('span').attr('class', 'slider round')
                )
            )
        )

        class_mute = "fas fa-volume-mute"
        class_loud = "fas fa-volume-up"
        span_volume = E("span").attr("class", class_loud).attr("style", "padding: 10px; font-size: 24px;")

        tr_sound_on = E('tr').append(
            E('td').append(E('span').inner_html("Geluid aan")),
            E('td').attr('style', 'padding: 10px 0px 0px 10px;').append(
                E('label').attr('class', 'switch').append(
                    checkbox_sound_on,
                    E('span').attr('class', 'slider round')
                )
            ),
            E("td").append(span_volume)
        )

        tr_auto_switch = E('tr').append(
            E('td').append(E('span').inner_html("Automatisch bron kiezen")),
            E('td').attr('style', 'padding: 10px 0px 0px 10px;').append(
                E('label').attr('class', 'switch').append(
                    checkbox_auto_switch,
                    E('span').attr('class', 'slider round')
                )
            )
        )

        self.append(E('tbody').append(
            tr_connect,
            tr_sound_on,
            tr_auto_switch
        ))

        def set_inputs(settings):
            checkbox_connect.element.checked = settings['connect_source_destination']
            tr_connect.element.style.display = 'none'
            if settings['show_button_connect']:
                tr_connect.element.style.display = ''
            # checkbox sound on
            checkbox_sound_on.element.checked = not settings['mute_sound']
            tr_sound_on.element.style.display = 'none'
            if settings['show_button_mute_sound']:
                tr_sound_on.element.style.display = ''
                if settings['mute_sound']:
                    span_volume.attr("class", class_mute)
                else:
                    span_volume.attr("class", class_loud)
            # checkbox auto switch
            checkbox_auto_switch.element.checked = settings['enable_auto_switch']
            tr_auto_switch.element.style.display = 'none'
            if settings['enable_option_auto_switch']:
                tr_auto_switch.element.style.display = ''
            
            self.sources_destinations.refresh()

        async def onchange(evt):
            settings = {
                'connect_source_destination': checkbox_connect.element.checked,
                'mute_sound': not checkbox_sound_on.element.checked,
                'enable_auto_switch': checkbox_auto_switch.element.checked,
            }
            r = await utils.post(utils.get_url('general/setSettings'), settings)
            set_inputs(r)

        checkbox_connect.element.onchange = onchange
        checkbox_sound_on.element.onchange = onchange
        checkbox_auto_switch.element.onchange = onchange

        async def initialize():
            r = await utils.post(utils.get_url('general/getSettings'), {})
            set_inputs(r)

        self.refresh = initialize


class SourcesDestinations(ElementWrapper):

    def __init__(self):
        super().__init__(element("table"))
        self.buttons_settings: ButtonsSettings = None
        self.attr('class', 'table borderless')
        self.td_sources = E('td')
        # E('div').attr('class', 'radio').append(E('label').append(source_elements[0], E('span').inner_html(" Kerkzaal"))),
        self.td_destinations = E('td')
        self.append(
            E('thead').attr('style', 'border-bottom: solid rgb(200,200,200);').append(E('tr').append(
                E('th').inner_html("Bron"), E('th').inner_html(''), E('th').inner_html("Bestemming"))),
            E('tbody').append(
                E('tr').append(E('td'), E('td'), E('td')),
                E('tr').append(
                    self.td_sources.attr('class', 'container').attr('style', 'width: 250px;'),
                    # E('td').append(E('span').attr('class', 'fas fa-arrow-circle-right').attr('style', 'font-size:100px;')),
                    # <img src="pic_trulli.jpg" alt="Italian Trulli">
                    E('td').attr('style', 'width: 220px;').append(E('img').attr('src', '/static/pictures/connected.png').attr('style', 'width: 160px;')),
                    self.td_destinations.attr('style', 'width: 250px;')
                ),
            )
        )

        async def get_sources():
            self.sources = await utils.post(utils.get_url('audio/getSources'), {})

        async def select_source(radio_button, source, evt):
            if radio_button.element.checked:
                for s in self.sources:
                    s['selected'] = False
                source['selected'] = True
                self.sources = await utils.post(utils.get_url('audio/setSources'), {'sources': self.sources})
                show_sources()

        async def get_destinations():
            self.destinations = await utils.post(utils.get_url('audio/getDestinations'), {})

        async def select_destination(checkbox, destination, evt):
            destination['selected'] = checkbox.element.checked
            self.destinations = await utils.post(utils.get_url('audio/setDestinations'), {'destinations': self.destinations})
            show_destinations()

        volume_spans = {}  # key = source_id (str), value = span-element

        def show_sources():
            self.td_sources.remove_childs()
            volume_spans.clear()
            for s in self.sources:
                volume_span = E('span')
                # E('span').attr('class', "fas fa-volume-up"),
                volume_spans[str(s.id)] = volume_span
                if s['enabled']:
                    radio_button = E('input').attr('type', 'radio').attr('name', 'select_source')
                    radio_button.element.checked = s['selected']
                    radio_button.element.onchange = select_source.bind(None, radio_button, s)
                    self.td_sources.append(
                        E('div').attr('class', 'row').append(
                            E('div').attr('class', 'radio col-sm-9').append(
                                E('label').attr('style', 'white-space: nowrap;').append(
                                    radio_button,
                                    E('span').inner_html("  "),
                                    E('span').text(s['name'])
                                )
                            ),
                            E('div').attr('class', 'col-sm-3').append(volume_span)
                        )
                    )

        def show_destinations():
            self.td_destinations.remove_childs()
            for d in self.destinations:
                if d['enabled']:
                    checkbox = E('input').attr('type', 'checkbox')
                    checkbox.element.checked = d['selected']
                    checkbox.element.onchange = select_destination.bind(None, checkbox, d)
                    self.td_destinations.append(
                        E('div').attr('class', 'radio').append(
                            E('label').attr('style', 'white-space: nowrap;').append(
                                E('label').attr('class', 'switch').append(
                                    checkbox,
                                    E('span').attr('class', 'slider round')
                                ),
                                E('span').inner_html("  "),
                                E('span').text(d['name'])
                            )
                        )
                    )

        async def update_volume_level():
            # volume_off = "fas fa-volume-off"
            volume_off = ""
            volume_on = "fas fa-volume-up"
            while True:
                try:
                    inputLevels = await utils.post(utils.get_url('audio/getInputLevels'), {})
                    inputLevels = dict(inputLevels)
                    for source_id, level in inputLevels.items():
                        span = volume_spans[str(source_id)]
                        if level['level'] is not None and level['level'] >= level['threshold']:
                            span.attr('class', volume_on).attr('title', str(level['level']))
                        else:
                            span.attr('class', volume_off)
                            if level['level'] is not None:
                                span.attr('title', str(level['level']))
                except:
                    pass
                await utils.sleep(3)

        async def initialize():
            connected = self.buttons_settings.checkbox_connect.element.checked if self.buttons_settings is not None else True
            if connected:
                self.element.style.display = 'block'
                await get_sources()
                await get_destinations()
                show_sources()
                show_destinations()
            else:
                self.element.style.display = 'none'

        self.refresh = initialize
        update_volume_level()


class Page(ElementWrapper):

    def __init__(self):
        super().__init__(element('div'))
        self.attr('style', 'max-width: 1000px;')
        buttons_settings = ButtonsSettings()
        sources_destinations = SourcesDestinations()
        # references to each other:
        buttons_settings.sources_destinations = sources_destinations
        sources_destinations.buttons_settings = buttons_settings
        self.append(buttons_settings, sources_destinations)
        self.refresh = lambda: buttons_settings.refresh()  # sources_destinations will be refreshed also

    def show(self):
        main.remove_childs()
        main.append(self)
        self.refresh()

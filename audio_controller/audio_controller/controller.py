
""" purpose: route input to output """
# standard lib
from typing import List
import asyncio
import logging

# externals

# internals
from . import itec as itec_module
from .itec import itec
from . import settings
from .settings import Source, Destination
from . import stream


main_logger = logging.getLogger("main")


def get_IN_port(source: Source) -> int:
    """ Get ITEC IN port nr, also if it is an url. """
    result = settings.get_IN_port(source.port_url)
    if result is None:
        result = settings.get_IN_port(settings.settings.port_IN_for_streams)
    return result


class Config:
    """ 
    Holds configuration, which consists of connections from input to output ports.
    """

    def __init__(self):
        self.current_levels = {}  # key = source-id, value = dict (keys: 'level', 'threshold', and 'prio')
        self.send_to_urls = stream.get_url_sender()
        self.read_from_url = stream.get_url_reader()
        self.sources = None
        self.destinations = None
        self.url_in = None  # url currently streamed onto the IN port (used by scan_ports); None if none

    def route_all_to_null(self):
        """ route all IN ports of itec to null, meaning no sound will go through """
        ports = [get_IN_port(s) for s in self.sources]
        for p in ports:
            itec.set_route(p, [])

    def stop_all(self):
        """ route all IN ports of itect to null, and stop reading from and sending to urls """
        self.route_all_to_null()
        self.read_from_url.update_url(None)
        self.send_to_urls.update_urls([])
        self.url_in = None

    def get_selected_source(self):
        for source in self.sources:
            if source.selected:
                return source
        return None

    def disable_unselected_sources(self, selected_port):
        # disable all IN ports which are not selected
        ports = [get_IN_port(s) for s in self.sources if not s.selected]
        for p in ports:
            if p != selected_port:
                itec.set_route(p, [])

    def get_input(self, selected_source):
        # determine all ports and urls for in and out
        port_in: int = None
        url_in: str = None
        
        port_in = settings.get_IN_port(selected_source.port_url)
        if port_in is None:
            # selected source is not a port, but an url
            port_in = settings.get_IN_port(settings.settings.port_IN_for_streams)
            url_in = selected_source.port_url
        
        return port_in, url_in

    def get_outputs(self):
        """
        Select all OUT ports which must get route (from input), and select urls to which audio must be send.
        """
        ports_out: List[int] = []
        urls_out: List[str] = []
        for d in self.destinations:
            if d.selected:
                port_out = settings.get_OUT_port(d.port_url_file)
                if port_out is None:
                    port_out = settings.get_OUT_port(settings.settings.port_OUT_to_stream)
                    if port_out is not None:
                        urls_out.append(d.port_url_file)
                if port_out is not None and port_out not in ports_out:
                    ports_out.append(port_out)
        return ports_out, urls_out

    def update_sources_destinations(self, sources: List[Source], destinations: List[Destination]):
        """ 
        Set routes on ITEC to route audio from selected sources to selected destinations.
        Sources and destinations must all be enabled.
        """
        self.sources = sources
        self.destinations = destinations

        if not settings.settings.connect_source_destination or not destinations:
            self.stop_all()
            return

        selected_source = self.get_selected_source()

        if selected_source is None:  # nothing selected
            self.stop_all()
            return None

        port_in, url_in = self.get_input(selected_source)
        self.url_in = url_in  # remember which url (if any) is on the IN port, for scan_ports (C1)

        self.disable_unselected_sources(port_in)

        ports_out, urls_out = self.get_outputs()

        if settings.settings.mute_sound:
            # Muting only affects the itec ports.
            # The url streams will be kept intact
            self.route_all_to_null()
        else:
            itec.set_route(port_in, ports_out)
        # start or stop playing url stream
        self.read_from_url.update_url(url_in)
        self.send_to_urls.update_urls(urls_out)


config = Config()


def set_routes():
    """ Setup routes according settings (not taking into account setting auto_switch) """
    enabled_sources = [s for s in settings.sources if s.enabled]
    enabled_destinations = [d for d in settings.destinations if d.enabled]
    config.update_sources_destinations(enabled_sources, enabled_destinations)
    config.current_levels.clear()


def get_routes():
    """ Return the routes of the enabled IN ports as text """
    # TODO maybe it is better to return all ITEC IN ports, not only the enabled sources.
    result = f"Looking at usb port {itec_module.get_usb_port()}\n"
    if itec.serial is None:
        result += f"ITEC is not connected.\n"
        return result
    enabled_sources = [s for s in settings.sources if s.enabled]
    ports = list(set([get_IN_port(s) for s in enabled_sources]))
    result += "IN -> OUT\n"
    for p in ports:
        result += f"{p} -> {itec.get_route(p)}\n"
    return result


async def scan_ports():
    """ Continuously scan ports, measure audio level (dB's) and save result in config.
    This method only scans ITEC ports, not the url streams. """
    while True:
        try:
            # look only at enabled sources
            sources = [s for s in settings.sources if s.enabled]

            # cleanup config, deleting all source-ids which not exist
            source_ids = [s.id for s in sources]
            for source_id in list(config.current_levels.keys()):
                if not source_id in source_ids:
                    del config.current_levels[source_id]

            # measure inputlevel by communicating with itec
            for source in sources:
                port = settings.get_IN_port(source.port_url)
                if port is None:
                    port = settings.get_IN_port(settings.settings.port_IN_for_streams)

                if settings.is_IN_port(source.port_url):
                    port = settings.get_IN_port(source.port_url)
                    level = itec.get_input_level(port)
                    config.current_levels[source.id] = {'level': level, 'threshold': source.db_level, 'prio': source.scan_prio}
                elif settings.is_url(source.port_url):
                    if config.url_in == source.port_url:
                        # TODO check if this source is currenly streamed on the IN port
                        # only then it can be updated, ignore otherwise (will be done maybe in next loop)
                        port = settings.get_IN_port(settings.settings.port_IN_for_streams)
                        level = itec.get_input_level(port)
                        config.current_levels[source.id] = {'level': level, 'threshold': source.db_level, 'prio': source.scan_prio}

        except Exception as e:
            # log instead of silently swallowing (C2); keep the loop alive
            main_logger.warning(f"scan_ports error: {e}")
        await asyncio.sleep(2)


def auto_switch_interval_seconds(timeout_minutes) -> int:
    """Seconds between auto_switch passes, with a 1s floor so a zero timeout can
    never turn the loop into a 100%-CPU busy loop. (P1)"""
    try:
        return max(1, int(timeout_minutes) * 60)
    except (TypeError, ValueError):
        return 60


async def auto_switch():
    """
    Continuously check if a switch to another source is needed.

    """
    interval_seconds = auto_switch_interval_seconds(settings.settings.timeout_auto_switch)
    while True:
        try:
            if settings.settings.enable_option_auto_switch and settings.settings.enable_auto_switch:
                # determine source_id which should be selected
                source_id = None
                prio = 0

                for s_id, v in config.current_levels.items():
                    level, threshold, source_prio = v['level'], v['threshold'], v['prio']
                    if source_prio > 0 and level >= threshold:
                        if prio == 0 or source_prio < prio:
                            source_id = s_id
                            prio = source_prio

                # routing is only needed if current selection is not source_id
                routing_needed = False
                source: Source = None
                if source_id is not None:
                    sources = [s for s in settings.sources if s.enabled and s.scan_prio >= 0]
                    for s in sources:
                        if s.id == source_id and not s.selected:
                            s.selected = True
                            routing_needed = True
                            source = s
                        elif s.id != source_id and s.selected:
                            s.selected = False
                            routing_needed = True

                if routing_needed:
                    msg = f"Auto switching to source '{source.name}'"
                    print(msg)
                    main_logger.info(msg)
                    settings.save()
                    set_routes()

        except Exception as e:
            # log instead of silently swallowing (C2); keep the loop alive
            main_logger.warning(f"auto_switch error: {e}")
        await asyncio.sleep(interval_seconds)

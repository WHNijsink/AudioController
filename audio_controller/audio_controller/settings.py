""" Module which handles settings, which are configurable and thus persistent """
import sys
import os
import json
import logging
import threading
import ipaddress
import re
from urllib.parse import urlparse
from typing import List
from pathlib import Path
import pickle
from dataclasses import dataclass, field, asdict
import hashlib

from . import fonts, camera, user, psalmbord

main_logger = logging.getLogger("main")

#
# Classes and default settings
#


@dataclass
class Settings:
    """ Settings including field types and default values """
    title: str = "Noorderkerk"
    nr_IN_ports: int = 8  # nr of IN ports on ITEC
    nr_OUT_ports: int = 4  # nr of OUT ports on ITEC
    port_IN_for_streams: str = 'IN4'  # IN port of ITEC, connected to output of this device (raspberry pi) to put audio from stream on
    port_OUT_to_stream: str = ''  # OUT port of ITEC, connected to input of this device (raspberry pi) to forward audio to url
    connect_source_destination: bool = True  # on/off switch: when False, no IN port is routed to OUT port, and streams are disconnected
    show_button_connect: bool = False # to show the button to connect source and destinations. If False, connect_source_destination must be True
    mute_sound: bool = False # on/off switch: when True, all sound is muted by disabling all OUT ports (but keeping streams connected)
    show_button_mute_sound: bool = True # to show the button to mute the sound. If False, mute_sound must be False
    enable_option_auto_switch: bool = False  # to be set by administrator, to enable/disable the option to enable auto scan and switch
    enable_auto_switch: bool = False  # when True, the IN ports belonging to all enabled sources are scanned, and when there is a signal, the source is automatically selected
    timeout_auto_switch: int = 15  # minutes to wait after signal is away, before switching to other
    enable_audio: bool = True # enable Geluid functionaliteit
    enable_psalmbord: bool = False  # enable Psalmbord functionaliteit
    enable_camera: bool = False  # enable Psalmbord functionaliteit
    enable_logging: bool = True
    version: int = 6  # version of settings, used for upgrades


@dataclass
class Source:
    name: str
    enabled: bool
    port_url: str
    scan_prio: int
    db_level: int
    selected: bool
    id: int = 0


@dataclass
class Destination:
    name: str
    enabled: bool
    port_url_file: str
    selected: bool
    id: int = 0


def default_sources():
    """ Default sources, used as initial and factory defaults """
    result = [
        Source('Kerkzaal', True, 'IN1', 1, -45, False),
        Source('Trouwzaal', True, 'IN2', 0, -45, False),
        Source('Zaal 3', False, 'IN3', 0, -45, False),
        Source('Microfoon', False, 'IN5', 0, -45, False),
        Source('Noord', False, 'http://meeluisteren.gergemrijssen.nl:8000/noord', 0, -45, False),
        Source('Zuid', True, 'http://meeluisteren.gergemrijssen.nl:8000/zuid', 0, -45, False),
        Source('West', True, 'http://meeluisteren.gergemrijssen.nl:8000/west', 0, -45, False),
        Source('Ref. Omroep 1', False, 'http://ro1.reformatorischeomroep.nl:8003/live', 0, -45, False),
        Source('Ref. Omroep 2', False, 'http://ro2.reformatorischeomroep.nl:8020/live', 0, -45, False),
        Source('Ref. Omroep 3', False, 'http://ro3.reformatorischeomroep.nl:8072/live', 0, -45, False),
    ]
    for i, obj in enumerate(result):
        obj.id = i
    return result


def default_destinations():
    """ Default destinations, used as initial and factory defaults """
    result = [
        Destination('Internet', True, 'OUT1', True),
        Destination('HF scanners', True, 'OUT2', True),
        Destination('Icecast', False, 'icecast://<user>:<pw>@<ip>:<port>/mountpoint', False),
        Destination('Opslaan', False, 'file://', False),
    ]
    for i, obj in enumerate(result):
        obj.id = i
    return result


#
# Stores / databases
#

# file to save settings (including sources and destinations)
file = Path.home() / ".audio_controller_settings.json"
# legacy pickle file, only read once for a one-time migration to json (S2)
_legacy_pickle_file = Path.home() / ".audio_controller_settings.pickle"
_save_lock = threading.Lock()

settings = Settings()
sources: List[Source] = []
destinations: List[Destination] = []
pb = psalmbord.Psalmbord()
cameras: List[camera.Camera] = []
users: List[user.User] = []

#
# Save and load
#


def _store_dict() -> dict:
    """Serializable snapshot of all persistent settings (json-safe)."""
    return {
        'settings': asdict(settings),
        'sources': [asdict(obj) for obj in sources],
        'destinations': [asdict(obj) for obj in destinations],
        'psalmbord': asdict(pb),
        'cameras': [obj.to_dict() for obj in cameras],
        'users': [asdict(obj) for obj in users],
    }


def upgrade(store: dict):
    """ upgrade store, for example after software is updated on a running application/device """
    if not 'version' in store['settings']:
        store['settings']['version'] = 1

    # Backfill keys that were introduced in this release without their own
    # upgrade step. Without this, upgrading a pre-camera/pre-user settings store
    # raises KeyError in use_from_store and silently loses all settings (falls
    # back to defaults). Seeding defaults here preserves the migration.
    if 'users' not in store:
        store['users'] = [asdict(u) for u in user.default_users()]
    if 'cameras' not in store:
        store['cameras'] = [c.to_dict() for c in camera.default_cameras()]

    if store['settings']['version'] == 1:
        store['settings']['version'] = 2
        store['settings']['port_OUT_to_stream'] = ''

    if store['settings']['version'] == 2:
        store['settings']['version'] = 3
        store['external_sites'] = []  # [asdict(obj) for obj in default_external_sites()]

    if store['settings']['version'] == 3:
        store['settings']['version'] = 4
        del store['external_sites']

    if store['settings']['version'] == 4:
        store['settings']['version'] = 5
        store['settings']['enable_logging'] = True

    if store['settings']['version'] == 5:
        store['settings']['version'] = 6
        store['settings']['enable_psalmbord'] = False
        store['psalmbord'] = asdict(psalmbord.Psalmbord())

    if store['settings']['version'] == 6:
        store['settings']['version'] = 7
        store['psalmbord']['fontfamily'] = psalmbord.default_fontfamily
        store['psalmbord']['fontsize'] = psalmbord.default_fontsize
        store['psalmbord']['fontweight'] = psalmbord.default_fontweight

    if store['settings']['version'] == 7:
        store['settings']['version'] = 8
        # use button mute_sound instead of enable/disable streams
        store['settings']["show_button_mute_sound"] = True
        store['settings']["show_button_connect"] = False
        connected = store['settings']['connect_source_destination']
        store['settings']["mute_sound"] = not connected
        store['settings']['connect_source_destination'] = True

    if store['settings']['version'] == 8:
        store['settings']['version'] = 9
        store['psalmbord']['active'] = True

    if store['settings']['version'] == 9:
        store['settings']['version'] = 10
        store['settings']['enable_camera'] = False
        # het oude bord-model (title + regels) is vervangen door screens; die
        # sleutels moeten weg, anders faalt Psalmbord(**store['psalmbord']) en
        # valt load() terug op defaults (alle instellingen kwijt)
        store['psalmbord'].pop('title', None)
        store['psalmbord'].pop('regels', None)
        store['psalmbord']['active'] = 1
        store['psalmbord']['screens'] = [
            psalmbord.PsalmbordScreen(index=i, text=text, size=8)
            for i, text in enumerate(psalmbord.default_screens)
        ]
        store['psalmbord']['refreshrate'] = 10
    
    if store['settings']['version'] == 10:
        store['settings']['version'] = 11
        store['settings']['enable_audio'] = True
    #
    # future upgrades will be placed here
    #


def use_from_store(store: dict):
    """ Clear current settings and update it with values in store. """
    upgrade(store)
    # create / update dataclass objects from store
    settings.__init__(**store['settings'])
    sources.clear()
    destinations.clear()
    cameras.clear()
    users.clear()
    for obj in store['sources']: sources.append(Source(**obj))
    for obj in store['destinations']: destinations.append(Destination(**obj))
    for obj in store["cameras"]: cameras.append(camera.Camera.from_dict(obj))
    for obj in store["users"]: users.append(user.User(**obj))
    pb.__init__(**store['psalmbord'])
    # Recompute the board content hash after loading: an older store has no
    # html_hash (default ""), which would collide with the kiosk's initial empty
    # hash and leave the board blank until the first edit (Guis f9e284c).
    pb.refresh_html_hash()


def load():
    """ Load settings from file, if available. Return True on success, False otherwise. """
    if file.exists():
        try:
            with open(file, 'r', encoding='utf-8') as f:
                store: dict = json.loads(f.read())
            use_from_store(store)
            save()  # save possible upgrades immediately
            return True
        except Exception:
            return False
    # one-time migration: older versions stored settings as a local pickle file (S2).
    # This reads the trusted on-disk file once, then persists as json going forward.
    if _legacy_pickle_file.exists():
        try:
            with open(_legacy_pickle_file, 'rb') as f:
                store = pickle.loads(f.read())
            use_from_store(store)
            save()  # now persisted as json
            # Remove the legacy pickle so it can never be read again. pickle.loads
            # is RCE if an attacker can plant this file and the json is later
            # removed; deleting it after a successful migration closes that.
            try:
                _legacy_pickle_file.unlink()
            except OSError:
                pass
            return True
        except Exception:
            return False
    return False


def save():
    """ Save all settings to file, atomically (temp file + os.replace), as json (C3). """
    with _save_lock:
        data = json.dumps(_store_dict())
        tmp = file.with_suffix(file.suffix + '.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        # The settings file holds user password hashes and cleartext camera
        # credentials: keep it owner-only so a local user cannot read secrets.
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, file)


def restore():
    """ Restore settings and use all defaults. Save to file """
    store = {
        'settings': asdict(Settings()),
        'sources': [asdict(obj) for obj in default_sources()],
        'destinations': [asdict(obj) for obj in default_destinations()],
        'psalmbord': asdict(psalmbord.Psalmbord()),
        'cameras': [obj.to_dict() for obj in camera.default_cameras()],
        'users': [asdict(obj) for obj in user.default_users()],
    }
    use_from_store(store)
    save()


def init_settings():
    """ Try to load settings from file. If not possible, restore default settings. """
    if not load():
        restore()


init_settings()


def get_binary():
    """ Get content of settings file as binary object (json bytes) """
    with open(file, 'rb') as f:
        return f.read()


def set_binary(obj):
    """ Replace settings from an uploaded settings file (json bytes) (S2).
    Silently ignores anything that is not a valid settings json object. """
    try:
        store = json.loads(obj)
    except (ValueError, TypeError):
        return
    if not isinstance(store, dict):
        return
    # check some required attributes (not all, because some appeared after upgrades)
    if not all(field in store for field in 'settings sources destinations'.split()):
        return
    _sanitize_uploaded_users(store)
    use_from_store(store)
    save()


def _sanitize_uploaded_users(store: dict):
    """Never trust password fields from an uploaded settings file (S-H1). A
    genuine backup stores salted pbkdf2 hashes, which are kept as-is; anything
    else (plaintext, or a bare legacy blake2b hash an attacker could craft into a
    known-password account) is re-hashed so it cannot serve as a working
    credential the uploader chose."""
    for obj in store.get('users', []):
        if not isinstance(obj, dict):
            continue
        pw = obj.get('password', '')
        if user.is_legacy_hash(pw):  # not already salted pbkdf2 -> plaintext or legacy
            obj['password'] = user.hash_password(pw)


#
# Validation of values
#


def get_port_nr(port: str, prefix="IN") -> int:
    """ Get number of IN or OUT port, or None if 'port' is not a valid value. """
    # compare with maximum port nr according current settings
    max_nr = settings.nr_IN_ports if prefix == "IN" else settings.nr_OUT_ports
    try:
        assert port.startswith(prefix)
        port_nr = int(port[len(prefix):])
        assert 0 < port_nr <= max_nr
    except:
        return None
    return port_nr


def get_IN_port(port: str) -> int:
    """ Get number of IN port, or None if 'port' is not a valid value. """
    return get_port_nr(port, "IN")


def is_IN_port(port: str):
    """ Return True if port is an IN port. False otherwise. """
    return get_IN_port(port) is not None


def get_OUT_port(port: str) -> int:
    """ Get number of OUT port, or None if 'port' is not a valid value. """
    return get_port_nr(port, "OUT")


def is_OUT_port(port: str):
    """ Return True if port is an OUT port. False otherwise. """
    return get_OUT_port(port) is not None


def is_url(value: str):
    """ Return True if value is an url. False otherwise. """
    return value.startswith("http") or value.startswith("icecast")


def is_file(value: str):
    """ Return True if value is an direction to a file. False otherwise. """
    return value.startswith("file")


def _is_internal_host(value: str) -> bool:
    """ True if an http(s)/icecast url points at a loopback, private or link-local
    host. Streams should only reach external services, so block internal targets
    to reduce SSRF. Hostnames (non-literal IPs) are allowed (no DNS lookup). (F) """
    try:
        host = urlparse(value).hostname or ""
    except Exception:
        return False
    if not host:
        return False
    if host.lower() in ("localhost", "localhost.localdomain"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved


def validate_settings(obj: Settings):
    """ Return True if settings are correct, False otherwise. Only check values, not types. Possibly correct values. """
    obj.nr_IN_ports = max(1, min(100, obj.nr_IN_ports))
    obj.nr_OUT_ports = max(1, min(8, obj.nr_OUT_ports))  # cannot be more than 8 (length of byte...)
    if not is_IN_port(obj.port_IN_for_streams):
        # IN port is mandatory, which enables the Pi to send audio to ITEC
        return False
    if not is_OUT_port(obj.port_OUT_to_stream) and not obj.port_OUT_to_stream == "":
        # OUT port is NOT mandatory, but the Pi will not send audio to external url (e.g. icecast) in this case
        return False
    if not obj.show_button_connect and not obj.show_button_mute_sound:
        # cannot disable both buttons
        return False
    # correct underlying values if buttons are hidden
    if not obj.show_button_connect:
        obj.connect_source_destination = True
    if not obj.show_button_mute_sound:
        obj.mute_sound = False
    # turn auto-switch off, if option is disabled
    if obj.enable_auto_switch and not obj.enable_option_auto_switch:
        obj.enable_auto_switch = False
    # at least 1 minute: 0 would make the auto_switch loop sleep(0) and spin the
    # CPU at 100% (P1)
    obj.timeout_auto_switch = max(1, min(60 * 24, obj.timeout_auto_switch))
    return True


assert validate_settings(Settings()), "Default settings are not valid"


def validate_source_attribute(name: str, value):
    """ Validate value for attribute with name of a Source object.
    Return value, or adjusted value, or None if it is not valid. """
    try:
        if name == 'name':
            return value[0:50].strip()  # max 50 characters
        elif name == 'port_url':
            if not (is_IN_port(value) or is_url(value)):
                return None
            if is_url(value) and _is_internal_host(value):
                return None  # block SSRF to internal hosts (F)
            return value.strip()
        elif name == 'scan_prio':
            value = max(-1, min(100, value))
        elif name == 'db_level':
            value = max(-70, min(0, value))
        return value
    except:
        return None


def validate_destination_attribute(name: str, value):
    """ Validate value for attribute with name of a Destination object.
    Return value, or adjusted value, or None if it is not valid. """
    try:
        if name == 'name':
            return value[0:50]  # max 50 characters
        elif name == 'port_url_file':  # must be IN port
            if not (is_OUT_port(value) or is_url(value) or is_file(value)):
                return None
            if is_url(value) and _is_internal_host(value):
                return None  # block SSRF to internal hosts (F)
        return value
    except:
        return None


_CAMERA_PORT_ATTRIBUTES = ("port_http", "port_onvif", "port_ws")

# A bare hostname (letters/digits/hyphen labels), used for camera url_intern.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,62})(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}))*$"
)


def _validate_camera_host(value):
    """Validate a camera url_intern: a bare hostname or IPv4/IPv6 literal that is
    spliced into http://{url_intern}/ajaxcom and used for ONVIF (S-M4). Cameras
    live on the private LAN, so private IPs stay valid; loopback/link-local/
    reserved are blocked so the field cannot be aimed at the Pi's own services,
    and scheme/path/port/userinfo are rejected to stop url injection."""
    host = str(value).strip()
    if not host or "://" in host or any(c in host for c in "/@ \t?#\\"):
        raise ValueError(f"camera url_intern: ongeldige host: {value!r}")
    ip = None
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if (ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_unspecified or ip.is_multicast):
            raise ValueError(f"camera url_intern: adres niet toegestaan: {host}")
        return host
    if _HOSTNAME_RE.match(host):
        return host
    raise ValueError(f"camera url_intern: ongeldige host: {value!r}")


def validate_camera_attribute(name: str, value):
    """ Validate value for attribute with name of a Camera object.
    Return value, or adjusted value. Raise ValueError for an invalid port.
    Ports arrive from the admin UI as strings; store them as int (1-65535)
    so a typo or an empty field cannot end up in the connection URL. """
    if name == 'url_intern':
        return _validate_camera_host(value)
    if name in _CAMERA_PORT_ATTRIBUTES:
        try:
            port = int(str(value).strip())
        except (TypeError, ValueError):
            raise ValueError(f"camera {name}: geen geldig poortnummer: {value!r}") from None
        if not 1 <= port <= 65535:
            raise ValueError(f"camera {name}: poort buiten bereik 1-65535: {port}")
        return port
    try:
        if name == 'name':
            return value[0:50]  # max 50 characters
        return value
    except:
        return None


def validate_user_attribute(name: str, value):
    """ Validate value for attribute with name of a User object.
    Return value, or adjusted value, or None if it is not valid. """
    try:
        if name == 'username':
            return value[0:50]  # max 50 characters
        elif name == 'password':
            return value[0:50]  # max 50 characters
        return value
    except:
        return None

#
# Updates
#


def update_settings(obj: dict):
    """ Update both cached and saved settings with values from 'obj'. """
    # dictonary with key, value = attribute-name, type
    annot = Settings.__annotations__
    # server-managed fields the client must never set (e.g. the migration
    # version, which could force a downgrade that resets settings on restart) (F)
    server_managed = {"version"}
    backup = Settings()
    backup.__init__(**asdict(settings))
    for attr in annot.keys():
        if attr in server_managed:
            continue
        if attr in obj:
            try:
                value = annot[attr](obj[attr])  # cast value to type
                setattr(settings, attr, value)
            except:
                pass  # ignore attr
    if validate_settings(settings):
        save()
    else:  # restore
        settings.__init__(**asdict(backup))


def update_sources(new_sources: List[dict]):
    """ Compare sources with current sources, and update the current.
    Each object must contain at least all attributes required to create Source.
    It may contain more, which will be ignored. """
    try:
        # convert all sources to the correct type, let it raise an Exception if its not possible
        fields = Source.__annotations__.copy()
        del fields['id']  # do not copy id
        # create a temporary list, to first validate everything, and then copy
        new_list: List[Source] = []
        for i, obj in enumerate(new_sources):
            new_obj = {}
            # copy attributes
            for attr, value_type in fields.items():
                # cast and validate value
                value = validate_source_attribute(attr, value_type(obj[attr]))
                if value is not None:
                    new_obj[attr] = value
            new_obj = Source(**new_obj)
            new_obj.id = i
            new_list.append(new_obj)
        sources.clear()
        for obj in new_list: sources.append(obj)
        save()
    except:
        pass


def update_destinations(new_destinations: List[dict]):
    """ Compare destinations with current destinations, and update the current.
    Each object must contain at least all attributes required to create Destination.
    It may contain more, which will be ignored. """
    try:
        # convert all sources to the correct type, let it raise an Exception if its not possible
        fields = Destination.__annotations__.copy()
        del fields['id']  # do not copy id
        # create a temporary list, to first validate everything, and then copy
        new_list: List[Destination] = []
        for i, obj in enumerate(new_destinations):
            new_obj = {}
            # copy attributes
            for attr, value_type in fields.items():
                # cast and validate value
                value = validate_destination_attribute(attr, value_type(obj[attr]))
                if value is not None:
                    new_obj[attr] = value
            new_obj = Destination(**new_obj)
            new_obj.id = i
            new_list.append(new_obj)
        destinations.clear()
        for obj in new_list: destinations.append(obj)
        save()
    except:
        pass


def update_cameras(new_cameras: List[dict]):
    try:
        new_list = []

        for i, obj in enumerate(new_cameras):
            cam = camera.Camera.from_dict(obj)
            cam.id = i

            # eventueel hier validatie van de eenvoudige velden
            cam.name = validate_camera_attribute("name", cam.name)
            cam.url_intern = validate_camera_attribute("url_intern", cam.url_intern)
            cam.url_extern = validate_camera_attribute("url_extern", cam.url_extern)
            cam.port_http = validate_camera_attribute("port_http", cam.port_http)
            cam.port_onvif = validate_camera_attribute("port_onvif", cam.port_onvif)
            cam.port_ws = validate_camera_attribute("port_ws", cam.port_ws)
            cam.username = validate_camera_attribute("username", cam.username)
            cam.password = validate_camera_attribute("password", cam.password)

            new_list.append(cam)

        cameras[:] = new_list
        save()
    except Exception:
        main_logger.exception("settings write failed")
        raise

def update_users(new_users: List[dict]):
    try:
        # index current users by username so a password change is detected by
        # identity, not list position (a reorder/insert no longer re-hashes the
        # wrong user's stored hash), and a blank password means "keep existing".
        # The client is never sent the hash (D), so blank is the normal case for
        # an unchanged user.
        existing = {u.username: u for u in users}
        new_list = []

        for obj in new_users:
            usr = user.User(**obj)
            usr.username = validate_user_attribute("username", usr.username)
            prior = existing.get(usr.username)
            incoming_pw = usr.password

            if not incoming_pw or (prior is not None and incoming_pw == prior.password):
                # blank or unchanged -> keep the stored (already hashed) password
                if prior is not None:
                    usr.password = prior.password
                    usr.must_change_password = prior.must_change_password
                else:
                    # brand-new user without a password: hash whatever was given
                    usr.password = user.hash_password(validate_user_attribute("password", incoming_pw))
                    usr.must_change_password = False
            else:
                # a new plaintext password was provided -> salt+hash it
                usr.password = validate_user_attribute("password", incoming_pw)
                usr.password = user.hash_password(usr.password)
                usr.must_change_password = False

            usr.admin = usr.admin or usr.admin == "True"
            usr.camera = usr.camera or usr.camera == "True"

            new_list.append(usr)

        # Authorization resolves a user by username (current_user_is_admin /
        # get_user use the first match), so duplicate usernames would let a
        # low-privilege session bind to a higher-privileged row. Reject any
        # write that would create a duplicate. (security)
        names = [u.username for u in new_list]
        if len(names) != len(set(names)):
            raise ValueError("duplicate usernames are not allowed")

        users[:] = new_list
        save()
    except Exception:
        main_logger.exception("settings write failed")
        raise

def test():
    return
    sys.exit(0)

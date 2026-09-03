from __future__ import annotations  # PEP 604 'X | None' hints on Python 3.9 (documented 3.7+)
from typing import Any
from dataclasses import dataclass, field, asdict, is_dataclass
import onvif
from onvif import ONVIFCamera
from urllib.parse import urlparse
import glob
import json
import os
import requests
import socket
import sys

from . import settings


def find_onvif_wsdl_dir(package_dir: str | None = None, prefix: str | None = None) -> str | None:
    """Map met de ONVIF wsdl-bestanden van onvif-zeep, of None als die ontbreekt.

    ONVIFCamera zoekt standaard in <site-packages>/wsdl naast het onvif-package.
    De onvif-zeep wheel zet die bestanden echter onder een vaste
    lib/python3.4/site-packages/wsdl in de venv, ongeacht de Python-versie
    (gezien op de Pi met Python 3.7). Kijk daarom eerst naast het package en
    val dan terug op elke lib/python*/site-packages/wsdl onder de venv-prefix.
    """
    package_dir = package_dir or os.path.dirname(onvif.__file__)
    prefix = prefix or sys.prefix
    candidates = [os.path.join(os.path.dirname(package_dir), "wsdl")]
    candidates += sorted(glob.glob(os.path.join(prefix, "lib", "python*", "site-packages", "wsdl")))
    candidates.append(os.path.join(prefix, "wsdl"))
    for d in candidates:
        if os.path.isfile(os.path.join(d, "devicemgmt.wsdl")):
            return d
    return None


# None -> geef de onvif-zeep default door, zodat de foutmelding het ontbrekende pad noemt
ONVIF_WSDL_DIR = find_onvif_wsdl_dir() or os.path.join(os.path.dirname(os.path.dirname(onvif.__file__)), "wsdl")

# camera-preset die niet in het bedieningspaneel getoond wordt (home-positie)
HOME_PRESET_TOKEN = "0"


@dataclass
class Preset:
    token: str
    label: str


@dataclass
class Camera:
    name: str
    url_intern: str
    url_extern: str
    port_http: int
    port_onvif: int
    port_ws: int
    username: str
    password: str

    # Persistente configuratie
    config_presets: list[Preset] = field(default_factory=list)

    # Runtime
    presets: list[Preset] = field(default_factory=list)
    active: str = "0"

    #
    # ONVIF
    #

    # ONVIF-objecten
    _cam: ONVIFCamera | None = field(init=False, default=None, repr=False, metadata={"persist": False})
    _media: Any | None = field(init=False, default=None, repr=False, metadata={"persist": False})
    _ptz: Any | None = field(init=False, default=None, repr=False, metadata={"persist": False})
    _device: Any | None = field(init=False, default=None, repr=False, metadata={"persist": False})
    _profile: Any | None = field(init=False, default=None, repr=False, metadata={"persist": False})
    _PTZ_SPEED = 0.075
    _PTZ_DIRECTIONS = {
        "left":      (-_PTZ_SPEED,  0,  0),
        "right":     ( _PTZ_SPEED,  0,  0),
        "up":        ( 0,  _PTZ_SPEED,  0),
        "down":      ( 0, -_PTZ_SPEED,  0),

        "leftup":    (-_PTZ_SPEED,  _PTZ_SPEED,  0),
        "rightup":   ( _PTZ_SPEED,  _PTZ_SPEED,  0),
        "leftdown":  (-_PTZ_SPEED, -_PTZ_SPEED,  0),
        "rightdown": ( _PTZ_SPEED, -_PTZ_SPEED,  0),

        "zoomadd":   ( 0,  0,  _PTZ_SPEED),
        "zoomdec":   ( 0,  0, -_PTZ_SPEED),
    }

    def connect(self):
        try:
            self._cam = ONVIFCamera(
                self.url_intern,
                self.port_onvif,
                self.username,
                self.password,
                ONVIF_WSDL_DIR,
            )

            self._media = self._cam.create_media_service()
            self._ptz = self._cam.create_ptz_service()
            self._device = self._cam.create_devicemgmt_service()
            self._profile = self._media.GetProfiles()[0]
        except Exception as err:
            raise ConnectionError(
                f"Verbinding met '{self.name}' mislukt"
            ) from err

    def to_dict(self):
        return {
            "name": self.name,
            "url_intern": self.url_intern,
            "url_extern": self.url_extern,
            "port_http": self.port_http,
            "port_onvif": self.port_onvif,
            "port_ws": self.port_ws,
            "username": self.username,
            "password": self.password,
            "config_presets": [
                asdict(p) if is_dataclass(p) else p
                for p in self.config_presets
            ],
            "active": self.active
        }

    @classmethod
    def from_dict(cls, data: dict):
        data = data.copy()

        data["config_presets"] = [
            Preset(**p) for p in data.get("config_presets", [])
        ]

        # Oudere opslag (en de admin-UI) leveren poorten als string; maak er
        # int van als dat kan. Onherstelbare waarden blijven staan zodat het
        # laden van de complete config er niet op stukloopt; update_cameras
        # (settings.validate_camera_attribute) weigert ze wel bij opslaan.
        for key in ("port_http", "port_onvif", "port_ws"):
            try:
                data[key] = int(str(data[key]).strip())
            except (KeyError, TypeError, ValueError):
                pass

        return cls(**data)

    def get_config_preset(self, token: str) -> Preset | None:
        """Zoek een preset in de configuratie."""

        token = str(token)

        for preset in self.config_presets:
            if preset.token == token:
                return preset

        return None

    def load_presets(self):
        """Lees presets uit de camera."""

        camera_presets = self._ptz.GetPresets(
            {"ProfileToken": self._profile.token}
        )

        self.presets.clear()

        for p in camera_presets:

            token = str(p.token)

            # Preset 0 is de home-positie van de camera; die hoort niet in
            # het bedieningspaneel (wel bereikbaar via goto_preset("0")).
            if token == HOME_PRESET_TOKEN:
                continue

            # Gebruik de naam van de camera indien aanwezig
            label = getattr(p, "Name", "") or ""

            # Anders de naam uit de configuratie
            # indien Name = leeg of hetzelfde als Token
            if not label or label == token:
                config = self.get_config_preset(token)
                if config:
                    label = config.label

            # Nog steeds niets
            if not label:
                label = f"Preset {token}"

            self.presets.append(
                Preset(
                    token=token,
                    label=label
                )
            )

        return self.presets

    def goto_preset(self, preset: Preset | str):
        """Ga naar een preset."""

        token = preset.token if isinstance(preset, Preset) else str(preset)

        request = self._ptz.create_type("GotoPreset")
        request.ProfileToken = self._profile.token
        request.PresetToken = token

        self._ptz.GotoPreset(request)

    def set_preset_label(self, token: str, label: str) -> bool:
        """Wijzig het label van een configuratie-preset."""

        for preset in self.config_presets:
            if preset.token == token:
                preset.label = label
                return True

        # Preset bestaat nog niet: voeg hem toe
        self.config_presets.append(
            Preset(
                token=token,
                label=label
            )
        )

        return True

    def get_stream_uri(self, protocol="RTSP") -> str:
        try:
            request = self._media.create_type("GetStreamUri")

            request.StreamSetup = {
                "Stream": "RTP-Unicast",
                "Transport": {
                    "Protocol": protocol
                }
            }

            request.ProfileToken = self._profile.token

            return urlparse(self._media.GetStreamUri(request).Uri).path

        except Exception:
            return False

    def reboot(self):
        """Herstart de camera."""
        
        self._device.SystemReboot()

    def is_onvif_available(self, timeout=3) -> bool:
        try:
            cam = ONVIFCamera(
                self.url_intern,
                self.port_onvif,
                self.username,
                self.password,
                ONVIF_WSDL_DIR,
            )

            device = cam.create_devicemgmt_service()

            device.GetDeviceInformation()

            return True

        except Exception:
            return False

    def move_direction(self, direction: str):
        """Start een beweging op basis van de richting."""

        pan, tilt, zoom = self._PTZ_DIRECTIONS[direction]
        self.move(pan, tilt, zoom)

    def move_stop(self):
        """Stop pan, tilt en zoom."""

        if self._ptz is None:
            raise RuntimeError("Camera is niet verbonden.")

        request = self._ptz.create_type("Stop")
        request.ProfileToken = self._profile.token
        request.PanTilt = True
        request.Zoom = True

        self._ptz.Stop(request)

    def move(
        self,
        pan: float = 0.0,
        tilt: float = 0.0,
        zoom: float = 0.0,
    ):
        """
        Continue PTZ-beweging.

        pan, tilt en zoom liggen tussen -1.0 en +1.0.
        """

        if self._ptz is None:
            raise RuntimeError("Camera is niet verbonden.")

        # Begrens de waarden
        pan = max(-1.0, min(1.0, pan))
        tilt = max(-1.0, min(1.0, tilt))
        zoom = max(-1.0, min(1.0, zoom))

        request = self._ptz.create_type("ContinuousMove")
        request.ProfileToken = self._profile.token

        request.Velocity = {
            "PanTilt": {
                "x": pan,
                "y": tilt,
            },
            "Zoom": {
                "x": zoom,
            },
        }

        self._ptz.ContinuousMove(request)

    # 
    # HTTP API
    #

    def ajaxcom(self, command: dict) -> dict:
        """
        Verstuur een opdracht naar de camera via /ajaxcom.

        Parameters
        ----------
        command
            Python dict met het JSON-commando.

        Returns
        -------
        dict
            Het gedecodeerde JSON-antwoord.
        """

        url = f"http://{self.url_intern}:{self.port_http}/ajaxcom"

        response = requests.post(
            url,
            data={
                "szCmd": json.dumps(command)
            },
            auth=(self.username, self.password),
            timeout=5,
        )

        response.raise_for_status()

        return response.json()

    def get_stream_publish(self, check = True) -> bool:

        response = self.ajaxcom({
            "GetEnv": {
                "StreamPublish": {
                    "nChannel": -1
                }
            }
        })
        
        if check:
            return response["stValue"][0]["stMaster"]["bEnable"] == 1
        else:
            return response["stValue"][0]

    def set_stream_publish(self, enable: bool):
        settings = self.get_stream_publish(False)
        settings["stMaster"]["bEnable"] = int(enable)

        return self.ajaxcom({
            "SetEnv": {
                "StreamPublish": [settings]
            }
        })
    
    def set_focus_mode(self, mode: int = 2):

        if mode not in (1, 2, 3):
            raise ValueError("Mode moet 1 (onepush), 2 (auto) of 3 (manual) zijn.")

        return self.ajaxcom({
            "SetEnv": {
                "VideoParam": [
                    {
                        "nChannel": 0,
                        "stAF": {
                            "emAFMode": mode
                        }
                    }
                ]
            }
        })

    def is_http_available(self, timeout=2) -> bool:
        try:
            url = f"http://{self.url_intern}:{self.port_http}/"

            response = requests.get(
                url,
                auth=(self.username, self.password),
                timeout=timeout,
            )

            return response.status_code < 500

        except requests.RequestException:
            return False

    #
    # COMMON
    #

    def port_open(self, port: int, timeout=1) -> bool:
        try:
            with socket.create_connection(
                (self.url_intern, port),
                timeout=timeout,
            ):
                return True

        except OSError:
            return False

    def test_connection(self):

        return {
            "http_port": self.port_open(self.port_http),
            "onvif_port": self.port_open(self.port_onvif),
            "http": self.is_http_available(),
            "onvif": self.is_onvif_available(),
        }

#
# DEFAULT CAMERA'S
#

def default_cameras():
    """ Default cameras, used as initial and factory defaults """
    result = [
        Camera(
            name="Kerk", 
            url_intern="192.168.1.1", 
            url_extern="west.gergemrijssen.nl", 
            port_http=80, 
            port_onvif=2000, 
            port_ws=8088, 
            username="username", 
            password="password",
            config_presets=[
                Preset(token="0", label="Home"),
                Preset(token="1", label="Podium"),
                Preset(token="2", label="Kansel"),
                Preset(token="3", label="Psalmbord R"),
                Preset(token="4", label="Orgel"),
                Preset(token="5", label="Podium breed"),
                Preset(token="6", label="Doopvont"),
                Preset(token="7", label="Katheder"),
                Preset(token="8", label="Kerkzaal"),
                Preset(token="9", label="Huwelijk"),
                Preset(token="10", label="Belijdenis"),
                Preset(token="11", label="Ouderlingen"),
                Preset(token="12", label="Diakenen"),
                Preset(token="13", label="Cymbelster"),
                Preset(token="14", label="Psalmbord L"),
                Preset(token="15", label="Koor"),
            ]
        ),
        Camera(
            name="Zaal", 
            url_intern="192.168.1.2", 
            url_extern="west.gergemrijssen.nl", 
            port_http=80, 
            port_onvif=2000, 
            port_ws=8088, 
            username="username", 
            password="password",
            config_presets=[
                Preset(token="0", label="Home"),
                Preset(token="1", label="Z3 algemeen"),
                Preset(token="2", label="Z3 uitgezoomd"),
                Preset(token="3", label="Z3 scherm R"),
                Preset(token="4", label="Z3 katheder"),
                Preset(token="5", label="Z3 rechts"),
                Preset(token="11", label="Z2 uitgezoomd"),
                Preset(token="12", label="Z2 scherm"),
                Preset(token="20", label="UTP lamp"),
                Preset(token="21", label="Hal"),
                Preset(token="22", label="Klok"),
            ]
        ),
    ]
    for i, obj in enumerate(result):
        obj.id = i
    return result


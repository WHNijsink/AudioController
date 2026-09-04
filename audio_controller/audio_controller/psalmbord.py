""" Functions to handle Psalmbord in settings.py """

# python standard lib
import json
from json import dumps
from typing import List
from dataclasses import dataclass, field, asdict
import hashlib

# internals
from . import fonts, settings

# external libs
import tornado.web
from tornado.escape import xhtml_escape


#
# Classes and default settings
#

default_fontfamily = fonts.validate_font_name("Samsung", True)
default_fontsize = fonts.validate_font_size(8, True)
default_fontweight = fonts.validate_font_weight(400, True)
default_screens = ['Ps 45:1\n10 GEB:9\nRom. 3:1-10\nPs 89:4\nPs 103:7\nPs 116:1 2 3\n\nHC Zondag 23','']
refreshrates = [1,2,3,4,5,10,15,30,60]


@dataclass
class PsalmbordScreen:
    index: int
    text: str
    size: int


@dataclass
class Psalmbord:
    fontfamily: str = default_fontfamily
    fontsize: int = default_fontsize
    fontweight: int = default_fontweight
    active: int = 1 # if 0, show empty screen (not to confuse with enable_psalmbord)
    screens: List[PsalmbordScreen] = field(default_factory=list)
    refreshrate: int = 10
    html_hash: str = ""

    #
    # Generate HTML
    #

    def psalmbord_as_html(self) -> str:
        """ Create a html string to display the psalmbord in the browser """

        # guard against an empty screen list or an out-of-range active index
        if not self.screens or not (0 <= self.active < len(self.screens)):
            return ""
        # screens hold dicts when set via the SPA/json but PsalmbordScreen
        # dataclasses when built by settings.restore(); accept both
        screen = self.screens[self.active]
        text = screen["text"] if isinstance(screen, dict) else screen.text
        regels = text.splitlines()

        content = ""
        for r in regels:
            css = "regel font_weight"
            # defensive: fall back to the default font class if an invalid
            # fontfamily was ever persisted, so the public board cannot be
            # DoS'd by a KeyError.
            css += f" {fonts.fonts.get(self.fontfamily) or fonts.fonts[default_fontfamily]}"
            if r.startswith('_'):
                css += " title"
                r = r[1:]

            content += f"<div class='{css}'>"

            col = r.strip().split(":")
            if len(col) > 1:
                # regel with three columns
                content += "<span class='col1'>"
                for col1 in col[0].split(" "):
                    if col1.strip() != "":
                        content += f"<span>{xhtml_escape(col1)}</span>"
                content += "</span>"

                content += "<span class='col2'>:</span>"

                content += "<span class='col3'>"
                for col3 in col[1].split(" "):
                    if col3.strip() != "":
                        content += f"<span>{xhtml_escape(col3)}</span>"
                content += "</span>"
            else:
                # regel without columns
                """ replace optional ";" with ":" to prevent splitting and alignment """
                regel_text = r.replace(";",":")
                content += f"<span class='no-col'>{xhtml_escape(regel_text)}</span>"
            
            content += "</div>\n"

        return content

    #
    # Updates
    #

    def update_psalmbord(self, fontfamily, fontsize: int, fontweight, active: int, screens: List[PsalmbordScreen], refreshrate: int):
        temp = Psalmbord(
            fontfamily = str(fontfamily),
            fontsize = int(fontsize),
            fontweight = int(fontweight),
            active = int(active),
            screens = screens,
            refreshrate = int(refreshrate)
        )

        # Validate the INCOMING values (temp), not the already-stored self.*
        # (which are always valid, making the check a no-op). Reject the update
        # if a font value is outside the allowlist, so an invalid fontfamily can
        # never reach the board CSS class / camera-page font-family.
        if not fonts.validate_font_name(temp.fontfamily):
            return None
        if not fonts.validate_font_size(temp.fontsize):
            return None
        if not fonts.validate_font_weight(temp.fontweight):
            return None

        self.fontfamily = temp.fontfamily
        self.fontsize = temp.fontsize
        self.fontweight = temp.fontweight
        self.active = temp.active
        self.screens = temp.screens
        self.refreshrate = temp.refreshrate

        self.refresh_html_hash()

        settings.save()
        return self

    def _active_text(self) -> str:
        """Text of the active screen, or '' if there is none. Handles both dict
        and PsalmbordScreen entries and guards an out-of-range active index (the
        same guard psalmbord_as_html uses)."""
        if not self.screens or not (0 <= self.active < len(self.screens)):
            return ""
        screen = self.screens[self.active]
        return screen["text"] if isinstance(screen, dict) else screen.text

    def refresh_html_hash(self):
        """Recompute the content hash used to skip unchanged board refreshes
        (Guis f9e284c). Always a real sha256 (even of ''), so it never collides
        with the client's initial empty hash and leaves the board blank."""
        self.html_hash = hashlib.sha256(self._active_text().encode("utf-8")).hexdigest()



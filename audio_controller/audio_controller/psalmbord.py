""" Functions to handle Psalmbord in settings.py """

# python standard lib
import json
from json import dumps
from typing import List
from dataclasses import dataclass, field, asdict

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

    #
    # Generate HTML
    #

    def psalmbord_as_html(self) -> str:
        """ Create a html string to display the psalmbord in the browser """

        # guard against an empty screen list or an out-of-range active index
        if not self.screens or not (0 <= self.active < len(self.screens)):
            return ""
        regels = self.screens[self.active]["text"].splitlines()

        content = ""
        for r in regels:
            css = "regel font_weight"
            css += f" {fonts.fonts[self.fontfamily]}"
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

        if not fonts.validate_font_name(self.fontfamily, True):
            return None
        if not fonts.validate_font_size(self.fontsize, True):
            return None
        if not fonts.validate_font_weight(self.fontweight, True):
            return None

        self.fontfamily = temp.fontfamily
        self.fontsize = temp.fontsize
        self.fontweight = temp.fontweight
        self.active = temp.active
        self.screens = temp.screens
        self.refreshrate = temp.refreshrate

        settings.save()
        return self



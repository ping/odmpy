# Copyright (C) 2021 github.com/ping
#
# This file is part of odmpy.
#
# odmpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# odmpy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with odmpy.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import platform
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict

from mutagen.mp3 import MP3  # type: ignore[import]

#
# Small utility type functions used across the board
#

TIMESTAMP_RE = re.compile(
    r"^((?P<hr>[0-9]+):)?(?P<min>[0-9]+):(?P<sec>[0-9]+)(\.(?P<ms>[0-9]+))?$"
)
ILLEGAL_WIN_PATH_CHARS_RE = re.compile(r'[<>:"/\\|?*]')


def plural_or_singular_noun(
    value: float, singular_noun: str, plural_noun: str = ""
) -> str:
    """
    Returns the appropriate noun based on the value provided.

    :param value:
    :param singular_noun:
    :param plural_noun:
    :return:
    """
    if not plural_noun:
        plural_noun = singular_noun + "s"
    return plural_noun if value != 1 else singular_noun


def sanitize_path(text: str, sub_text: str = "-") -> str:
    """
    Strips invalid characters from a local file path component.

    :param text:
    :param sub_text:
    :return:
    """
    if os.name == "nt" or platform.system().lower() == "windows":
        # just replacing `os.sep` is not enough on Windows
        # ref https://github.com/ping/odmpy/issues/30
        text = ILLEGAL_WIN_PATH_CHARS_RE.sub(sub_text, text)

    text = text.replace(os.sep, sub_text)
    # also strip away non-printable chars just to be safe
    return "".join(c for c in text if c.isprintable())


def get_element_text(ele: Optional[ET.Element]) -> str:
    """
    Returns the element text

    :param ele:
    :return:
    """
    if (ele is not None) and ele.text:
        return ele.text or ""
    return ""


def set_ele_attributes(ele: ET.Element, attributes: Dict) -> None:
    """
    Set multiple attributes on an Element

    :param ele: Element
    :param attributes:
    :return:
    """
    for k, v in attributes.items():
        ele.set(k, v)


def parse_duration_to_milliseconds(text: str) -> int:
    """
    Converts a duration string into milliseconds

    :param text: A duration string, e.g. "10:15", "10:15.300", "1:10:15"
    :return:
    """
    mobj = TIMESTAMP_RE.match(text)
    if not mobj:
        raise ValueError(f"Invalid timestamp text: {text}")
    hours = int(mobj.group("hr") or 0)
    minutes = int(mobj.group("min") or 0)
    seconds = int(mobj.group("sec") or 0)
    milliseconds = int((mobj.group("ms") or "0").ljust(3, "0"))
    return hours * 60 * 60 * 1000 + minutes * 60 * 1000 + seconds * 1000 + milliseconds


def parse_duration_to_seconds(text: str) -> int:
    """
    Converts a duration string into seconds

    :param text: A duration string, e.g. "10:15", "10:15.300", "1:10:15"
    :return:
    """
    return round(parse_duration_to_milliseconds(text) / 1000.0)


def mp3_duration_ms(filename: Path) -> int:
    # Ref: https://github.com/ping/odmpy/pull/3
    # returns the length of the mp3 in ms

    # eyeD3's audio length function:
    # audiofile.info.time_secs
    # returns incorrect times due to its header computation
    # mutagen does not have this issue
    audio = MP3(filename)
    if not audio.info:
        raise ValueError(f"Unable to parse MP3 info from: {filename}")
    return int(round(audio.info.length * 1000))


# From django
def slugify(value: str, allow_unicode: bool = False) -> str:
    """
    Convert to ASCII if 'allow_unicode' is False. Convert spaces to hyphens.
    Remove characters that aren't alphanumerics, underscores, or hyphens.
    Convert to lowercase. Also strip leading and trailing whitespace.
    """
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
        value = re.sub(r"[^\w\s-]", "", value, flags=re.U).strip().lower()
        return re.sub(r"[-\s]+", "-", value, flags=re.U)
    value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)

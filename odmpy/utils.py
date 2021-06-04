# -*- coding: utf-8 -*-

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
import io
import re
import unicodedata
from mutagen.mp3 import MP3
from PIL import Image


def mp3_duration_ms(filename):
    # Ref: https://github.com/ping/odmpy/pull/3
    # returns the length of the mp3 in ms

    # eyeD3's audio length function:
    # audiofile.info.time_secs
    # returns incorrect times due to it's header computation
    # mutagen does not have this issue
    audio = MP3(filename)
    return int(round(audio.info.length * 1000))


def unescape_html(text):
    """py2/py3 compatible html unescaping"""
    try:
        import html
        return html.unescape(text)
    except ImportError:
        import HTMLParser
        parser = HTMLParser.HTMLParser()
        return parser.unescape(text)


# From django
def slugify(value, allow_unicode=False):
    """
    Convert to ASCII if 'allow_unicode' is False. Convert spaces to hyphens.
    Remove characters that aren't alphanumerics, underscores, or hyphens.
    Convert to lowercase. Also strip leading and trailing whitespace.
    """
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
        value = re.sub(r'[^\w\s-]', '', value, flags=re.U).strip().lower()
        return re.sub(r'[-\s]+', '-', value, flags=re.U)
    value = unicodedata.normalize(
        'NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value).strip().lower()
    return re.sub(r'[-\s]+', '-', value)


def resize(cover):
    """
    Change the aspect ratio of the cover image to 1:1 using the
    image width as the default size and preserving the quality
    as close to the original as possible.
    Do it in memory so the image is only written to disk once.
    """
    img = Image.open(io.BytesIO(cover))
    img = img.resize(((img.size[0]), (img.size[0])), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=95, subsampling=0)
    return buf.getvalue()

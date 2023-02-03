# -*- coding: utf-8 -*-

# Copyright (C) 2018 github.com/ping
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

import argparse
import os
import subprocess
import sys
import datetime
import time
import xml.etree.ElementTree
import uuid
import hashlib
import base64
from collections import OrderedDict
import re
import logging
import math
import json
from urllib.parse import urlparse

try:
    from functools import reduce
except ImportError:
    pass

import requests
from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import HTTPError, ConnectionError
from clint.textui import colored, progress
import eyed3
from eyed3.utils import art
from .utils import unescape_html, slugify, mp3_duration_ms
from .constants import (
    OMC,
    OS,
    UA,
    UA_LONG,
    UNSUPPORTED_PARSER_ENTITIES,
    PERFORMER_FID,
)
from .libby import LibbyClient

logger = logging.getLogger(__file__)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
logger.addHandler(ch)
logger.setLevel(logging.INFO)

__version__ = "0.5.0"  # also update ../setup.py

MARKER_TIMESTAMP_MMSS = r"(?P<min>[0-9]+):(?P<sec>[0-9]+)\.(?P<ms>[0-9]+)"
MARKER_TIMESTAMP_HHMMSS = (
    r"(?P<hr>[0-9]+):(?P<min>[0-9]+):(?P<sec>[0-9]+)\.(?P<ms>[0-9]+)"
)


def process_odm(odm_file, args, cleanup_odm_license=False):
    """
    Main working method to process an odm file.
    :param odm_file:
    :param args:
    :param cleanup_odm_license:
    :return:
    """
    ffmpeg_loglevel = "info" if logger.level == logging.DEBUG else "error"
    xml_doc = xml.etree.ElementTree.parse(odm_file)
    root = xml_doc.getroot()
    metadata = None
    for t in root.itertext():
        if not t.startswith("<Metadata>"):
            continue
        # remove invalid '&' char
        text = re.sub(r"\s&\s", " &amp; ", t)
        try:
            metadata = xml.etree.ElementTree.fromstring(text)
        except xml.etree.ElementTree.ParseError:
            # [TODO]: Find a more generic solution instead of patching entities, maybe lxml?
            # Ref: https://github.com/ping/odmpy/issues/19
            patched_text = "<!DOCTYPE xml [{patch}]>{text}".format(
                patch="".join(
                    [
                        f'<!ENTITY {entity} "{replacement}">'
                        for entity, replacement in UNSUPPORTED_PARSER_ENTITIES.items()
                    ]
                ),
                text=text,
            )
            metadata = xml.etree.ElementTree.fromstring(patched_text)
        break

    debug_meta = {}

    title = metadata.find("Title").text
    cover_url = (
        metadata.find("CoverUrl").text if metadata.find("CoverUrl") is not None else ""
    )
    authors = [
        unescape_html(c.text)
        for c in metadata.find("Creators")
        if "Author" in c.attrib.get("role", "")
    ]
    if not authors:
        authors = [
            unescape_html(c.text)
            for c in metadata.find("Creators")
            if "Editor" in c.attrib.get("role", "")
        ]
    if not authors:
        authors = [unescape_html(c.text) for c in metadata.find("Creators")]
    narrators = [
        unescape_html(c.text)
        for c in metadata.find("Creators")
        if "Narrator" in c.attrib.get("role", "")
    ]
    publisher = metadata.find("Publisher").text
    description = (
        metadata.find("Description").text
        if metadata.find("Description") is not None
        else ""
    )

    debug_meta["meta"] = {
        "title": title,
        "coverUrl": cover_url,
        "authors": authors,
        "publisher": publisher,
        "description": description,
    }

    # View Book Info
    if args.command_name == "info":
        if args.format == "text":
            logger.info(f"{'Title:':10} {colored.blue(title)}")
            logger.info(
                "{:10} {}".format(
                    "Creators:",
                    colored.blue(
                        ", ".join(
                            [
                                f"{c.text} ({c.attrib['role']})"
                                for c in metadata.find("Creators")
                            ]
                        )
                    ),
                )
            )
            logger.info(f"{'Publisher:':10} {metadata.find('Publisher').text}")
            logger.info(
                f"{'Subjects:':10} {', '.join([c.text for c in metadata.find('Subjects')])}"
            )
            logger.info(
                f"{'Languages:':10} {', '.join([c.text for c in metadata.find('Languages')])}"
            )
            logger.info(f"{'Description:':10}\n{metadata.find('Description').text}")

            for formats in root.findall("Formats"):
                for f in formats:
                    logger.info(f"\n{'Format:':10} {f.attrib['name']}")
                    parts = f.find("Parts")
                    for p in parts:
                        logger.info(
                            f"* {p.attrib['name']} - {p.attrib['duration']} ({math.ceil(1.0 * int(p.attrib['filesize']) / 1024):,.0f}kB)"
                        )

        elif args.format == "json":
            result = {
                "title": title,
                "creators": [
                    f"{c.text} ({c.attrib['role']})" for c in metadata.find("Creators")
                ],
                "publisher": metadata.find("Publisher").text,
                "subjects": [c.text for c in metadata.find("Subjects")],
                "languages": [c.text for c in metadata.find("Languages")],
                "description": metadata.find("Description").text,
                "formats": [],
            }

            for formats in root.findall("Formats"):
                for f in formats:
                    parts = []
                    total_secs = 0
                    for p in f.find("Parts"):
                        part_duration = p.attrib["duration"]
                        # part duration can look like '%M:%S.%f' or '%H:%M:%S.%f'
                        try:
                            mins, secs = map(float, part_duration.split(":"))
                            hrs = 0
                        except ValueError:  # ValueError: too many values to unpack
                            hrs, mins, secs = map(float, part_duration.split(":"))
                        total_secs += hrs * 60 * 60 + secs + mins * 60
                        parts.append(
                            {
                                "name": p.attrib["name"],
                                "duration": part_duration,
                                "filesize": f"{math.ceil(1.0 * int(p.attrib['filesize']) / 1024):,.0f}kB",
                            }
                        )
                    result["formats"].append(
                        {"format": f.attrib["name"], "parts": parts}
                    )
                    # in case there are multiple formats, only need to store it once
                    if "total_duration" not in result:
                        result["total_duration"] = {
                            "total_minutes": round(total_secs / 60),
                            "total_seconds": round(total_secs),
                        }

            logger.info(json.dumps(result))

        sys.exit()

    session = requests.Session()
    custom_adapter = HTTPAdapter(
        max_retries=Retry(total=args.retries, backoff_factor=0.1)
    )
    for prefix in ("http://", "https://"):
        session.mount(prefix, custom_adapter)

    # Download Book
    download_baseurl = ""
    download_parts = []
    for formats in root.findall("Formats"):
        for f in formats:
            protocols = f.find("Protocols")
            for p in protocols:
                if p.attrib.get("method", "") != "download":
                    continue
                download_baseurl = p.attrib["baseurl"]
                break
            parts = f.find("Parts")
            for p in parts:
                download_parts.append(p.attrib)
    debug_meta["download_parts"] = download_parts

    logger.info(
        f'Downloading "{colored.blue(title, bold=True)}" by "{colored.blue(", ".join(authors))}" in {len(download_parts)} part(s)...'
    )

    # declare book folder/file names here together so we can catch problems from too long names
    book_folder = os.path.join(
        args.download_dir,
        f"{title.replace(os.sep, '-')} - {', '.join(authors).replace(os.sep, '-')}",
    )
    if args.no_book_folder:
        book_folder = args.download_dir

    # for merged mp3
    book_filename = os.path.join(
        book_folder,
        f"{title.replace(os.sep, '-')} - {', '.join(authors).replace(os.sep, '-')}.mp3",
    )
    # for merged m4b
    book_m4b_filename = os.path.join(
        book_folder,
        f"{title.replace(os.sep, '-')} - {', '.join(authors).replace(os.sep, '-')}.m4b",
    )

    if not os.path.exists(book_folder):
        try:
            os.makedirs(book_folder)
        except OSError as exc:
            # ref http://www.ioplex.com/~miallen/errcmpp.html
            if exc.errno not in (36, 63) or args.no_book_folder:
                raise

            # Ref OSError: [Errno 36] File name too long https://github.com/ping/odmpy/issues/5
            # create book folder, file with just the title
            book_folder = os.path.join(
                args.download_dir, f"{title.replace(os.sep, '-')}"
            )
            os.makedirs(book_folder)

            book_filename = os.path.join(
                book_folder, f"{title.replace(os.sep, '-')}.mp3"
            )
            book_m4b_filename = os.path.join(
                book_folder, f"{title.replace(os.sep, '-')}.m4b"
            )

    # check early if a merged file is already saved
    if args.merge_output and os.path.isfile(
        book_filename if args.merge_format == "mp3" else book_m4b_filename
    ):
        logger.warning(
            'Already saved "{}"'.format(
                colored.magenta(
                    book_filename if args.merge_format == "mp3" else book_m4b_filename
                )
            )
        )
        if cleanup_odm_license and os.path.isfile(odm_file):
            try:
                os.remove(odm_file)
            except Exception as e:  # pylint: disable=broad-except
                logger.warning(f'Error deleting "{odm_file}": {str(e)}')
        sys.exit()

    cover_filename = os.path.join(book_folder, "cover.jpg")
    debug_filename = os.path.join(book_folder, "debug.json")
    if not os.path.isfile(cover_filename) and cover_url:
        try:
            square_cover_url_params = {
                "type": "auto",
                "width": 510,
                "height": 510,
                "force": "true",
                "quality": 80,
                "url": urlparse(cover_url).path,
            }
            # credit: https://github.com/lullius/pylibby/pull/18
            # this endpoint produces a resized version of the cover
            cover_res = session.get(
                "https://ic.od-cdn.com/resize",
                params=square_cover_url_params,
                headers={"User-Agent": UA},
                timeout=args.timeout,
            )
            cover_res.raise_for_status()
            with open(cover_filename, "wb") as outfile:
                outfile.write(cover_res.content)
        except requests.exceptions.HTTPError as he:
            logger.warning(
                f"Error downloading square cover: {colored.red(str(he), bold=True)}"
            )
            # fallback to original cover url
            try:
                cover_res = session.get(
                    cover_url,
                    headers={"User-Agent": UA},
                    timeout=args.timeout,
                )
                cover_res.raise_for_status()
                with open(cover_filename, "wb") as outfile:
                    outfile.write(cover_res.content)
            except requests.exceptions.HTTPError as he2:
                logger.warning(
                    f"Error downloading cover: {colored.red(str(he2), bold=True)}"
                )

    acquisition_url = root.find("License").find("AcquisitionUrl").text
    media_id = root.attrib["id"]

    client_id = str(uuid.uuid1()).upper()
    raw_hash = f"{client_id}|{OMC}|{OS}|ELOSNOC*AIDEM*EVIRDREVO"
    m = hashlib.sha1(raw_hash.encode("utf-16-le"))
    license_hash = base64.b64encode(m.digest())

    # Extract license
    # License file is downloadable only once per odm
    # so we keep it in case downloads fail
    _, odm_filename = os.path.split(odm_file)
    license_file = os.path.join(
        args.download_dir, odm_filename.replace(".odm", ".license")
    )

    if os.path.isfile(license_file):
        logger.warning(f"Already downloaded license file: {license_file}")
    else:
        # download license file
        params = OrderedDict(
            [
                ("MediaID", media_id),
                ("ClientID", client_id),
                ("OMC", OMC),
                ("OS", OS),
                ("Hash", license_hash),
            ]
        )

        license_res = session.get(
            acquisition_url,
            params=params,
            headers={"User-Agent": UA},
            timeout=args.timeout,
            stream=True,
        )
        try:
            license_res.raise_for_status()
            with open(license_file, "wb") as outfile:
                for chunk in license_res.iter_content(1024):
                    outfile.write(chunk)
            logger.debug(f"Saved license file {license_file}")

        except HTTPError as he:
            if he.response.status_code == 404:
                # odm file has expired
                logger.error(
                    f'The loan file "{args.odm_file}" has expired. Please download again.'
                )
            else:
                logger.error(he.response.content)
            sys.exit(1)
        except ConnectionError as ce:
            logger.error(f"ConnectionError: {str(ce)}")
            sys.exit(1)

    license_xml_doc = xml.etree.ElementTree.parse(license_file)
    license_root = license_xml_doc.getroot()

    ns = "{http://license.overdrive.com/2008/03/License.xsd}"

    license_client = license_root.find(f"{ns}SignedInfo").find(f"{ns}ClientID")
    license_client_id = license_client.text

    with open(license_file, "r", encoding="utf-8") as lic_file:
        lic_file_contents = lic_file.read()

    cover_bytes = None
    if os.path.isfile(cover_filename):
        with open(cover_filename, "rb") as f:
            cover_bytes = f.read()

    track_count = 0
    file_tracks = []
    keep_cover = args.always_keep_cover
    audio_lengths_ms = []
    for p in download_parts:
        part_number = int(p["number"])
        part_filename = os.path.join(
            book_folder,
            f"{slugify(f'{title} - Part {part_number:02d}', allow_unicode=True)}.mp3",
        )
        part_tmp_filename = f"{part_filename}.part"
        part_file_size = int(p["filesize"])
        part_url_filename = p["filename"]
        part_download_url = f"{download_baseurl}/{part_url_filename}"
        part_markers = []

        if os.path.isfile(part_filename):
            logger.warning(f"Already saved {colored.magenta(part_filename)}")
        else:
            try:
                part_download_res = session.get(
                    part_download_url,
                    headers={
                        "User-Agent": UA,
                        "ClientID": license_client_id,
                        "License": lic_file_contents,
                    },
                    timeout=args.timeout,
                    stream=True,
                )

                part_download_res.raise_for_status()

                chunk_size = 1024 * 1024
                expected_chunk_count = math.ceil(1.0 * part_file_size / chunk_size)
                with open(part_tmp_filename, "wb") as outfile:
                    for chunk in progress.bar(
                        part_download_res.iter_content(chunk_size=chunk_size),
                        label=f"Part {part_number}",
                        expected_size=expected_chunk_count,
                        hide=args.hide_progress,
                    ):
                        if chunk:
                            outfile.write(chunk)

                # try to remux file to remove mp3 lame tag errors
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    ffmpeg_loglevel,
                    "-i",
                    part_tmp_filename,
                    "-c:a",
                    "copy",
                    "-c:v",
                    "copy",
                    part_filename,
                ]
                try:
                    exit_code = subprocess.call(cmd)
                    if exit_code:
                        logger.warning(f"ffmpeg exited with the code: {exit_code!s}")
                        logger.warning(f"Command: {' '.join(cmd)!s}")
                        os.rename(part_tmp_filename, part_filename)
                    else:
                        os.remove(part_tmp_filename)
                except Exception as ffmpeg_ex:  # pylint: disable=broad-except
                    logger.warning(f"Error executing ffmpeg: {str(ffmpeg_ex)}")
                    os.rename(part_tmp_filename, part_filename)

            except HTTPError as he:
                logger.error(f"HTTPError: {str(he)}")
                logger.debug(he.response.content)
                sys.exit(1)

            except ConnectionError as ce:
                logger.error(f"ConnectionError: {str(ce)}")
                sys.exit(1)

        try:
            # Fill id3 info for mp3 part
            audiofile = eyed3.load(part_filename)
            if not audiofile.tag:
                audiofile.initTag()
            if not audiofile.tag.title:
                audiofile.tag.title = f"{title}"
            if not audiofile.tag.album:
                audiofile.tag.album = f"{title}"
            if not audiofile.tag.artist:
                audiofile.tag.artist = f"{authors[0]}"
            if not audiofile.tag.album_artist:
                audiofile.tag.album_artist = f"{authors[0]}"
            if not audiofile.tag.track_num:
                audiofile.tag.track_num = (part_number, len(download_parts))
            if narrators and not audiofile.tag.getTextFrame(PERFORMER_FID):
                audiofile.tag.setTextFrame(PERFORMER_FID, f"{narrators[0]}")
            if not audiofile.tag.publisher:
                audiofile.tag.publisher = f"{publisher}"
            if eyed3.id3.frames.COMMENT_FID not in audiofile.tag.frame_set:
                audiofile.tag.comments.set(f"{description}", description="Description")
            if cover_bytes:
                audiofile.tag.images.set(
                    art.TO_ID3_ART_TYPES[art.FRONT_COVER][0],
                    cover_bytes,
                    "image/jpeg",
                    description="Cover",
                )
            audiofile.tag.save()

            audio_lengths_ms.append(mp3_duration_ms(part_filename))

            # Extract OD chapter info from mp3s for use in merged file
            for frame in audiofile.tag.frame_set.get(eyed3.id3.frames.USERTEXT_FID, []):
                if frame.description != "OverDrive MediaMarkers":
                    continue
                if frame.text:
                    try:
                        tree = xml.etree.ElementTree.fromstring(frame.text)
                    except UnicodeEncodeError:
                        tree = xml.etree.ElementTree.fromstring(
                            frame.text.encode("ascii", "ignore").decode("ascii")
                        )

                    for m in tree.iter("Marker"):
                        marker_name = m.find("Name").text.strip()
                        marker_timestamp = m.find("Time").text
                        timestamp = None
                        ts_mark = 0
                        # 2 timestamp formats found
                        for r in ("%M:%S.%f", "%H:%M:%S.%f"):
                            try:
                                timestamp = time.strptime(marker_timestamp, r)
                                ts = datetime.timedelta(
                                    hours=timestamp.tm_hour,
                                    minutes=timestamp.tm_min,
                                    seconds=timestamp.tm_sec,
                                )
                                ts_mark = int(1000 * ts.total_seconds())
                                break
                            except ValueError:
                                pass

                        if not timestamp:
                            # some invalid timestamp string, e.g. 60:15.00
                            mobj = re.match(MARKER_TIMESTAMP_HHMMSS, marker_timestamp)
                            if mobj:
                                ts_mark = (
                                    int(mobj.group("hr")) * 60 * 60 * 1000
                                    + int(mobj.group("min")) * 60 * 1000
                                    + int(mobj.group("sec")) * 1000
                                    + int(mobj.group("ms"))
                                )
                            else:
                                mobj = re.match(MARKER_TIMESTAMP_MMSS, marker_timestamp)
                                if mobj:
                                    ts_mark = (
                                        int(mobj.group("min")) * 60 * 1000
                                        + int(mobj.group("sec")) * 1000
                                        + int(mobj.group("ms"))
                                    )
                                else:
                                    raise ValueError(
                                        f"Invalid marker timestamp: {marker_timestamp}"
                                    )

                        track_count += 1
                        part_markers.append(
                            (f"ch{track_count:02d}", marker_name, ts_mark)
                        )
                break

            if (
                args.add_chapters
                and not args.merge_output
                and not audiofile.tag.table_of_contents
            ):
                # set the chapter marks
                generated_markers = []
                for j, file_marker in enumerate(part_markers):
                    generated_markers.append(
                        {
                            "id": file_marker[0],
                            "text": file_marker[1],
                            "start_time": int(file_marker[2]),
                            "end_time": int(
                                round(audiofile.info.time_secs * 1000)
                                if j == (len(part_markers) - 1)
                                else part_markers[j + 1][2]
                            ),
                        }
                    )

                toc = audiofile.tag.table_of_contents.set(
                    "toc".encode("ascii"),
                    toplevel=True,
                    ordered=True,
                    child_ids=[],
                    description="Table of Contents",
                )

                for i, m in enumerate(generated_markers):
                    title_frameset = eyed3.id3.frames.FrameSet()
                    title_frameset.setTextFrame(
                        eyed3.id3.frames.TITLE_FID, f"{m['text']}"
                    )

                    chap = audiofile.tag.chapters.set(
                        m["id"].encode("ascii"),
                        times=(m["start_time"], m["end_time"]),
                        sub_frames=title_frameset,
                    )
                    toc.child_ids.append(chap.element_id)
                    start_time = datetime.timedelta(milliseconds=m["start_time"])
                    end_time = datetime.timedelta(milliseconds=m["end_time"])
                    logger.debug(
                        f'Added chap tag => {colored.cyan(m["id"])}: {start_time}-{end_time} '
                        f'"{colored.cyan(m["text"])}" to "{colored.blue(part_filename)}"'
                    )

                audiofile.tag.save()

        except Exception as e:  # pylint: disable=broad-except
            logger.warning(f"Error saving ID3: {colored.red(str(e), bold=True)}")
            keep_cover = True

        logger.info(f'Saved "{colored.magenta(part_filename)}"')

        file_tracks.append(
            {
                "file": part_filename,
                "markers": part_markers,
            }
        )
    # end loop: for p in download_parts:

    debug_meta["audio_lengths_ms"] = audio_lengths_ms
    debug_meta["file_tracks"] = file_tracks

    if args.merge_output:
        logger.info(
            'Generating "{}"...'.format(
                colored.magenta(
                    book_filename if args.merge_format == "mp3" else book_m4b_filename
                )
            )
        )

        # We can't directly generate a m4b here even if specified because eyed3 doesn't support m4b/mp4
        temp_book_filename = f"{book_filename}.part"
        cmd = [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            ffmpeg_loglevel,
        ]
        if not args.hide_progress:
            cmd.append("-stats")
        cmd.extend(
            [
                "-i",
                f"concat:{'|'.join([ft['file'] for ft in file_tracks])}",
                "-acodec",
                "copy",
                "-b:a",
                "64k",  # explicitly set audio bitrate
                "-f",
                "mp3",
                temp_book_filename,
            ]
        )
        exit_code = subprocess.call(cmd)

        if exit_code:
            logger.error(f"ffmpeg exited with the code: {exit_code!s}")
            logger.error(f"Command: {' '.join(cmd)!s}")
            sys.exit(exit_code)
        os.rename(temp_book_filename, book_filename)

        audiofile = eyed3.load(book_filename)
        audiofile.tag.title = f"{title}"
        if not audiofile.tag.album:
            audiofile.tag.album = f"{title}"
        if not audiofile.tag.artist:
            audiofile.tag.artist = f"{authors[0]}"
        if not audiofile.tag.album_artist:
            audiofile.tag.album_artist = f"{authors[0]}"
        if narrators and not audiofile.tag.getTextFrame(PERFORMER_FID):
            audiofile.tag.setTextFrame(PERFORMER_FID, f"{narrators[0]}")
        if not audiofile.tag.publisher:
            audiofile.tag.publisher = f"{publisher}"
        if eyed3.id3.frames.COMMENT_FID not in audiofile.tag.frame_set:
            audiofile.tag.comments.set(f"{description}", description="Description")

        if args.add_chapters and not audiofile.tag.table_of_contents:
            merged_markers = []
            for i, f in enumerate(file_tracks):
                prev_tracks_len_ms = (
                    0 if i == 0 else reduce(lambda x, y: x + y, audio_lengths_ms[0:i])
                )
                this_track_endtime_ms = int(
                    reduce(lambda x, y: x + y, audio_lengths_ms[0 : i + 1])
                )
                file_markers = f["markers"]
                for j, file_marker in enumerate(file_markers):
                    merged_markers.append(
                        {
                            "id": file_marker[0],
                            "text": f"{file_marker[1]}",
                            "start_time": int(file_marker[2]) + prev_tracks_len_ms,
                            "end_time": int(
                                this_track_endtime_ms
                                if j == (len(file_markers) - 1)
                                else file_markers[j + 1][2] + prev_tracks_len_ms
                            ),
                        }
                    )
            debug_meta["merged_markers"] = merged_markers

            toc = audiofile.tag.table_of_contents.set(
                "toc".encode("ascii"),
                toplevel=True,
                ordered=True,
                child_ids=[],
                description="Table of Contents",
            )

            for i, m in enumerate(merged_markers):
                title_frameset = eyed3.id3.frames.FrameSet()
                title_frameset.setTextFrame(eyed3.id3.frames.TITLE_FID, f"{m['text']}")
                chap = audiofile.tag.chapters.set(
                    m["id"].encode("ascii"),
                    times=(m["start_time"], m["end_time"]),
                    sub_frames=title_frameset,
                )
                toc.child_ids.append(chap.element_id)
                start_time = datetime.timedelta(milliseconds=m["start_time"])
                end_time = datetime.timedelta(milliseconds=m["end_time"])
                logger.debug(
                    f'Added chap tag => {colored.cyan(m["id"])}: {start_time}-{end_time} '
                    f'"{colored.cyan(m["text"])}" to "{colored.blue(book_filename)}"'
                )

        audiofile.tag.save()

        if args.merge_format == "mp3":
            logger.info(
                'Merged files into "{}"'.format(
                    colored.magenta(
                        book_filename
                        if args.merge_format == "mp3"
                        else book_m4b_filename
                    )
                )
            )

        if args.merge_format == "m4b":
            temp_book_m4b_filename = f"{book_m4b_filename}.part"
            cmd = [
                "ffmpeg",
                "-y",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                ffmpeg_loglevel,
            ]
            if not args.hide_progress:
                cmd.append("-stats")
            cmd.extend(
                [
                    "-i",
                    book_filename,
                ]
            )
            if os.path.isfile(cover_filename):
                cmd.extend(["-i", cover_filename])

            cmd.extend(
                [
                    "-map",
                    "0:a",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "64k",  # explicitly set audio bitrate
                ]
            )
            if os.path.isfile(cover_filename):
                cmd.extend(
                    [
                        "-map",
                        "1:v",
                        "-c:v",
                        "copy",
                        "-disposition:v:0",
                        "attached_pic",
                    ]
                )

            cmd.extend(["-f", "mp4", temp_book_m4b_filename])
            exit_code = subprocess.call(cmd)

            if exit_code:
                logger.error(f"ffmpeg exited with the code: {exit_code!s}")
                logger.error(f"Command: {' '.join(cmd)!s}")
                sys.exit(exit_code)

            os.rename(temp_book_m4b_filename, book_m4b_filename)
            logger.info(f'Merged files into "{colored.magenta(book_m4b_filename)}"')
            try:
                os.remove(book_filename)
            except Exception as e:  # pylint: disable=broad-except
                logger.warning(f'Error deleting "{book_filename}": {str(e)}')

        if not args.keep_mp3:
            for f in file_tracks:
                try:
                    os.remove(f["file"])
                except Exception as e:  # pylint: disable=broad-except
                    logger.warning(f'Error deleting "{f["file"]}": {str(e)}')

    if cleanup_odm_license:
        for target_file in [odm_file, license_file]:
            if os.path.isfile(target_file):
                try:
                    os.remove(target_file)
                except Exception as e:  # pylint: disable=broad-except
                    logger.warning(f'Error deleting "{target_file}": {str(e)}')

    if not keep_cover and os.path.isfile(cover_filename):
        try:
            os.remove(cover_filename)
        except Exception as e:  # pylint: disable=broad-except
            logger.warning(f'Error deleting "{cover_filename}": {str(e)}')

    if args.write_json:
        with open(debug_filename, "w", encoding="utf-8") as outfile:
            json.dump(debug_meta, outfile, indent=2)


def add_common_download_arguments(parser_dl):
    """
    Add common arguments needed for downloading

    :param parser_dl:
    :return:
    """
    parser_dl.add_argument(
        "-d",
        "--downloaddir",
        dest="download_dir",
        default=".",
        help="Download folder path",
    )
    parser_dl.add_argument(
        "-c",
        "--chapters",
        dest="add_chapters",
        action="store_true",
        help="Add chapter marks (experimental)",
    )
    parser_dl.add_argument(
        "-m",
        "--merge",
        dest="merge_output",
        action="store_true",
        help="Merge into 1 file (experimental, requires ffmpeg)",
    )
    parser_dl.add_argument(
        "--mergeformat",
        dest="merge_format",
        choices=["mp3", "m4b"],
        default="mp3",
        help="Merged file format (m4b is slow, experimental, requires ffmpeg)",
    )
    parser_dl.add_argument(
        "-k",
        "--keepcover",
        dest="always_keep_cover",
        action="store_true",
        help="Always generate the cover image file (cover.jpg)",
    )
    parser_dl.add_argument(
        "-f",
        "--keepmp3",
        dest="keep_mp3",
        action="store_true",
        help="Keep downloaded mp3 files (after merging)",
    )
    parser_dl.add_argument(
        "--nobookfolder",
        dest="no_book_folder",
        action="store_true",
        help="Don't create a book subfolder",
    )
    parser_dl.add_argument(
        "-j",
        "--writejson",
        dest="write_json",
        action="store_true",
        help="Generate a meta json file (for debugging)",
    )
    parser_dl.add_argument(
        "-r",
        "--retry",
        dest="retries",
        type=int,
        default=1,
        help="Number of retries if download fails. Default 1.",
    )
    parser_dl.add_argument(
        "--hideprogress",
        dest="hide_progress",
        action="store_true",
        help="Hide the download progress bar (e.g. during testing)",
    )


def run():
    parser = argparse.ArgumentParser(
        prog="odmpy",
        description="Download/return an Overdrive loan audiobook",
        epilog=(
            f"Version {__version__}. "
            f"[Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}-{sys.platform}] "
            "Source at https://github.com/ping/odmpy/"
        ),
        fromfile_prefix_chars="@",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="store_true",
        help="Enable more verbose messages for debugging",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        dest="timeout",
        type=int,
        default=10,
        help="Timeout (seconds) for network requests. Default 10.",
    )

    subparsers = parser.add_subparsers(
        title="Available commands",
        dest="command_name",
        help="To get more help, use the -h option with the command.",
    )
    parser_info = subparsers.add_parser(
        "info",
        description="Get information about a loan file.",
        help="Get information about a loan file",
    )
    parser_info.add_argument(
        "-f",
        "--format",
        dest="format",
        choices=["text", "json"],
        default="text",
        help="Format for output",
    )
    parser_info.add_argument("odm_file", type=str, help="ODM file path")

    parser_dl = subparsers.add_parser(
        "dl", description="Download from a loan file.", help="Download from a loan file"
    )
    add_common_download_arguments(parser_dl)
    parser_dl.add_argument("odm_file", type=str, help="ODM file path")

    parser_ret = subparsers.add_parser(
        "ret", description="Return a loan file.", help="Return a loan file."
    )
    parser_ret.add_argument("odm_file", type=str, help="ODM file path")

    parser_libby = subparsers.add_parser(
        "libby",
        description="Interactive Libby Interface",
        help="Interact directly with Libby to download audiobooks",
    )
    parser_libby.add_argument(
        "--settings",
        dest="settings_folder",
        type=str,
        default="./odmpy_settings",
        metavar="SETTINGS_FOLDER",
        help="Settings folder to store odmpy required settings, e.g. Libby authentication.",
    )
    parser_libby.add_argument(
        "--keepodm",
        action="store_true",
        help="Keep the downloaded odm and license files.",
    )
    add_common_download_arguments(parser_libby)

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # suppress warnings
    logging.getLogger("eyed3").setLevel(
        logging.WARNING if logger.level == logging.DEBUG else logging.ERROR
    )

    if args.command_name == "libby":
        client_title = "Libby Interactive Client"
        logger.info(client_title)
        logger.info("-" * 70)
        libby_client = LibbyClient(
            args.settings_folder, timeout=args.timeout, logger=logger
        )
        if not libby_client.has_sync_code():
            instructions = (
                "A Libby setup code is needed to allow odmpy to interact with Libby."
                "\nTo get a Libby code, see https://help.libbyapp.com/en-us/6070.htm"
            )
            sync_code = input(f"{instructions}\n\nLibby code (8-digit): ").strip()
            if not sync_code:
                return
            if not sync_code.isdigit() and len(sync_code) != 8:
                logger.warning(f"Invalid code: {sync_code}")
                return
            libby_client.get_chip()
            libby_client.clone_by_code(sync_code)
            if not libby_client.is_logged_in():
                libby_client.clear_settings()
                raise RuntimeError(
                    "Could not log in with code.\n"
                    "Make sure that you have entered the right code and within the time limit.\n"
                    "You also need to have at least 1 registered library card."
                )
            logger.info("Login successful.\n")
        audiobook_loans = libby_client.get_audiobook_loans()
        if not audiobook_loans:
            logger.info("No downloadable audiobook loans found.")
            return
        logger.info("Found %s downloadable loans.", colored.blue(len(audiobook_loans)))
        for index, loan in enumerate(audiobook_loans, start=1):
            expiry_date = datetime.datetime.strptime(
                loan["expireDate"], "%Y-%m-%dT%H:%M:%SZ"
            )
            logger.info(
                "%s: %-50s  %-30s  %s",
                colored.magenta(f"{index:2d}", bold=True),
                loan["title"],
                f'By: {loan["firstCreatorSortName"]}',
                f"Exp: {expiry_date:%Y-%m-%d}",
            )
        while True:
            loan_index_selected = input(
                f"\nChoose from {colored.magenta(f'1-{len(audiobook_loans)}', bold=True)}, "
                "or leave blank to quit, then press enter: "
            ).strip()
            if not loan_index_selected:
                break
            if (
                (not loan_index_selected.isdigit())
                or int(loan_index_selected) < 1
                or int(loan_index_selected) > len(audiobook_loans)
            ):
                logger.warning(f"Invalid choice: {loan_index_selected}")
                continue
            break

        if loan_index_selected:
            loan_index_selected = int(loan_index_selected)
            selected_loan = audiobook_loans[loan_index_selected - 1]
            file_name = f'{selected_loan["title"]} {selected_loan["id"]}'
            odm_file_path = os.path.join(
                args.download_dir,
                f"{slugify(file_name, allow_unicode=True)}.odm",
            )
            odm_res_content = libby_client.fulfill_odm(
                selected_loan["id"], selected_loan["cardId"], "audiobook-mp3"
            )
            with open(odm_file_path, "wb") as f:
                f.write(odm_res_content)
                logger.info("Downloaded odm to %s", colored.magenta(odm_file_path))
            process_odm(odm_file_path, args, cleanup_odm_license=not args.keepodm)

        return  # end libby command

    # because py<=3.6 does not support `add_subparsers(required=True)`
    try:
        # test for odm file
        args.odm_file
    except AttributeError:
        parser.print_help()
        sys.exit()

    xml_doc = xml.etree.ElementTree.parse(args.odm_file)
    root = xml_doc.getroot()

    # Return Book
    if args.command_name == "ret":
        logger.info(f"Returning {args.odm_file} ...")
        early_return_url = root.find("EarlyReturnURL").text
        try:
            early_return_res = requests.get(
                early_return_url, headers={"User-Agent": UA_LONG}, timeout=10
            )
            early_return_res.raise_for_status()
            logger.info(f"Loan returned successfully: {args.odm_file}")
        except HTTPError as he:
            if he.response.status_code == 403:
                logger.warning("Loan is probably already returned.")
                sys.exit()
            logger.error(
                f"Unexpected HTTPError while trying to return loan {args.odm_file}"
            )
            logger.error(f"HTTPError: {str(he)}")
            logger.debug(he.response.content)
            sys.exit(1)
        except ConnectionError as ce:
            logger.error(f"ConnectionError: {str(ce)}")
            sys.exit(1)

        sys.exit()

    process_odm(args.odm_file, args)

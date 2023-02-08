# Copyright (C) 2023 github.com/ping
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
import logging
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List, Tuple
from urllib.parse import urlparse

import eyed3  # type: ignore[import]
import requests
from eyed3.utils import art  # type: ignore[import]
from termcolor import colored

from .constants import PERFORMER_FID, LANGUAGE_FID
from .libby import USER_AGENT
from .utils import slugify


def generate_names(title: str, authors: List[str], args) -> Tuple[str, str, str]:
    """
    Creates the download folder if necessary and generates the merged book names

    :param title:
    :param authors:
    :param args:
    :return:
    """

    # declare book folder/file names here together, so that we can catch problems from too long names
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
    return book_folder, book_filename, book_m4b_filename


def write_tags(
    audiofile,
    title: str,
    sub_title: Optional[str],
    authors: List[str],
    narrators: Optional[List[str]],
    publisher: str,
    description: str,
    cover_bytes: Optional[bytes],
    genres: Optional[List[str]],
    languages: Optional[List[str]],
    published_date: Optional[str],
    part_number: int,
    total_parts: int,
    overdrive_id: str,
    overwrite_title: bool = False,
    always_overwrite: bool = False,
    delimiter: str = ";",
) -> None:
    """
    Write out ID3 tags to the audiofile

    :param audiofile:
    :param title:
    :param sub_title:
    :param authors:
    :param narrators:
    :param publisher:
    :param description:
    :param cover_bytes:
    :param genres:
    :param languages:
    :param published_date:
    :param part_number:
    :param total_parts:
    :param overdrive_id:
    :param overwrite_title:
    :param always_overwrite:
    :param delimiter:
    :return:
    """
    if not delimiter:
        delimiter = ";"

    if not audiofile.tag:
        audiofile.initTag()
    if always_overwrite or overwrite_title or not audiofile.tag.title:
        audiofile.tag.title = str(title)
    if sub_title and (
        always_overwrite
        or not audiofile.tag.getTextFrame(eyed3.id3.frames.SUBTITLE_FID)
    ):
        audiofile.tag.setTextFrame(eyed3.id3.frames.SUBTITLE_FID, sub_title)
    if always_overwrite or not audiofile.tag.album:
        audiofile.tag.album = str(title)
    if authors and (always_overwrite or not audiofile.tag.artist):
        audiofile.tag.artist = delimiter.join([str(a) for a in authors])
    if authors and (always_overwrite or not audiofile.tag.album_artist):
        audiofile.tag.album_artist = delimiter.join([str(a) for a in authors])
    if part_number and (always_overwrite or not audiofile.tag.track_num):
        audiofile.tag.track_num = (part_number, total_parts)
    if narrators and (
        always_overwrite or not audiofile.tag.getTextFrame(PERFORMER_FID)
    ):
        audiofile.tag.setTextFrame(
            PERFORMER_FID, delimiter.join([str(n) for n in narrators])
        )
    if publisher and (always_overwrite or not audiofile.tag.publisher):
        audiofile.tag.publisher = str(publisher)
    if description and (
        always_overwrite or eyed3.id3.frames.COMMENT_FID not in audiofile.tag.frame_set
    ):
        audiofile.tag.comments.set(str(description), description="Description")
    if genres and (always_overwrite or not audiofile.tag.genre):
        audiofile.tag.genre = delimiter.join(genres)
    if languages and (always_overwrite or not audiofile.tag.getTextFrame(LANGUAGE_FID)):
        audiofile.tag.setTextFrame(
            LANGUAGE_FID, delimiter.join([str(lang) for lang in languages])
        )
    if published_date and (always_overwrite or not audiofile.tag.release_date):
        audiofile.tag.release_date = published_date
    if cover_bytes:
        audiofile.tag.images.set(
            art.TO_ID3_ART_TYPES[art.FRONT_COVER][0],
            cover_bytes,
            "image/jpeg",
            description="Cover",
        )
    # Output some OD identifiers in the mp3
    if overdrive_id:
        audiofile.tag.user_text_frames.set(
            overdrive_id,
            "OverDrive Media ID" if overdrive_id.isdigit() else "OverDrive Reserve ID",
        )


def generate_cover(
    book_folder: str,
    cover_url: Optional[str],
    session: requests.Session,
    timeout: int,
    logger: logging.Logger,
) -> Tuple[str, Optional[bytes]]:
    """
    Get the book cover

    :param book_folder:
    :param cover_url:
    :param session:
    :param timeout:
    :param logger:
    :return:
    """
    cover_filename = os.path.join(book_folder, "cover.jpg")
    if not os.path.isfile(cover_filename) and cover_url:
        try:
            square_cover_url_params = {
                "type": "auto",
                "width": str(510),
                "height": str(510),
                "force": "true",
                "quality": str(80),
                "url": urlparse(cover_url).path,
            }
            # credit: https://github.com/lullius/pylibby/pull/18
            # this endpoint produces a resized version of the cover
            cover_res = session.get(
                "https://ic.od-cdn.com/resize",
                params=square_cover_url_params,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            )
            cover_res.raise_for_status()
            with open(cover_filename, "wb") as outfile:
                outfile.write(cover_res.content)
        except requests.exceptions.HTTPError as he:
            logger.warning(
                "Error downloading square cover: %s",
                colored(str(he), "red", attrs=["bold"]),
            )
            # fallback to original cover url
            try:
                cover_res = session.get(
                    cover_url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=timeout,
                )
                cover_res.raise_for_status()
                with open(cover_filename, "wb") as outfile:
                    outfile.write(cover_res.content)
            except requests.exceptions.HTTPError as he2:
                logger.warning(
                    "Error downloading cover: %s",
                    colored(str(he2), "red", attrs=["bold"]),
                )

    cover_bytes: Optional[bytes] = None
    if os.path.isfile(cover_filename):
        with open(cover_filename, "rb") as f:
            cover_bytes = f.read()

    return cover_filename, cover_bytes


def merge_into_mp3(
    book_filename: str,
    file_tracks: List[Dict],
    audio_bitrate: int,
    ffmpeg_loglevel: str,
    hide_progress: bool,
    logger: logging.Logger,
) -> None:
    """
    Merge the files into a single mp3

    :param book_filename: mp3 file name
    :param file_tracks:
    :param audio_bitrate:
    :param ffmpeg_loglevel:
    :param hide_progress:
    :param logger:
    :return:
    """

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
    if not hide_progress:
        cmd.append("-stats")
    cmd.extend(
        [
            "-i",
            f"concat:{'|'.join([ft['file'] for ft in file_tracks])}",
            "-acodec",
            "copy",
            "-b:a",
            f"{audio_bitrate}k"
            if audio_bitrate
            else "64k",  # explicitly set audio bitrate
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


def convert_to_m4b(
    book_filename: str,
    book_m4b_filename: str,
    cover_filename: str,
    audio_bitrate: int,
    ffmpeg_loglevel: str,
    hide_progress: str,
    logger: logging.Logger,
) -> None:
    """
    Converts the merged mp3 into a m4b

    :param book_filename: mp3 file name
    :param book_m4b_filename:
    :param cover_filename:
    :param audio_bitrate:
    :param ffmpeg_loglevel:
    :param hide_progress:
    :param logger:
    :return:
    """
    temp_book_m4b_filename = f"{book_m4b_filename}.part"
    cmd = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        ffmpeg_loglevel,
    ]
    if not hide_progress:
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
            f"{audio_bitrate}k"
            if audio_bitrate
            else "64k",  # explicitly set audio bitrate
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
    logger.info('Merged files into "%s"', colored(book_m4b_filename, "magenta"))
    try:
        os.remove(book_filename)
    except Exception as e:  # pylint: disable=broad-except
        logger.warning(f'Error deleting "{book_filename}": {str(e)}')


def remux_mp3(
    part_tmp_filename: str,
    part_filename: str,
    ffmpeg_loglevel: str,
    logger: logging.Logger,
) -> None:
    """
    Try to remux file to remove mp3 lame tag errors

    :param part_tmp_filename:
    :param part_filename:
    :param ffmpeg_loglevel:
    :param logger:
    :return:
    """
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


def set_ele_attributes(ele: ET.Element, attributes: Dict) -> None:
    """
    Set multiple attributes on an Element

    :param ele: Element
    :param attributes:
    :return:
    """
    for k, v in attributes.items():
        ele.set(k, v)


def create_opf(
    media_info: Dict,
    cover_filename: Optional[str],
    file_tracks: List[Dict],
    opf_file_path: str,
    logger: logging.Logger,
) -> None:
    """

    :param media_info:
    :param cover_filename:
    :param file_tracks:
    :param opf_file_path:
    :param logger:
    :return:
    """
    ET.register_namespace("opf", "http://www.idpf.org/2007/opf")
    ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")
    package = ET.Element("package")
    set_ele_attributes(
        package,
        {
            "version": "2.0",
            "xmlns": "http://www.idpf.org/2007/opf",
            "unique-identifier": "BookId",
        },
    )
    metadata = ET.SubElement(package, "metadata")
    set_ele_attributes(
        metadata,
        {
            "xmlns:dc": "http://purl.org/dc/elements/1.1/",
            "xmlns:opf": "http://www.idpf.org/2007/opf",
        },
    )
    title = ET.SubElement(metadata, "dc:title")
    title.text = media_info["title"]
    if media_info.get("subtitle"):
        ET.SubElement(metadata, "dc:subtitle").text = media_info["subtitle"]
    ET.SubElement(metadata, "dc:language").text = media_info["languages"][0]["id"]
    identifier = ET.SubElement(metadata, "dc:identifier")
    identifier.set("id", "BookId")
    isbn = next(
        iter(
            [
                f["identifiers"][0]["value"]
                for f in media_info["formats"]
                if f["id"] == "audiobook-mp3"
                and [i for i in f["identifiers"] if i["type"] == "ISBN"]
            ]
        ),
        None,
    )
    if isbn:
        identifier.set("opf:scheme", "ISBN")
        identifier.text = isbn
    else:
        identifier.set("opf:scheme", "overdrive")
        identifier.text = media_info["id"]

    # add overdrive id and reserveId
    overdrive_id = ET.SubElement(metadata, "dc:identifier")
    overdrive_id.set("opf:scheme", "OverDriveId")
    overdrive_id.text = media_info["id"]
    overdrive_reserve_id = ET.SubElement(metadata, "dc:identifier")
    overdrive_reserve_id.set("opf:scheme", "OverDriveReserveId")
    overdrive_reserve_id.text = media_info["reserveId"]

    # Roles https://idpf.org/epub/20/spec/OPF_2.0_final_spec.html#Section2.2.6
    for media_role, opf_role in (
        ("Author", "aut"),
        ("Narrator", "nrt"),
        ("Editor", "edt"),
    ):
        creators = [
            c for c in media_info["creators"] if c.get("role", "") == media_role
        ]
        for c in creators:
            creator = ET.SubElement(metadata, "dc:creator")
            creator.set("opf:role", opf_role)
            set_ele_attributes(
                creator,
                {"opf:role": opf_role, "opf:file-as": c["sortName"]},
            )
            creator.text = c["name"]

    if media_info.get("publisher", {}).get("name"):
        ET.SubElement(metadata, "dc:publisher").text = media_info["publisher"]["name"]
    if media_info.get("description"):
        ET.SubElement(metadata, "dc:description").text = media_info["description"]
    for s in media_info.get("subject", []):
        ET.SubElement(metadata, "dc:subject").text = s["name"]
    for k in media_info.get("keywords", []):
        ET.SubElement(metadata, "dc:tag").text = k
    if media_info.get("publishDate"):
        pub_date = ET.SubElement(metadata, "dc:date")
        pub_date.set("opf:event", "publication")
        pub_date.text = media_info["publishDate"]
    if media_info.get("detailedSeries"):
        series_info = media_info["detailedSeries"]
        if series_info.get("seriesName"):
            set_ele_attributes(
                ET.SubElement(metadata, "meta"),
                {"name": "calibre:series", "content": series_info["seriesName"]},
            )
        if series_info.get("readingOrder"):
            set_ele_attributes(
                ET.SubElement(metadata, "meta"),
                {
                    "name": "calibre:series_index",
                    "content": series_info["readingOrder"],
                },
            )

    manifest = ET.SubElement(package, "manifest")
    if cover_filename:
        set_ele_attributes(
            ET.SubElement(manifest, "item"),
            {
                "id": "cover",
                "href": os.path.basename(cover_filename),
                "media-type": "image/jpeg",
            },
        )
    spine = ET.SubElement(package, "spine")
    for f in file_tracks:
        file_name, _ = os.path.splitext(os.path.basename(f["file"]))
        file_id = slugify(file_name)
        set_ele_attributes(
            ET.SubElement(manifest, "item"),
            {
                "id": file_id,
                "href": os.path.basename(f["file"]),
                "media-type": "audio/mpeg",
            },
        )
        set_ele_attributes(ET.SubElement(spine, "itemref"), {"idref": file_id})

    tree = ET.ElementTree(package)
    tree.write(opf_file_path, xml_declaration=True, encoding="utf-8")
    logger.info('Saved "%s"', colored(opf_file_path, "magenta"))

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

import argparse
import datetime
import logging
import subprocess
import xml.etree.ElementTree as ET
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Tuple, NamedTuple
from urllib.parse import urlparse

import requests
from mutagen.id3 import (
    ID3,
    TIT2,
    TIT3,
    TALB,
    TPE1,
    TPE2,
    TRCK,
    TPUB,
    COMM,
    APIC,
    TPE3,
    TLAN,
    TDRL,
    TXXX,
    TCON,
    PictureType,
    Encoding,
)
from mutagen.mp3 import MP3
from requests.adapters import HTTPAdapter, Retry
from termcolor import colored
from iso639 import Lang  # type: ignore[import]

from ..errors import OdmpyRuntimeError
from ..libby import USER_AGENT, LibbyFormats
from ..utils import slugify, sanitize_path, is_windows, escape_text_for_ffmpeg


#
# Shared functions across processing for diff loan types
#


def init_session(max_retries: int = 0) -> requests.Session:
    session = requests.Session()
    custom_adapter = HTTPAdapter(
        max_retries=Retry(total=max_retries, backoff_factor=0.1)
    )
    for prefix in ("http://", "https://"):
        session.mount(prefix, custom_adapter)
    return session


def generate_names(
    title: str,
    series: str,
    authors: List[str],
    edition: str,
    title_id: str,
    args: argparse.Namespace,
    logger: logging.Logger,
) -> Tuple[Path, Path]:
    """
    Creates the download folder if necessary and generates the merged book names

    :param title:
    :param authors:
    :param edition:
    :param title_id:
    :param series:
    :param args:
    :param logger:
    :return:
    """
    book_folder_name = args.book_folder_format % {
        "Title": sanitize_path(title),
        "Author": sanitize_path(", ".join(authors)),
        "Series": sanitize_path(series or ""),
        "Edition": sanitize_path(edition),
        "ID": sanitize_path(title_id),
    }
    # unlike book_folder_name, we sanitize the entire book file format
    # because it is expected to be a single name and `os.sep` will be
    # stripped
    book_file_format = sanitize_path(
        args.book_file_format
        % {
            "Title": title,
            "Author": ", ".join(authors),
            "Series": series or "",
            "Edition": edition,
            "ID": sanitize_path(title_id),
        }
    )
    # declare book folder/file names here together, so that we can catch problems from too long names
    book_folder = Path(args.download_dir, book_folder_name)
    if args.no_book_folder:
        book_folder = Path(args.download_dir)

    # for merged mp3
    book_filename = book_folder.joinpath(f"{book_file_format}.mp3")

    try:
        if not book_folder.exists():
            book_folder.mkdir(parents=True, exist_ok=True)
    except OSError as os_err:
        # ref http://www.ioplex.com/~miallen/errcmpp.html
        # for Windows: OSError: [WinError 123] The filename, directory name, or volume label syntax is incorrect
        if (is_windows() and os_err.errno != 22) or (
            os_err.errno not in (36, 63) and not is_windows()
        ):
            raise

        # Ref OSError: [Errno 36] File name too long https://github.com/ping/odmpy/issues/5
        # create book folder with just the title and first author
        book_folder_name = args.book_folder_format % {
            "Title": sanitize_path(title),
            "Author": sanitize_path(authors[0]) if authors else "",
            "Series": sanitize_path(series or ""),
            "ID": sanitize_path(title_id),
        }
        book_folder = Path(args.download_dir, book_folder_name)
        if args.no_book_folder:
            book_folder = Path(args.download_dir)

        logger.warning(
            f'Book folder name is too long. Files will be saved in "{book_folder}" instead.'
        )
        if not book_folder.exists():
            book_folder.mkdir(parents=True, exist_ok=True)

        # also create book name with just one author
        book_file_format = sanitize_path(
            args.book_file_format
            % {
                "Title": title,
                "Author": authors[0] if authors else "",
                "Series": series or "",
                "Edition": edition,
                "ID": sanitize_path(title_id),
            }
        )
        book_filename = book_folder.joinpath(f"{book_file_format}.mp3")
    return book_folder, book_filename


class Tag(str, Enum):
    """
    Helper string enum for tag frames names
    """

    Title = "TIT2"
    SubTitle = "TIT3"
    Album = "TALB"
    Artist = "TPE1"
    AlbumArtist = "TPE2"
    TrackNumber = "TRCK"
    Publisher = "TPUB"
    Comment = "COMM"
    Genre = "TCON"
    Conductor = "TPE3"
    Language = "TLAN"
    ReleaseDate = "TDRL"
    TableOfContents = "CTOC"
    Chapter = "CHAP"

    def __str__(self):
        return str(self.value)


def write_tags(
    audiofile: MP3,
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
    series: Optional[str],
    part_number: int,
    total_parts: int,
    overdrive_id: str,
    isbn: Optional[str] = None,
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
    :param series:
    :param part_number:
    :param total_parts:
    :param overdrive_id:
    :param isbn:
    :param overwrite_title:
    :param always_overwrite:
    :param delimiter:
    :return:
    """
    if not delimiter:
        delimiter = ";"

    if not audiofile.tags:
        audiofile.tags = ID3()

    if always_overwrite or overwrite_title or Tag.Title not in audiofile.tags:
        audiofile.tags.add(TIT2(encoding=Encoding.UTF8, text=title))
    if sub_title and (always_overwrite or Tag.SubTitle not in audiofile.tags):
        audiofile.tags.add(TIT3(encoding=Encoding.UTF8, text=sub_title))

    if always_overwrite or Tag.Album not in audiofile.tags:
        audiofile.tags.add(TALB(encoding=Encoding.UTF8, text=title))

    if authors and (always_overwrite or Tag.Artist not in audiofile.tags):
        audiofile.tags.add(TPE1(encoding=Encoding.UTF8, text=delimiter.join(authors)))
    if authors and (always_overwrite or Tag.AlbumArtist not in audiofile.tags):
        audiofile.tags.add(TPE2(encoding=Encoding.UTF8, text=delimiter.join(authors)))
    if part_number and (always_overwrite or Tag.TrackNumber not in audiofile.tags):
        audiofile.tags.add(
            TRCK(
                encoding=Encoding.UTF8,
                text="{:02d}/{:02d}".format(part_number, total_parts),
            )
        )
    if narrators and (always_overwrite or Tag.Conductor not in audiofile):
        audiofile.tags.add(TPE3(encoding=Encoding.UTF8, text=delimiter.join(narrators)))
    if publisher and (always_overwrite or Tag.Publisher not in audiofile.tags):
        audiofile.tags.add(TPUB(encoding=Encoding.UTF8, text=publisher))
    if description and (always_overwrite or Tag.Comment not in audiofile.tags):
        audiofile.tags.add(
            COMM(encoding=Encoding.UTF8, desc="Description", text=description)
        )
    if genres and (always_overwrite or Tag.Genre not in audiofile.tags):
        audiofile.tags.add(TCON(encoding=Encoding.UTF8, text=delimiter.join(genres)))
    if languages and (always_overwrite or Tag.Language not in audiofile):
        try:
            tag_langs = [Lang(lang).pt2b for lang in languages]
        except:  # noqa, pylint: disable=bare-except
            tag_langs = languages
        audiofile.tags.add(TLAN(encoding=Encoding.UTF8, text=delimiter.join(tag_langs)))
    if published_date and (always_overwrite or Tag.ReleaseDate not in audiofile):
        audiofile.tags.add(TDRL(encoding=Encoding.UTF8, text=published_date))
    if cover_bytes:
        audiofile.tags.add(
            APIC(
                encoding=Encoding.UTF8,
                mime="image/jpeg",
                type=PictureType.COVER_FRONT,
                desc="Cover",
                data=cover_bytes,
            )
        )
    if series:
        audiofile.tags.add(TXXX(encoding=3, desc="Series", text=series))
    # Output some OD identifiers in the mp3
    if overdrive_id:
        audiofile.tags.add(
            TXXX(
                encoding=Encoding.UTF8,
                desc="OverDrive Media ID"
                if overdrive_id.isdigit()
                else "OverDrive Reserve ID",
                text=overdrive_id,
            )
        )
    if isbn:
        audiofile.tags.add(TXXX(encoding=Encoding.UTF8, desc="ISBN", text=isbn))


def get_best_cover_url(loan: Dict) -> Optional[str]:
    covers: List[Dict] = sorted(
        list(loan.get("covers", []).values()),
        key=lambda c: c.get("width", 0),
        reverse=True,
    )
    cover_highest_res: Optional[Dict] = next(iter(covers), None)
    return cover_highest_res["href"] if cover_highest_res else None


def generate_cover(
    book_folder: Path,
    cover_url: Optional[str],
    session: requests.Session,
    timeout: int,
    logger: logging.Logger,
    force_square: bool = True,
) -> Tuple[Path, Optional[bytes]]:
    """
    Get the book cover

    :param book_folder:
    :param cover_url:
    :param session:
    :param timeout:
    :param logger:
    :param force_square:
    :return:
    """
    cover_filename = book_folder.joinpath("cover.jpg")
    if not cover_filename.exists() and cover_url:
        try:
            if force_square:
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
            else:
                cover_res = session.get(
                    cover_url, headers={"User-Agent": USER_AGENT}, timeout=timeout
                )
            cover_res.raise_for_status()
            with cover_filename.open("wb") as outfile:
                outfile.write(cover_res.content)
        except requests.exceptions.HTTPError as he:
            if not force_square:
                logger.warning(
                    "Error downloading cover: %s",
                    colored(str(he), "red", attrs=["bold"]),
                )
            else:
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
                    with cover_filename.open("wb") as outfile:
                        outfile.write(cover_res.content)
                except requests.exceptions.HTTPError as he2:
                    logger.warning(
                        "Error downloading cover: %s",
                        colored(str(he2), "red", attrs=["bold"]),
                    )

    cover_bytes: Optional[bytes] = None
    if cover_filename.exists():
        with cover_filename.open("rb") as f:
            cover_bytes = f.read()

    return cover_filename, cover_bytes


def merge_into_mp3(
    book_filename: Path,
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

    # We won't directly generate a m4b here even if specified because mutagen support for m4b/mp4
    # is not as good as mp3
    temp_book_filename = book_filename.with_suffix(".part")
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
            f"concat:{'|'.join([str(ft['file']) for ft in file_tracks])}",
            "-acodec",
            "copy",
            "-b:a",
            f"{audio_bitrate}k"
            if audio_bitrate
            else "64k",  # explicitly set audio bitrate
            "-f",
            "mp3",
            str(temp_book_filename),
        ]
    )
    exit_code = subprocess.call(cmd)
    if exit_code:
        logger.error(f"ffmpeg exited with the code: {exit_code!s}")
        logger.error(f"Command: {' '.join(cmd)!s}")
        raise OdmpyRuntimeError("ffmpeg exited with a non-zero code")

    temp_book_filename.replace(book_filename)


def convert_to_m4b(
    book_filename: Path,
    book_m4b_filename: Path,
    cover_filename: Path,
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
    temp_book_m4b_filename = book_m4b_filename.with_suffix(".part")
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
            str(book_filename),
        ]
    )
    if cover_filename.exists():
        cmd.extend(["-i", str(cover_filename)])

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
    if cover_filename.exists():
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

    cmd.extend(["-f", "mp4", str(temp_book_m4b_filename)])
    exit_code = subprocess.call(cmd)
    if exit_code:
        logger.error(f"ffmpeg exited with the code: {exit_code!s}")
        logger.error(f"Command: {' '.join(cmd)!s}")
        raise OdmpyRuntimeError("ffmpeg exited with a non-zero code")

    temp_book_m4b_filename.rename(book_m4b_filename)
    logger.info('Merged files into "%s"', colored(str(book_m4b_filename), "magenta"))
    try:
        book_filename.unlink()
    except Exception as e:  # pylint: disable=broad-except
        logger.warning(f'Error deleting "{book_filename}": {str(e)}')


class FfmpegChapterMarker(NamedTuple):
    title: str
    start_millisecond: int
    end_millisecond: int


def update_chapters(
    target_filepath: Path,
    chapters: List[FfmpegChapterMarker],
    output_format: str,
    ffmpeg_loglevel: str,
    logger: logging.Logger,
) -> None:
    """
    Workaround for https://github.com/quodlibet/mutagen/issues/506

    :param target_filepath:
    :param chapters:
    :param output_format:
    :param ffmpeg_loglevel:
    :param logger:
    :return:
    """

    # We have to export ffmpegmeta first because
    # ffmpeg metadata updates overwrites everything

    ffmeta_filepath = target_filepath.with_suffix(".ffmeta.txt")
    # generate current ffmetadata file first
    cmd = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        ffmpeg_loglevel,
        "-i",
        str(target_filepath),
        "-f",
        "ffmetadata",
        str(ffmeta_filepath),
    ]
    try:
        exit_code = subprocess.call(cmd)
        if exit_code:
            logger.warning(f"ffmpeg exited with the code: {exit_code!s}")
            logger.warning(f"Command: {' '.join(cmd)!s}")
            if ffmeta_filepath.exists():
                ffmeta_filepath.unlink()
            return
    except Exception as ffmpeg_ex:  # pylint: disable=broad-except
        logger.warning(f"Error executing ffmpeg: {str(ffmpeg_ex)}")
        if ffmeta_filepath.exists():
            ffmeta_filepath.unlink()
        return

    with ffmeta_filepath.open("a", encoding="utf-8") as f:
        for chapter in chapters:
            f.write("[CHAPTER]\n")
            f.write("TIMEBASE=1/1000\n")
            f.write(f"START={chapter.start_millisecond}\n")
            f.write(f"END={chapter.end_millisecond}\n")
            f.write(f"title={escape_text_for_ffmpeg(chapter.title)}\n")
        f.write("\n")

    target_tmp_filepath = target_filepath.with_suffix(".tmp")
    cmd = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        ffmpeg_loglevel,
        "-i",
        str(target_filepath),
        "-i",
        str(ffmeta_filepath),
        "-map_metadata",
        "1",
        "-c",
        "copy",
        "-f",
        output_format,
        str(target_tmp_filepath),
    ]
    try:
        logger.info(f"Command: {' '.join(cmd)!s}")
        exit_code = subprocess.call(cmd)
        if exit_code:
            logger.warning(f"ffmpeg exited with the code: {exit_code!s}")
            logger.warning(f"Command: {' '.join(cmd)!s}")
            if target_tmp_filepath.exists():
                target_tmp_filepath.unlink()
        else:
            try:
                target_tmp_filepath.rename(target_filepath)
            except FileExistsError:
                # For Windows
                target_filepath.unlink()
                target_tmp_filepath.rename(target_filepath)
        if ffmeta_filepath.exists():
            ffmeta_filepath.unlink()
    except Exception as ffmpeg_ex:  # pylint: disable=broad-except
        logger.warning(f"Error executing ffmpeg: {str(ffmpeg_ex)}")
        if ffmeta_filepath.exists():
            ffmeta_filepath.unlink()
        if target_tmp_filepath.exists():
            target_tmp_filepath.unlink()


def remux_mp3(
    part_tmp_filename: Path,
    part_filename: Path,
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
        str(part_tmp_filename),
        "-c:a",
        "copy",
        "-c:v",
        "copy",
        str(part_filename),
    ]
    try:
        exit_code = subprocess.call(cmd)
        if exit_code:
            logger.warning(f"ffmpeg exited with the code: {exit_code!s}")
            logger.warning(f"Command: {' '.join(cmd)!s}")
            part_tmp_filename.rename(part_filename)
        else:
            part_tmp_filename.unlink()
    except Exception as ffmpeg_ex:  # pylint: disable=broad-except
        logger.warning(f"Error executing ffmpeg: {str(ffmpeg_ex)}")
        part_tmp_filename.rename(part_filename)


def extract_authors_from_openbook(openbook: Dict) -> List[str]:
    """
    Extract list of author names from openbook

    :param openbook:
    :return:
    """
    creators = openbook.get("creator", [])
    return (
        [c["name"] for c in creators if c.get("role", "") == "author"]
        or [c["name"] for c in creators if c.get("role", "") == "editor"]
        or [c["name"] for c in creators]
    )


def extract_asin(formats: List[Dict]) -> str:
    """
    Extract Amazon's ASIN from media_info["formats"]

    :param formats:
    :return:
    """
    for media_format in [
        f
        for f in formats
        if [i for i in f.get("identifiers", []) if i["type"] == "ASIN"]
    ]:
        asin = next(
            iter(
                [
                    identifier["value"]
                    for identifier in media_format.get("identifiers", [])
                    if identifier["type"] == "ASIN"
                ]
            ),
            "",
        )
        if asin:
            return asin
    return ""


def extract_isbn(formats: List[Dict], format_types: List[str]) -> str:
    """
    Extract ISBN from media_info["formats"]

    :param formats:
    :param format_types:
    :return:
    """
    # a format can contain 2 different "ISBN"s.. one type "ISBN", and another "LibraryISBN"
    # in format["identifiers"]
    # format["isbn"] reflects the "LibraryISBN" value

    isbn = next(
        iter([f["isbn"] for f in formats if f["id"] in format_types and f.get("isbn")]),
        "",
    )
    if isbn:
        return isbn

    for isbn_type in ("LibraryISBN", "ISBN"):
        for media_format in [
            f
            for f in formats
            if f["id"] in format_types
            and [i for i in f.get("identifiers", []) if i["type"] == isbn_type]
        ]:
            isbn = next(
                iter(
                    [
                        identifier["value"]
                        for identifier in media_format.get("identifiers", [])
                        if identifier["type"] == isbn_type
                    ]
                ),
                "",
            )
            if isbn:
                return isbn

    return ""


def build_opf_package(
    media_info: Dict, version: str = "2.0", loan_format: str = LibbyFormats.AudioBookMP3
) -> ET.Element:
    """
    Build the package element from media_info.

    :param media_info:
    :param version:
    :param loan_format:
    :return:
    """

    # References:
    # Version 2: https://idpf.org/epub/20/spec/OPF_2.0_final_spec.html#Section2.0
    # Version 3: https://www.w3.org/TR/epub-33/#sec-package-doc
    direct_epub_formats = [LibbyFormats.EBookOverdrive, LibbyFormats.MagazineOverDrive]
    ET.register_namespace("opf", "http://www.idpf.org/2007/opf")
    ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")
    package = ET.Element(
        "package",
        attrib={
            "version": version,
            "xmlns": "http://www.idpf.org/2007/opf",
            "unique-identifier": "publication-id",
        },
    )
    metadata = ET.SubElement(
        package,
        "metadata",
        attrib={
            "xmlns:dc": "http://purl.org/dc/elements/1.1/",
            "xmlns:opf": "http://www.idpf.org/2007/opf",
        },
    )
    title = ET.SubElement(metadata, "dc:title")
    title.text = media_info["title"]
    if loan_format == LibbyFormats.MagazineOverDrive and media_info.get("edition"):
        # for magazines, put the edition into the title to ensure some uniqueness
        title.text = f'{media_info["title"]} - {media_info["edition"]}'

    if version == "3.0":
        title.set("id", "main-title")
        meta_main_title = ET.SubElement(
            metadata,
            "meta",
            attrib={"refines": "#main-title", "property": "title-type"},
        )
        meta_main_title.text = "main"

    if (
        version == "2.0"
        and loan_format not in direct_epub_formats
        and media_info.get("subtitle")
    ):
        ET.SubElement(metadata, "dc:subtitle").text = media_info["subtitle"]
    if version == "3.0" and media_info.get("subtitle"):
        sub_title = ET.SubElement(metadata, "dc:title")
        sub_title.text = media_info["subtitle"]
        sub_title.set("id", "sub-title")
        meta_sub_title = ET.SubElement(
            metadata, "meta", attrib={"refines": "#sub-title", "property": "title-type"}
        )
        meta_sub_title.text = "subtitle"

    if version == "3.0" and media_info.get("edition"):
        sub_title = ET.SubElement(metadata, "dc:title")
        sub_title.text = media_info["edition"]
        sub_title.set("id", "edition")
        media_edition = ET.SubElement(
            metadata, "meta", attrib={"refines": "#edition", "property": "title-type"}
        )
        media_edition.text = "edition"

    ET.SubElement(metadata, "dc:language").text = media_info["languages"][0]["id"]
    identifier = ET.SubElement(metadata, "dc:identifier")
    identifier.set("id", "publication-id")

    isbn = extract_isbn(media_info["formats"], format_types=[loan_format])
    if isbn:
        identifier.text = isbn
        if version == "2.0":
            identifier.set("opf:scheme", "ISBN")
        if version == "3.0":
            if len(isbn) in (10, 13):
                meta_isbn = ET.SubElement(
                    metadata,
                    "meta",
                    attrib={
                        "refines": "#publication-id",
                        "property": "identifier-type",
                        "scheme": "onix:codelist5",
                    },
                )
                # https://ns.editeur.org/onix/en/5
                meta_isbn.text = "15" if len(isbn) == 13 else "02"
    else:
        identifier.text = media_info["id"]
        if version == "2.0":
            identifier.set("opf:scheme", "overdrive")
        if version == "3.0":
            identifier.text = media_info["id"]

    asin = extract_asin(media_info["formats"])
    if asin:
        asin_tag = ET.SubElement(metadata, "dc:identifier")
        asin_tag.text = asin
        asin_tag.set("id", "asin")
        if version == "2.0":
            asin_tag.set("opf:scheme", "ASIN")
        if version == "3.0":
            asin_tag_meta = ET.SubElement(
                metadata,
                "meta",
                attrib={
                    "refines": "#asin",
                    "property": "identifier-type",
                },
            )
            asin_tag_meta.text = "ASIN"

    # add overdrive id and reserveId
    overdrive_id = ET.SubElement(metadata, "dc:identifier")
    overdrive_id.text = media_info["id"]
    overdrive_id.set("id", "overdrive-id")
    overdrive_reserve_id = ET.SubElement(metadata, "dc:identifier")
    overdrive_reserve_id.text = media_info["reserveId"]
    overdrive_reserve_id.set("id", "overdrive-reserve-id")
    if version == "2.0":
        overdrive_id.set("opf:scheme", "OverDriveId")
        overdrive_reserve_id.set("opf:scheme", "OverDriveReserveId")
    if version == "3.0":
        overdrive_id_meta = ET.SubElement(
            metadata,
            "meta",
            attrib={
                "refines": "#overdrive-id",
                "property": "identifier-type",
            },
        )
        overdrive_id_meta.text = "overdrive-id"

        overdrive_reserve_id_meta = ET.SubElement(
            metadata,
            "meta",
            attrib={
                "refines": "#overdrive-reserve-id",
                "property": "identifier-type",
            },
        )
        overdrive_reserve_id_meta.text = "overdrive-reserve-id"

    # for magazines, no creators are provided, so we'll patch in the publisher
    if media_info.get("publisher", {}).get("name") and not media_info["creators"]:
        media_info["creators"] = [
            {
                "name": media_info["publisher"]["name"],
                "id": media_info["publisher"]["id"],
                "role": "Publisher",
            }
        ]

    # Roles https://idpf.org/epub/20/spec/OPF_2.0_final_spec.html#Section2.2.6
    for media_role, opf_role in (
        ("Author", "aut"),
        ("Narrator", "nrt"),
        ("Editor", "edt"),
        ("Translator", "trl"),
        ("Illustrator", "ill"),
        ("Photographer", "pht"),
        ("Artist", "art"),
        ("Collaborator", "clb"),
        ("Other", "oth"),
        ("Publisher", "pbl"),
    ):
        creators = [
            c for c in media_info["creators"] if c.get("role", "") == media_role
        ]
        for c in creators:
            creator = ET.SubElement(metadata, "dc:creator")
            creator.text = c["name"]
            if version == "2.0":
                creator.set("opf:role", opf_role)
                if c.get("sortName"):
                    creator.set("opf:file-as", c["sortName"])
            if version == "3.0":
                creator.set("id", f'creator_{c["id"]}')
                if c.get("sortName"):
                    meta_file_as = ET.SubElement(
                        metadata,
                        "meta",
                        attrib={
                            "refines": f'#creator_{c["id"]}',
                            "property": "file-as",
                        },
                    )
                    meta_file_as.text = c["sortName"]
                meta_role = ET.SubElement(
                    metadata,
                    "meta",
                    attrib={
                        "refines": f'#creator_{c["id"]}',
                        "property": "role",
                        "scheme": "marc:relators",
                    },
                )
                meta_role.text = opf_role

    if media_info.get("publisher", {}).get("name"):
        ET.SubElement(metadata, "dc:publisher").text = media_info["publisher"]["name"]
    if media_info.get("description"):
        ET.SubElement(metadata, "dc:description").text = media_info["description"]
    for s in media_info.get("subject", []):
        ET.SubElement(metadata, "dc:subject").text = s["name"]

    if version == "2.0" and loan_format not in direct_epub_formats:
        for k in media_info.get("keywords", []):
            ET.SubElement(metadata, "dc:tag").text = k
    if version == "3.0" and media_info.get("bisac"):
        for i, bisac in enumerate(media_info["bisac"], start=1):
            subject = ET.SubElement(metadata, "dc:subject")
            subject.text = bisac["description"]
            subject.set("id", f"subject_{i}")
            meta_subject_authority = ET.SubElement(
                metadata,
                "meta",
                attrib={"refines": f"#subject_{i}", "property": "authority"},
            )
            meta_subject_authority.text = "BISAC"
            meta_subject_term = ET.SubElement(
                metadata,
                "meta",
                attrib={"refines": f"#subject_{i}", "property": "term"},
            )
            meta_subject_term.text = bisac["code"]

    publish_date = media_info.get("publishDate") or media_info.get(
        "estimatedReleaseDate"
    )
    if publish_date:
        pub_date = ET.SubElement(metadata, "dc:date")
        if version == "2.0":
            pub_date.set("opf:event", "publication")
        pub_date.text = publish_date
        if version == "3.0":
            meta_pubdate = ET.SubElement(metadata, "meta")
            meta_pubdate.set("property", "dcterms:modified")
            meta_pubdate.text = publish_date

    if (
        media_info.get("detailedSeries")
        or media_info.get("series")
        or loan_format == LibbyFormats.MagazineOverDrive
    ):
        series_info = media_info.get("detailedSeries", {})
        series_name = (
            series_info.get("seriesName")
            or media_info.get("series")
            or (
                media_info["title"]
                if loan_format == LibbyFormats.MagazineOverDrive
                else None
            )
        )
        if series_name:
            ET.SubElement(
                metadata,
                "meta",
                attrib={"name": "calibre:series", "content": series_name},
            )
            if version == "3.0":
                meta_series = ET.SubElement(
                    metadata,
                    "meta",
                    attrib={"id": "series-name", "property": "belongs-to-collection"},
                )
                meta_series.text = series_name
                meta_series_type = ET.SubElement(
                    metadata,
                    "meta",
                    attrib={"refines": "#series-name", "property": "collection-type"},
                )
                meta_series_type.text = "series"

        reading_order = series_info.get("readingOrder", "")
        if (
            (not reading_order)
            and loan_format == LibbyFormats.MagazineOverDrive
            and media_info.get("estimatedReleaseDate")
        ):
            est_release_date = datetime.datetime.strptime(
                media_info["estimatedReleaseDate"], "%Y-%m-%dT%H:%M:%SZ"
            )
            reading_order = f"{est_release_date:%y%j}"  # use release date to construct a pseudo reading order

        if reading_order:
            ET.SubElement(
                metadata,
                "meta",
                attrib={
                    "name": "calibre:series_index",
                    "content": reading_order,
                },
            )
            if version == "3.0":
                meta_series_pos = ET.SubElement(
                    metadata,
                    "meta",
                    attrib={"refines": "#series-name", "property": "group-position"},
                )
                meta_series_pos.text = reading_order

    return package


def create_opf(
    media_info: Dict,
    cover_filename: Optional[Path],
    file_tracks: List[Dict],
    opf_file_path: Path,
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
    package = build_opf_package(media_info, version="2.0", loan_format="audiobook-mp3")
    manifest = ET.SubElement(package, "manifest")
    if cover_filename:
        ET.SubElement(
            manifest,
            "item",
            attrib={
                "id": "cover",
                "href": cover_filename.name,
                "media-type": "image/jpeg",
            },
        )
    spine = ET.SubElement(package, "spine")
    for f in file_tracks:
        file_id = slugify(f["file"].stem)
        ET.SubElement(
            manifest,
            "item",
            attrib={
                "id": file_id,
                "href": f["file"].name,
                "media-type": "audio/mpeg",
            },
        )
        ET.SubElement(spine, "itemref", attrib={"idref": file_id})

    tree = ET.ElementTree(package)
    tree.write(opf_file_path, xml_declaration=True, encoding="utf-8")
    logger.info('Saved "%s"', colored(str(opf_file_path), "magenta"))

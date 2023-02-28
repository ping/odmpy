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
import json
import logging
import os
import shutil
from typing import Optional, Any, Dict, List
from typing import OrderedDict as OrderedDictType

import eyed3  # type: ignore[import]
import requests
from requests.exceptions import HTTPError, ConnectionError
from termcolor import colored
from tqdm import tqdm

from .shared import (
    generate_names,
    write_tags,
    generate_cover,
    remux_mp3,
    merge_into_mp3,
    convert_to_m4b,
    create_opf,
    get_best_cover_url,
)
from ..libby import (
    USER_AGENT,
    merge_toc,
    PartMeta,
)
from ..overdrive import OverDriveClient
from ..utils import slugify, plural_or_singular_noun as ps


#
# Main processing logic for libby direct audiobook loans
#


def process_audiobook_loan(
    loan: Dict,
    openbook: Dict,
    parsed_toc: OrderedDictType[str, PartMeta],
    session: requests.Session,
    args: argparse.Namespace,
    logger: logging.Logger,
) -> None:
    """
    Download the audiobook loan directly via Libby without the use of
    an odm file

    :param loan:
    :param openbook:
    :param parsed_toc:
    :param session: From `LibbyClient.libby_session` because it contains a needed auth cookie
    :param args:
    :param logger:
    :return:
    """

    ffmpeg_loglevel = "info" if logger.level == logging.DEBUG else "fatal"

    title = loan["title"]
    overdrive_media_id = loan["id"]
    sub_title = loan.get("subtitle", None)
    cover_url = get_best_cover_url(loan)
    authors = [
        c["name"] for c in openbook.get("creator", []) if c.get("role", "") == "author"
    ]
    if not authors:
        authors = [
            c["name"]
            for c in openbook.get("creator", [])
            if c.get("role", "") == "editor"
        ]
    if not authors:
        authors = [c["name"] for c in openbook.get("creator", [])]
    narrators = [
        c["name"]
        for c in openbook.get("creator", [])
        if c.get("role", "") == "narrator"
    ]
    languages: Optional[List[str]] = (
        [str(openbook.get("language"))] if openbook.get("language") else []
    )
    subjects = [subj["name"] for subj in loan.get("subjects", []) if subj.get("name")]
    publish_date = loan.get("publishDate", None)
    publisher = loan.get("publisherAccount", {}).get("name", "") or ""
    series = loan.get("series", "")
    description = (
        openbook.get("description", {}).get("full", "")
        or openbook.get("description", {}).get("short")
        or ""
    )
    debug_meta: Dict[str, Any] = {
        "meta": {
            "title": title,
            "coverUrl": cover_url,
            "authors": authors,
            "publisher": publisher,
            "description": description,
        }
    }

    download_parts: List[PartMeta] = list(parsed_toc.values())  # noqa
    debug_meta["download_parts"] = []
    for p in download_parts:
        chapters = [
            {"title": m.title, "start": m.start_second, "end": m.end_second}
            for m in p["chapters"]
        ]
        debug_meta["download_parts"].append(
            {
                "url": p["url"],
                "audio-duration": p["audio-duration"],
                "file-length": p["file-length"],
                "spine-position": p["spine-position"],
                "chapters": chapters,
            }
        )

    logger.info(
        f'Downloading "{colored(title, "blue", attrs=["bold"])}" '
        f'by "{colored(", ".join(authors), "blue", attrs=["bold"])}" '
        f'in {len(download_parts)} {ps(len(download_parts), "part")}...'
    )

    book_folder, book_filename, book_m4b_filename = generate_names(
        title=title,
        series=series,
        authors=authors,
        edition=loan.get("edition") or "",
        args=args,
        logger=logger,
    )

    # check early if a merged file is already saved
    if args.merge_output and os.path.isfile(
        book_filename if args.merge_format == "mp3" else book_m4b_filename
    ):
        logger.warning(
            'Already saved "%s"',
            colored(
                book_filename if args.merge_format == "mp3" else book_m4b_filename,
                "magenta",
            ),
        )
        return

    if args.is_debug_mode:
        with open(os.path.join(book_folder, "loan.json"), "w", encoding="utf-8") as f:
            json.dump(loan, f, indent=2)

        with open(
            os.path.join(book_folder, "openbook.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(openbook, f, indent=2)

    debug_filename = os.path.join(book_folder, "debug.json")

    cover_filename, cover_bytes = generate_cover(
        book_folder=book_folder,
        cover_url=cover_url,
        session=session,
        timeout=args.timeout,
        logger=logger,
    )

    keep_cover = args.always_keep_cover
    file_tracks = []
    audio_bitrate = 0
    for p in download_parts:
        part_number = p["spine-position"] + 1
        part_filename = os.path.join(
            book_folder,
            f"{slugify(f'{title} - Part {part_number:02d}', allow_unicode=True)}.mp3",
        )
        part_tmp_filename = f"{part_filename}.part"
        part_file_size = p["file-length"]
        part_download_url = p["url"]

        if os.path.isfile(part_filename):
            logger.warning("Already saved %s", colored(part_filename, "magenta"))
        else:
            try:
                already_downloaded_len = 0
                if os.path.exists(part_tmp_filename):
                    already_downloaded_len = os.stat(part_tmp_filename).st_size

                part_download_res = session.get(
                    part_download_url,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Range": f"bytes={already_downloaded_len}-"
                        if already_downloaded_len
                        else None,
                    },
                    timeout=args.timeout,
                    stream=True,
                )
                part_download_res.raise_for_status()

                with tqdm.wrapattr(
                    part_download_res.raw,
                    "read",
                    total=part_file_size,
                    initial=already_downloaded_len,
                    desc=f"Part {part_number:2d}",
                    disable=args.hide_progress,
                ) as res_raw:
                    with open(
                        part_tmp_filename, "ab" if already_downloaded_len else "wb"
                    ) as outfile:
                        shutil.copyfileobj(res_raw, outfile)

                # try to remux file to remove mp3 lame tag errors
                remux_mp3(
                    part_tmp_filename=part_tmp_filename,
                    part_filename=part_filename,
                    ffmpeg_loglevel=ffmpeg_loglevel,
                    logger=logger,
                )

            except HTTPError as he:
                logger.error(f"HTTPError: {str(he)}")
                logger.debug(he.response.content)
                raise RuntimeError("HTTP Error while downloading part file.")

            except ConnectionError as ce:
                logger.error(f"ConnectionError: {str(ce)}")
                raise RuntimeError("Connection Error while downloading part file.")

        try:
            # Fill id3 info for mp3 part
            audiofile = eyed3.load(part_filename)
            variable_bitrate, audio_bitrate = audiofile.info.bit_rate
            if variable_bitrate:
                # don't use vbr
                audio_bitrate = 0
            write_tags(
                audiofile=audiofile,
                title=title,
                sub_title=sub_title,
                authors=authors,
                narrators=narrators,
                publisher=publisher,
                description=description,
                cover_bytes=cover_bytes,
                genres=subjects,
                languages=languages,
                published_date=publish_date,
                series=series,
                part_number=part_number,
                total_parts=len(download_parts),
                overdrive_id=overdrive_media_id,
                always_overwrite=args.overwrite_tags,
                delimiter=args.tag_delimiter,
            )
            audiofile.tag.save()

            if (
                args.add_chapters
                and not args.merge_output
                and not audiofile.tag.table_of_contents
            ):
                toc = audiofile.tag.table_of_contents.set(
                    "toc".encode("ascii"),
                    toplevel=True,
                    ordered=True,
                    child_ids=[],
                    description="Table of Contents",
                )
                chapter_marks = p["chapters"]
                for i, m in enumerate(chapter_marks):
                    title_frameset = eyed3.id3.frames.FrameSet()
                    title_frameset.setTextFrame(eyed3.id3.frames.TITLE_FID, m.title)
                    chap = audiofile.tag.chapters.set(
                        f"ch{i}".encode("ascii"),
                        times=(
                            round(m.start_second * 1000),
                            round(m.end_second * 1000),
                        ),
                        sub_frames=title_frameset,
                    )
                    toc.child_ids.append(chap.element_id)
                    start_time = datetime.timedelta(seconds=m.start_second)
                    end_time = datetime.timedelta(seconds=m.end_second)
                    logger.debug(
                        'Added chap tag => %s: %s-%s "%s" to "%s"',
                        colored(f"ch{i}", "cyan"),
                        start_time,
                        end_time,
                        colored(m.title, "cyan"),
                        colored(part_filename, "blue"),
                    )
                audiofile.tag.save()

        except Exception as e:  # pylint: disable=broad-except
            logger.warning(
                "Error saving ID3: %s", colored(str(e), "red", attrs=["bold"])
            )
            keep_cover = True

        logger.info('Saved "%s"', colored(part_filename, "magenta"))
        file_tracks.append({"file": part_filename})

    debug_meta["file_tracks"] = file_tracks
    if args.merge_output:
        logger.info(
            'Generating "%s"...',
            colored(
                book_filename if args.merge_format == "mp3" else book_m4b_filename,
                "magenta",
            ),
        )

        merge_into_mp3(
            book_filename=book_filename,
            file_tracks=file_tracks,
            audio_bitrate=audio_bitrate,
            ffmpeg_loglevel=ffmpeg_loglevel,
            hide_progress=args.hide_progress,
            logger=logger,
        )

        audiofile = eyed3.load(book_filename)
        write_tags(
            audiofile=audiofile,
            title=title,
            sub_title=sub_title,
            authors=authors,
            narrators=narrators,
            publisher=publisher,
            description=description,
            cover_bytes=cover_bytes,
            genres=subjects,
            languages=languages,
            published_date=publish_date,
            series=series,
            part_number=0,
            total_parts=0,
            overdrive_id=overdrive_media_id,
            always_overwrite=args.overwrite_tags,
            delimiter=args.tag_delimiter,
        )

        if args.add_chapters and not audiofile.tag.table_of_contents:
            toc = audiofile.tag.table_of_contents.set(
                "toc".encode("ascii"),
                toplevel=True,
                ordered=True,
                child_ids=[],
                description="Table of Contents",
            )
            merged_markers = merge_toc(parsed_toc)
            debug_meta["merged_markers"] = [
                {"title": m.title, "start": m.start_second, "end": m.end_second}
                for m in merged_markers
            ]

            for i, m in enumerate(merged_markers):
                title_frameset = eyed3.id3.frames.FrameSet()
                title_frameset.setTextFrame(eyed3.id3.frames.TITLE_FID, m.title)
                chap = audiofile.tag.chapters.set(
                    f"ch{i}".encode("ascii"),
                    times=(round(m.start_second * 1000), round(m.end_second * 1000)),
                    sub_frames=title_frameset,
                )
                toc.child_ids.append(chap.element_id)
                start_time = datetime.timedelta(seconds=m.start_second)
                end_time = datetime.timedelta(seconds=m.end_second)
                logger.debug(
                    'Added chap tag => %s: %s-%s "%s" to "%s"',
                    colored(f"ch{i}", "cyan"),
                    start_time,
                    end_time,
                    colored(m.title, "cyan"),
                    colored(book_filename, "blue"),
                )

        audiofile.tag.save()

        if args.merge_format == "mp3":
            logger.info(
                'Merged files into "%s"',
                colored(
                    book_filename if args.merge_format == "mp3" else book_m4b_filename,
                    "magenta",
                ),
            )

        if args.merge_format == "m4b":
            convert_to_m4b(
                book_filename=book_filename,
                book_m4b_filename=book_m4b_filename,
                cover_filename=cover_filename,
                audio_bitrate=audio_bitrate,
                ffmpeg_loglevel=ffmpeg_loglevel,
                hide_progress=args.hide_progress,
                logger=logger,
            )

        if not args.keep_mp3:
            for file_track in file_tracks:
                try:
                    os.remove(file_track["file"])
                except Exception as e:  # pylint: disable=broad-except
                    logger.warning(f'Error deleting "{file_track["file"]}": {str(e)}')

    if not keep_cover and os.path.isfile(cover_filename):
        try:
            os.remove(cover_filename)
        except Exception as e:  # pylint: disable=broad-except
            logger.warning(f'Error deleting "{cover_filename}": {str(e)}')

    if args.generate_opf:
        opf_file_path = os.path.join(
            book_folder, f"{slugify(title, allow_unicode=True)}.opf"
        )
        if not os.path.exists(opf_file_path):
            od_client = OverDriveClient(
                user_agent=USER_AGENT, timeout=args.timeout, retry=args.retries
            )
            media_info = od_client.media(loan["id"])
            create_opf(
                media_info,
                cover_filename if keep_cover else None,
                file_tracks
                if not args.merge_output
                else [
                    {
                        "file": book_filename
                        if args.merge_format == "mp3"
                        else book_m4b_filename
                    }
                ],
                opf_file_path,
                logger,
            )
        else:
            logger.info("Already saved %s", colored(opf_file_path, "magenta"))

    if args.write_json:
        with open(debug_filename, "w", encoding="utf-8") as outfile:
            json.dump(debug_meta, outfile, indent=2)

    if not args.is_debug_mode:
        # clean up
        for file_name in (
            "openbook.json",
            "loan.json",
        ):
            target = os.path.join(book_folder, file_name)
            if os.path.exists(target):
                os.remove(target)

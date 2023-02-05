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

import os
import subprocess
import sys
from urllib.parse import urlparse

import eyed3
import requests
from eyed3.utils import art
from termcolor import colored

from .constants import PERFORMER_FID
from .libby import USER_AGENT


def generate_names(title, authors, args):
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
    title,
    authors,
    narrators,
    publisher,
    description,
    cover_bytes,
    part_number,
    total_parts,
    overwrite_title=False,
):
    """
    Write out ID3 tags to the audiofile

    :param audiofile:
    :param title:
    :param authors:
    :param narrators:
    :param publisher:
    :param description:
    :param cover_bytes:
    :param part_number:
    :param total_parts:
    :param overwrite_title:
    :return:
    """
    if not audiofile.tag:
        audiofile.initTag()
    if overwrite_title or not audiofile.tag.title:
        audiofile.tag.title = str(title)
    if not audiofile.tag.album:
        audiofile.tag.album = str(title)
    if authors and not audiofile.tag.artist:
        audiofile.tag.artist = str(authors[0])
    if authors and not audiofile.tag.album_artist:
        audiofile.tag.album_artist = str(authors[0])
    if part_number and not audiofile.tag.track_num:
        audiofile.tag.track_num = (part_number, total_parts)
    if narrators and not audiofile.tag.getTextFrame(PERFORMER_FID):
        audiofile.tag.setTextFrame(PERFORMER_FID, str(narrators[0]))
    if publisher and not audiofile.tag.publisher:
        audiofile.tag.publisher = str(publisher)
    if description and eyed3.id3.frames.COMMENT_FID not in audiofile.tag.frame_set:
        audiofile.tag.comments.set(str(description), description="Description")
    if cover_bytes:
        audiofile.tag.images.set(
            art.TO_ID3_ART_TYPES[art.FRONT_COVER][0],
            cover_bytes,
            "image/jpeg",
            description="Cover",
        )


def generate_cover(book_folder, cover_url, session, timeout, logger):
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

    cover_bytes = None
    if os.path.isfile(cover_filename):
        with open(cover_filename, "rb") as f:
            cover_bytes = f.read()

    return cover_filename, cover_bytes


def merge_into_mp3(book_filename, file_tracks, ffmpeg_loglevel, hide_progress, logger):
    """
    Merge the files into a single mp3

    :param book_filename: mp3 file name
    :param file_tracks:
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


def convert_to_m4b(
    book_filename,
    book_m4b_filename,
    cover_filename,
    ffmpeg_loglevel,
    hide_progress,
    logger,
):
    """
    Converts the merged mp3 into a m4b

    :param book_filename: mp3 file name
    :param book_m4b_filename:
    :param cover_filename:
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
    logger.info('Merged files into "%s"', colored(book_m4b_filename, "magenta"))
    try:
        os.remove(book_filename)
    except Exception as e:  # pylint: disable=broad-except
        logger.warning(f'Error deleting "{book_filename}": {str(e)}')

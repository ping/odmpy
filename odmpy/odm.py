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
import datetime
import logging
import os
import sys
import xml.etree.ElementTree
from http.client import HTTPConnection

import requests
from requests.exceptions import HTTPError, ConnectionError
from termcolor import colored

from .utils import slugify
from .processing import process_odm, process_audiobook_loan
from .constants import UA_LONG
from .libby import LibbyClient

logger = logging.getLogger(__file__)
requests_logger = logging.getLogger("urllib3")
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
logger.addHandler(ch)
logger.setLevel(logging.INFO)
requests_logger.addHandler(ch)
requests_logger.setLevel(logging.WARNING)
requests_logger.propagate = True

__version__ = "0.6.4"  # also update ../setup.py


def add_common_download_arguments(parser_dl: argparse.ArgumentParser):
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
        "--opf",
        dest="generate_opf",
        action="store_true",
        help="Generate an OPF file for the book",
    )
    parser_dl.add_argument(
        "--overwritetags",
        dest="overwrite_tags",
        action="store_true",
        help=(
            "Always overwrite ID3 tags. By default odmpy tries to non-destructively "
            "tag audiofiles. This option forces odmpy to overwrite tags where possible."
        ),
    )
    parser_dl.add_argument(
        "--tagsdelimiter",
        dest="tag_delimiter",
        metavar="DELIMITER",
        type=str,
        default=";",
        help=(
            "For ID3 tags with multiple values, this defines the delimiter. "
            'For example, with the default delimiter ";", authors are written '
            'to the artist tag as "Author A;Author B;Author C".'
        ),
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
        description="Download/return an OverDrive loan audiobook",
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
        help="Settings folder to store odmpy required settings, e.g. Libby authentication",
    )
    parser_libby.add_argument(
        "--reset",
        dest="reset_settings",
        action="store_true",
        help="Remove previously saved odmpy Libby settings",
    )
    parser_libby.add_argument(
        "--direct",
        dest="libby_direct",
        action="store_true",
        help="Don't download the odm file from Libby but instead process the audiobook download directly",
    )
    parser_libby.add_argument(
        "--keepodm",
        action="store_true",
        help="Keep the downloaded odm and license files",
    )
    add_common_download_arguments(parser_libby)

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        requests_logger.setLevel(logging.DEBUG)
        HTTPConnection.debuglevel = 1

    if hasattr(args, "download_dir") and args.download_dir:
        args.download_dir = os.path.expanduser(args.download_dir)
    if hasattr(args, "settings_folder") and args.settings_folder:
        args.settings_folder = os.path.expanduser(args.settings_folder)

    # suppress warnings
    logging.getLogger("eyed3").setLevel(
        logging.WARNING if logger.level == logging.DEBUG else logging.ERROR
    )

    if args.command_name == "libby":
        client_title = "Libby Interactive Client"
        logger.info(client_title)
        logger.info("-" * 70)
        try:
            libby_client = LibbyClient(
                args.settings_folder, timeout=args.timeout, logger=logger
            )
            if args.reset_settings:
                libby_client.clear_settings()

            if not libby_client.has_sync_code():
                instructions = (
                    "A Libby setup code is needed to allow odmpy to interact with Libby.\n"
                    "To get a Libby code, see https://help.libbyapp.com/en-us/6070.htm\n"
                )
                logger.info(instructions)
                while True:
                    sync_code = input(
                        "Enter the 8-digit Libby code and press enter: "
                    ).strip()
                    if not sync_code:
                        return
                    if not LibbyClient.is_valid_sync_code(sync_code):
                        logger.warning("Invalid code: %s", colored(sync_code, "red"))
                        continue
                    break

                try:
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
                except requests.exceptions.HTTPError as he:
                    libby_client.clear_settings()
                    raise RuntimeError(
                        "Could not log in with code.\n"
                        "Make sure that you have entered the right code and within the time limit."
                    ) from he
            synced_state = libby_client.sync()
            audiobook_loans = [
                book
                for book in synced_state.get("loans", [])
                if libby_client.is_audiobook_loan(book)
            ]
            if not audiobook_loans:
                logger.info("No downloadable audiobook loans found.")
                return

            cards = synced_state.get("cards", [])
            logger.info(
                "Found %s downloadable loans.",
                colored(str(len(audiobook_loans)), "blue"),
            )
            # sort by checkout date so that recent most is at the bottom
            audiobook_loans = sorted(audiobook_loans, key=lambda l: l["checkoutDate"])
            for index, loan in enumerate(audiobook_loans, start=1):
                expiry_date = datetime.datetime.strptime(
                    loan["expireDate"], "%Y-%m-%dT%H:%M:%SZ"
                )
                logger.info(
                    "%s: %-55s  %-25s  \n    * %s  %s",
                    colored(f"{index:2d}", attrs=["bold"]),
                    colored(loan["title"], attrs=["bold"]),
                    f'By: {loan["firstCreatorName"]}',
                    f"Expires: {expiry_date:%Y-%m-%d}",
                    next(
                        iter(
                            [
                                c["library"]["name"]
                                for c in cards
                                if c["cardId"] == loan["cardId"]
                            ]
                        )
                    ),
                )
            while True:
                loan_choices = input(
                    f'\nChoose from {colored(f"1-{len(audiobook_loans)}", attrs=["bold"])} '
                    "(separate choices with a space or leave blank to quit), \n"
                    "then press enter: "
                ).strip()
                if not loan_choices:
                    break

                loan_choices = loan_choices.split(" ")
                loan_choices_isvalid = True
                for loan_index_selected in loan_choices:
                    if (
                        (not loan_index_selected.isdigit())
                        or int(loan_index_selected) < 1
                        or int(loan_index_selected) > len(audiobook_loans)
                    ):
                        logger.warning(f"Invalid choice: {loan_index_selected}")
                        loan_choices_isvalid = False
                        continue
                if loan_choices_isvalid:
                    break

            if args.libby_direct:
                for loan_index_selected in loan_choices:
                    loan_index_selected = int(loan_index_selected)
                    selected_loan = audiobook_loans[loan_index_selected - 1]
                    logger.info(
                        'Opening book "%s"...', colored(selected_loan["title"], "blue")
                    )
                    openbook, toc = libby_client.process_audiobook(selected_loan)
                    process_audiobook_loan(
                        selected_loan,
                        openbook,
                        toc,
                        libby_client.libby_session,
                        args,
                        logger,
                    )
                return

            for loan_index_selected in loan_choices:
                loan_index_selected = int(loan_index_selected)
                selected_loan = audiobook_loans[loan_index_selected - 1]
                file_name = f'{selected_loan["title"]} {selected_loan["id"]}'
                odm_file_path = os.path.join(
                    args.download_dir,
                    f"{slugify(file_name, allow_unicode=True)}.odm",
                )
                # don't re-download odm if it already exists so that we don't
                # needlessly use up the fulfillment limits
                if not os.path.exists(odm_file_path):
                    logger.info(
                        'Opening book "%s"...', colored(selected_loan["title"], "blue")
                    )
                    odm_res_content = libby_client.fulfill_odm(
                        selected_loan["id"], selected_loan["cardId"], "audiobook-mp3"
                    )
                    with open(odm_file_path, "wb") as f:
                        f.write(odm_res_content)
                        logger.info(
                            "Downloaded odm to %s", colored(odm_file_path, "magenta")
                        )
                else:
                    logger.info("Already downloaded odm file: %s", odm_file_path)
                process_odm(
                    odm_file_path, args, logger, cleanup_odm_license=not args.keepodm
                )

        except RuntimeError as run_err:
            logger.error(colored(str(run_err), "red"))
        except Exception:  # noqa, pylint: disable=broad-except
            logger.exception(colored("An unexpected error has occured", "red"))

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

    process_odm(args.odm_file, args, logger)

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
import io
import json
import logging
import os
import sys
import time
import xml.etree.ElementTree
from enum import Enum
from http.client import HTTPConnection
from typing import Dict, List

import requests
from requests.exceptions import HTTPError, ConnectionError
from termcolor import colored

from .constants import UA_LONG
from .libby import LibbyClient
from .libby_errors import ClientBadRequestError
from .processing import process_odm, process_audiobook_loan
from .utils import slugify, get_element_text

logger = logging.getLogger(__file__)
requests_logger = logging.getLogger("urllib3")
ch = logging.StreamHandler(io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8"))
ch.setLevel(logging.DEBUG)
logger.addHandler(ch)
logger.setLevel(logging.INFO)
requests_logger.addHandler(ch)
requests_logger.setLevel(logging.WARNING)
requests_logger.propagate = True

__version__ = "0.6.7"  # also update ../setup.py


class OdmpyCommands(str, Enum):
    Information = "info"
    Download = "dl"
    Return = "ret"
    Libby = "libby"
    LibbyReturn = "libbyreturn"
    LibbyRenew = "libbyrenew"


def positive_int(value: str) -> int:
    """
    Ensure that argument is a postive integer

    :param value:
    :return:
    """
    try:
        int_value = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f'"{value}" is not a positive integer value')
    if int_value <= 0:
        raise argparse.ArgumentTypeError(f'"{value}" is not a positive integer value')
    return int_value


def valid_book_folder_format(value: str) -> str:
    try:
        value % {"Title": "", "Author": "", "Series": ""}
    except KeyError as err:
        raise argparse.ArgumentTypeError(
            f'"{value}" is not a valid book folder name format: Invalid field {err}'
        ) from err
    except Exception as err:
        raise argparse.ArgumentTypeError(
            f'"{value}" is not a valid book folder name format: {err}'
        ) from err
    return value


def add_common_libby_arguments(parser_libby: argparse.ArgumentParser) -> None:
    parser_libby.add_argument(
        "--settings",
        dest="settings_folder",
        type=str,
        default="./odmpy_settings",
        metavar="SETTINGS_FOLDER",
        help="Settings folder to store odmpy required settings, e.g. Libby authentication.",
    )


def add_common_download_arguments(parser_dl: argparse.ArgumentParser) -> None:
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
        help="Download folder path.",
    )
    parser_dl.add_argument(
        "-c",
        "--chapters",
        dest="add_chapters",
        action="store_true",
        help="Add chapter marks (experimental).",
    )
    parser_dl.add_argument(
        "-m",
        "--merge",
        dest="merge_output",
        action="store_true",
        help="Merge into 1 file (experimental, requires ffmpeg).",
    )
    parser_dl.add_argument(
        "--mergeformat",
        dest="merge_format",
        choices=["mp3", "m4b"],
        default="mp3",
        help="Merged file format (m4b is slow, experimental, requires ffmpeg).",
    )
    parser_dl.add_argument(
        "-k",
        "--keepcover",
        dest="always_keep_cover",
        action="store_true",
        help="Always generate the cover image file (cover.jpg).",
    )
    parser_dl.add_argument(
        "-f",
        "--keepmp3",
        dest="keep_mp3",
        action="store_true",
        help="Keep downloaded mp3 files (after merging).",
    )
    parser_dl.add_argument(
        "--nobookfolder",
        dest="no_book_folder",
        action="store_true",
        help="Don't create a book subfolder.",
    )
    parser_dl.add_argument(
        "--bookfolderformat",
        dest="book_folder_format",
        type=valid_book_folder_format,
        default="%(Title)s - %(Author)s",
        help=(
            'Book folder format string. Default "%%(Title)s - %%(Author)s".\n'
            "Available fields:\n"
            "  %%(Title)s : Title\n"
            "  %%(Author)s: Comma-separated Author names\n"
            "  %%(Series)s: Series\n"
        ),
    )
    parser_dl.add_argument(
        "--overwritetags",
        dest="overwrite_tags",
        action="store_true",
        help=(
            "Always overwrite ID3 tags.\n"
            "By default odmpy tries to non-destructively tag audiofiles.\n"
            "This option forces odmpy to overwrite tags where possible."
        ),
    )
    parser_dl.add_argument(
        "--tagsdelimiter",
        dest="tag_delimiter",
        metavar="DELIMITER",
        type=str,
        default=";",
        help=(
            "For ID3 tags with multiple values, this defines the delimiter.\n"
            'For example, with the default delimiter ";", authors are written '
            'to the artist tag as "Author A;Author B;Author C".'
        ),
    )
    parser_dl.add_argument(
        "--opf",
        dest="generate_opf",
        action="store_true",
        help="Generate an OPF file for the book.",
    )
    parser_dl.add_argument(
        "-r",
        "--retry",
        dest="obsolete_retries",
        type=int,
        default=0,
        help="Obsolete. Do not use.",
    )
    parser_dl.add_argument(
        "-j",
        "--writejson",
        dest="write_json",
        action="store_true",
        help="Generate a meta json file (for debugging).",
    )
    parser_dl.add_argument(
        "--hideprogress",
        dest="hide_progress",
        action="store_true",
        help="Hide the download progress bar (e.g. during testing).",
    )


def extract_odm(
    libby_client: LibbyClient, selected_loan: Dict, args: argparse.Namespace
) -> str:
    """
    Extracts the ODM file for processing

    :param libby_client:
    :param selected_loan:
    :param args:
    :return: The path to the ODM file
    """
    file_name = f'{selected_loan["title"]} {selected_loan["id"]}'
    odm_file_path = os.path.join(
        args.download_dir,
        f"{slugify(file_name, allow_unicode=True)}.odm",
    )
    # don't re-download odm if it already exists so that we don't
    # needlessly use up the fulfillment limits
    if not os.path.exists(odm_file_path):
        logger.info(
            'Opening book "%s"...',
            colored(selected_loan["title"], "blue"),
        )
        odm_res_content = libby_client.fulfill_odm(
            selected_loan["id"],
            selected_loan["cardId"],
            "audiobook-mp3",
        )
        with open(odm_file_path, "wb") as f:
            f.write(odm_res_content)
            logger.info(
                "Downloaded odm to %s",
                colored(odm_file_path, "magenta"),
            )
    else:
        logger.info("Already downloaded odm file: %s", odm_file_path)

    return odm_file_path


def run() -> None:
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
        "--version",
        action="version",
        version=(
            f"%(prog)s {__version__} "
            f"[Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}-{sys.platform}]"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="store_true",
        help="Enable more verbose messages for debugging.",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        dest="timeout",
        type=int,
        default=10,
        help="Timeout (seconds) for network requests. Default 10.",
    )
    parser.add_argument(
        "-r",
        "--retry",
        dest="retries",
        type=int,
        default=1,
        help="Number of retries if a network request fails. Default 1.",
    )

    subparsers = parser.add_subparsers(
        title="Available commands",
        dest="command_name",
        help="To get more help, use the -h option with the command.",
    )

    # odm info parser
    parser_info = subparsers.add_parser(
        OdmpyCommands.Information.value,
        description="Get information about a loan file.",
        help="Get information about a loan file",
    )
    parser_info.add_argument(
        "-f",
        "--format",
        dest="format",
        choices=["text", "json"],
        default="text",
        help="Format for output.",
    )
    parser_info.add_argument("odm_file", type=str, help="ODM file path.")

    # odm download parser
    parser_dl = subparsers.add_parser(
        OdmpyCommands.Download.value,
        description="Download from a loan file.",
        help="Download from a loan odm file.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser_dl.add_argument("odm_file", type=str, help="ODM file path.")
    add_common_download_arguments(parser_dl)

    # odm return parser
    parser_ret = subparsers.add_parser(
        OdmpyCommands.Return.value,
        description="Return a loan file.",
        help="Return a loan file.",
    )
    parser_ret.add_argument("odm_file", type=str, help="ODM file path.")

    # libby download parser
    parser_libby = subparsers.add_parser(
        OdmpyCommands.Libby.value,
        description="Interactive Libby Interface for downloading audiobook loans.",
        help="Download audiobooks via Libby.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_common_libby_arguments(parser_libby)
    parser_libby.add_argument(
        "--reset",
        dest="reset_settings",
        action="store_true",
        help="Remove previously saved odmpy Libby settings.",
    )
    parser_libby.add_argument(
        "--direct",
        dest="libby_direct",
        action="store_true",
        help="Don't download the odm file from Libby but instead process the audiobook download directly.",
    )
    parser_libby.add_argument(
        "--keepodm",
        action="store_true",
        help="Keep the downloaded odm and license files.",
    )
    parser_libby.add_argument(
        "--latest",
        dest="download_latest_n",
        type=positive_int,
        default=0,
        metavar="N",
        help="Non-interactive mode that downloads the latest N number of loans.",
    )
    parser_libby.add_argument(
        "--select",
        dest="selected_loans_indices",
        type=positive_int,
        nargs="+",
        metavar="N",
        help=(
            "Non-interactive mode that downloads loans by the index entered.\n"
            'For example, "--select 1 5" will download the first and fifth loans in '
            "order of the checked out date.\n"
            "If the 5th loan does not exist, it will be skipped."
        ),
    )
    parser_libby.add_argument(
        "--exportloans",
        dest="export_loans_path",
        metavar="LOANS_JSON_FILEPATH",
        type=str,
        help="Non-interactive mode that exports audiobook loans information into a json file at the path specified.",
    )
    add_common_download_arguments(parser_libby)

    # libby return parser
    parser_libby_return = subparsers.add_parser(
        OdmpyCommands.LibbyReturn.value,
        description="Interactive Libby Interface for returning audiobook loans.",
        help="Return audiobook loans via Libby.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_common_libby_arguments(parser_libby_return)

    # libby renew parser
    parser_libby_renew = subparsers.add_parser(
        OdmpyCommands.LibbyRenew.value,
        description="Interactive Libby Interface for renewing audiobook loans.",
        help="Renew audiobook loans via Libby.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_common_libby_arguments(parser_libby_renew)

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        requests_logger.setLevel(logging.DEBUG)
        HTTPConnection.debuglevel = 1

    if hasattr(args, "download_dir") and args.download_dir:
        args.download_dir = os.path.expanduser(args.download_dir)
    if hasattr(args, "settings_folder") and args.settings_folder:
        args.settings_folder = os.path.expanduser(args.settings_folder)
    if hasattr(args, "export_loans_path") and args.export_loans_path:
        args.export_loans_path = os.path.expanduser(args.export_loans_path)

    # suppress warnings
    logging.getLogger("eyed3").setLevel(
        logging.WARNING if logger.level == logging.DEBUG else logging.ERROR
    )

    if hasattr(args, "obsolete_retries") and args.obsolete_retries:
        # retire --retry on the subcommands, after v0.6.7
        logger.warning(
            f"{'*' * 60}\n⚠️  The %s option for the %s command is no longer valid, and\n"
            f"has been moved to the base odmpy command, example: 'odmpy --retry {args.obsolete_retries}'.\n"
            f"Please change your command to '%s' instead\n{'*' * 60}",
            colored("--retry/-r", "red"),
            colored(args.command_name, "red"),
            colored(
                f"odmpy --retry {args.obsolete_retries} {args.command_name}",
                attrs=["bold"],
            ),
        )
        time.sleep(3)

    if args.command_name in (
        OdmpyCommands.Libby,
        OdmpyCommands.LibbyReturn,
        OdmpyCommands.LibbyRenew,
    ):
        client_title = "Libby Interactive Client"
        logger.info(client_title)
        logger.info("-" * 70)
        try:
            libby_client = LibbyClient(
                settings_folder=args.settings_folder,
                max_retries=args.retries,
                timeout=args.timeout,
                logger=logger,
            )
            if args.command_name == OdmpyCommands.Libby and args.reset_settings:
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

            # sort by checkout date so that recent most is at the bottom
            audiobook_loans = sorted(
                [
                    book
                    for book in synced_state.get("loans", [])
                    if libby_client.is_audiobook_loan(book)
                ],
                key=lambda ln: ln["checkoutDate"],  # type: ignore[no-any-return]
            )

            if args.command_name == OdmpyCommands.Libby and args.export_loans_path:
                logger.info(
                    "Non-interactive mode. Exporting loans json to %s...",
                    colored(args.export_loans_path, "magenta"),
                )
                with open(args.export_loans_path, "w", encoding="utf-8") as f:
                    json.dump(audiobook_loans, f)
                    logger.info(
                        'Saved loans as "%s"',
                        colored(args.export_loans_path, "magenta", attrs=["bold"]),
                    )
                return

            if args.command_name == OdmpyCommands.LibbyRenew:
                audiobook_loans = [
                    loan for loan in audiobook_loans if libby_client.is_renewable(loan)
                ]
                if not audiobook_loans:
                    logger.info("No renewable audiobook loans found.")
                    return

            if not audiobook_loans:
                logger.info("No downloadable audiobook loans found.")
                return
            if args.command_name == OdmpyCommands.Libby and (
                args.selected_loans_indices or args.download_latest_n
            ):
                selected_loans_indices = []
                total_loans_count = len(audiobook_loans)
                if args.selected_loans_indices:
                    selected_loans_indices.extend(
                        [
                            j
                            for j in args.selected_loans_indices
                            if j <= total_loans_count
                        ]
                    )
                    logger.info(
                        "Non-interactive mode. Downloading selected loan(s) %s...",
                        colored(
                            ", ".join([str(i) for i in selected_loans_indices]),
                            "blue",
                            attrs=["bold"],
                        ),
                    )
                if args.download_latest_n:
                    logger.info(
                        "Non-interactive mode. Downloading latest %s loan(s)...",
                        colored(str(args.download_latest_n), "blue"),
                    )
                    selected_loans_indices.extend(
                        list(range(1, len(audiobook_loans) + 1))[
                            -args.download_latest_n :
                        ]
                    )
                selected_loans_indices = sorted(list(set(selected_loans_indices)))
                selected_loans: List[Dict] = [
                    audiobook_loans[j - 1] for j in selected_loans_indices
                ]
                if args.libby_direct:
                    for selected_loan in selected_loans:
                        logger.info(
                            'Opening book "%s"...',
                            colored(selected_loan["title"], "blue"),
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
                for selected_loan in selected_loans:
                    process_odm(
                        extract_odm(libby_client, selected_loan, args),
                        args,
                        logger,
                        cleanup_odm_license=not args.keepodm,
                    )
                return

            cards = synced_state.get("cards", [])
            logger.info(
                "Found %s loans.",
                colored(str(len(audiobook_loans)), "blue"),
            )
            for index, loan in enumerate(audiobook_loans, start=1):
                expiry_date = datetime.datetime.strptime(
                    loan["expireDate"], "%Y-%m-%dT%H:%M:%SZ"
                )
                logger.info(
                    "%s: %-55s  %-25s  \n    * %s  %s",
                    colored(f"{index:2d}", attrs=["bold"]),
                    colored(loan["title"], attrs=["bold"]),
                    f'By: {loan["firstCreatorName"]}',
                    f"Expires: {colored(f'{expiry_date:%Y-%m-%d}','blue' if libby_client.is_renewable(loan) else None)}",
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
            loan_choices: List[str] = []

            libby_mode = "download"
            if args.command_name == OdmpyCommands.LibbyReturn:
                libby_mode = "return"
            elif args.command_name == OdmpyCommands.LibbyRenew:
                libby_mode = "renew"
            while True:
                user_loan_choice_input = input(
                    f'\n{colored(libby_mode.title(), "magenta", attrs=["bold"])}. '
                    f'Choose from {colored(f"1-{len(audiobook_loans)}", attrs=["bold"])} '
                    "(separate choices with a space or leave blank to quit), \n"
                    "then press enter: "
                ).strip()
                if not user_loan_choice_input:
                    break

                loan_choices = list(set(user_loan_choice_input.split(" ")))
                loan_choices_isvalid = True
                for loan_index_selected in loan_choices:
                    if (
                        (not loan_index_selected.isdigit())
                        or int(loan_index_selected) < 0
                        or int(loan_index_selected) > len(audiobook_loans)
                    ):
                        logger.warning(f"Invalid choice: {loan_index_selected}")
                        loan_choices_isvalid = False
                        continue
                if loan_choices_isvalid:
                    break

            if args.command_name == OdmpyCommands.LibbyReturn:
                # do returns
                for c in loan_choices:
                    selected_loan = audiobook_loans[int(c) - 1]
                    logger.info(
                        'Returning loan "%s"...',
                        colored(selected_loan["title"], "blue"),
                    )
                    libby_client.return_loan(selected_loan)
                return

            if args.command_name == OdmpyCommands.LibbyRenew:
                # do renewals
                for c in loan_choices:
                    selected_loan = audiobook_loans[int(c) - 1]
                    logger.info(
                        'Renewing loan "%s"...',
                        colored(selected_loan["title"], "blue"),
                    )
                    try:
                        _ = libby_client.renew_loan(selected_loan)
                    except ClientBadRequestError as badreq_err:
                        logger.warning(
                            'Error encountered while renewing "%s": %s',
                            selected_loan["title"],
                            colored(badreq_err.msg, "red"),
                        )
                return

            if args.command_name == OdmpyCommands.Libby:
                # do downloads
                if args.libby_direct:
                    for c in loan_choices:
                        selected_loan = audiobook_loans[int(c) - 1]
                        logger.info(
                            'Opening book "%s"...',
                            colored(selected_loan["title"], "blue"),
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

                for c in loan_choices:
                    selected_loan = audiobook_loans[int(c) - 1]
                    process_odm(
                        extract_odm(libby_client, selected_loan, args),
                        args,
                        logger,
                        cleanup_odm_license=not args.keepodm,
                    )
                return

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
        early_return_url = get_element_text(root.find("EarlyReturnURL"))
        if not early_return_url:
            raise RuntimeError("Unable to get EarlyReturnURL")
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

    if args.command_name in ("dl", "info"):
        process_odm(args.odm_file, args, logger)
        return

    # we shouldn't get this error
    logger.error("Unknown command: %s", colored(args.command_name, "red"))

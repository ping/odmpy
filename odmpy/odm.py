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
import io
import json
import logging
import os
import sys
import time
from http.client import HTTPConnection
from pathlib import Path
from typing import Dict, List, Optional

from termcolor import colored

from .cli_utils import (
    OdmpyCommands,
    OdmpyNoninteractiveOptions,
    positive_int,
    valid_book_folder_file_format,
    DEFAULT_FORMAT_FIELDS,
)
from .errors import LibbyNotConfiguredError, OdmpyRuntimeError
from .libby import LibbyClient, LibbyFormats
from .libby_errors import ClientBadRequestError, ClientError
from .overdrive import OverDriveClient
from .processing import (
    process_odm,
    process_audiobook_loan,
    process_odm_return,
    process_ebook_loan,
)
from .processing.shared import (
    generate_names,
    generate_cover,
    get_best_cover_url,
    init_session,
    extract_authors_from_openbook,
)
from .utils import slugify, plural_or_singular_noun as ps, parse_datetime

#
# Orchestrates the interaction between the CLI, APIs and the processing bits
#

logger = logging.getLogger(__name__)
requests_logger = logging.getLogger("urllib3")
ch = logging.StreamHandler(io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8"))
ch.setLevel(logging.DEBUG)
logger.addHandler(ch)
logger.setLevel(logging.INFO)
requests_logger.addHandler(ch)
requests_logger.setLevel(logging.ERROR)
requests_logger.propagate = True

__version__ = "0.7.9"  # also update ../setup.py
TAGS_ENDPOINT = "https://api.github.com/repos/ping/odmpy/tags"
REPOSITORY_URL = "https://github.com/ping/odmpy"


def check_version(timeout: int, max_retries: int) -> None:
    sess = init_session(max_retries)
    # noinspection PyBroadException
    try:
        res = sess.get(TAGS_ENDPOINT, timeout=timeout)
        res.raise_for_status()
        curr_version = res.json()[0].get("name", "")
        if curr_version and curr_version != __version__:
            logger.warning(
                f"⚠️  A new version {curr_version} is available at {REPOSITORY_URL}."
            )
    except:  # noqa: E722, pylint: disable=bare-except
        pass


def add_common_libby_arguments(parser_libby: argparse.ArgumentParser) -> None:
    parser_libby.add_argument(
        "--settings",
        dest="settings_folder",
        type=str,
        default="./odmpy_settings",
        metavar="SETTINGS_FOLDER",
        help="Settings folder to store odmpy required settings, e.g. Libby authentication.",
    )
    parser_libby.add_argument(
        "--ebooks",
        dest="include_ebooks",
        default=False,
        action="store_true",
        help=(
            "Include ebook (EPUB/PDF) loans (experimental). An EPUB/PDF (DRM) loan will be downloaded as an .acsm file"
            "\nwhich can be opened in Adobe Digital Editions for offline reading."
            "\nRefer to https://help.overdrive.com/en-us/0577.html and "
            "\nhttps://help.overdrive.com/en-us/0005.html for more information."
            "\nAn open EPUB/PDF (no DRM) loan will be downloaded as an .epub/.pdf file which can be opened"
            "\nin any EPUB/PDF-compatible reader."
            if parser_libby.prog == f"odmpy {OdmpyCommands.Libby}"
            else "Include ebook (EPUB/PDF) loans."
        ),
    )
    parser_libby.add_argument(
        "--magazines",
        dest="include_magazines",
        default=False,
        action="store_true",
        help=(
            "Include magazines loans (experimental)."
            if parser_libby.prog == f"odmpy {OdmpyCommands.Libby}"
            else "Include magazines loans."
        ),
    )
    parser_libby.add_argument(
        "--noaudiobooks",
        dest="exclude_audiobooks",
        default=False,
        action="store_true",
        help="Exclude audiobooks.",
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
        help="Add chapter marks (experimental). For audiobooks.",
    )
    parser_dl.add_argument(
        "-m",
        "--merge",
        dest="merge_output",
        action="store_true",
        help="Merge into 1 file (experimental, requires ffmpeg). For audiobooks.",
    )
    parser_dl.add_argument(
        "--mergeformat",
        dest="merge_format",
        choices=["mp3", "m4b"],
        default="mp3",
        help="Merged file format (m4b is slow, experimental, requires ffmpeg). For audiobooks.",
    )
    parser_dl.add_argument(
        "--mergecodec",
        dest="merge_codec",
        choices=["aac", "libfdk_aac"],
        default="aac",
        help="Audio codec of merged m4b file. (requires ffmpeg; using libfdk_aac requires ffmpeg compiled with libfdk_aac support). For audiobooks. Has no effect if mergeformat is not set to m4b.",
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
        help="Keep downloaded mp3 files (after merging). For audiobooks.",
    )
    parser_dl.add_argument(
        "--nobookfolder",
        dest="no_book_folder",
        action="store_true",
        help="Don't create a book subfolder.",
    )

    available_fields_help = [
        "%%(Title)s : Title",
        "%%(Author)s: Comma-separated Author names",
        "%%(Series)s: Series",
    ]
    if parser_dl.prog == "odmpy libby":
        available_fields_help.append("%%(ReadingOrder)s: Series Reading Order")
    available_fields_help.extend(["%%(Edition)s: Edition", "%%(ID)s: Title/Loan ID"])
    available_fields_help_text = "Available fields:\n  " + "\n  ".join(
        available_fields_help
    )

    available_fields = list(DEFAULT_FORMAT_FIELDS)
    if parser_dl.prog != "odmpy libby":
        available_fields.remove("ReadingOrder")

    parser_dl.add_argument(
        "--bookfolderformat",
        dest="book_folder_format",
        type=lambda v: valid_book_folder_file_format(v, tuple(available_fields)),
        default="%(Title)s - %(Author)s",
        help=f'Book folder format string. Default "%%(Title)s - %%(Author)s".\n{available_fields_help_text}',
    )
    parser_dl.add_argument(
        "--bookfileformat",
        dest="book_file_format",
        type=lambda v: valid_book_folder_file_format(v, tuple(available_fields)),
        default="%(Title)s - %(Author)s",
        help=(
            'Book file format string (without extension). Default "%%(Title)s - %%(Author)s".\n'
            f"This applies to only merged audiobooks, ebooks, and magazines.\n{available_fields_help_text}"
        ),
    )
    parser_dl.add_argument(
        "--removefrompaths",
        dest="remove_from_paths",
        metavar="ILLEGAL_CHARS",
        type=str,
        help=r'Remove characters in string specified from folder and file names, example "<>:"/\|?*"',
    )
    parser_dl.add_argument(
        "--overwritetags",
        dest="overwrite_tags",
        action="store_true",
        help=(
            "Always overwrite ID3 tags.\n"
            "By default odmpy tries to non-destructively tag audiofiles.\n"
            "This option forces odmpy to overwrite tags where possible. For audiobooks."
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
            'For example, with the default delimiter ";", authors are written\n'
            'to the artist tag as "Author A;Author B;Author C". For audiobooks.'
        ),
    )
    parser_dl.add_argument(
        "--id3v2version",
        dest="id3v2_version",
        type=int,
        default=4,
        choices=[3, 4],
        help="ID3 v2 version. 3 = v2.3, 4 = v2.4",
    )
    parser_dl.add_argument(
        "--opf",
        dest="generate_opf",
        action="store_true",
        help="Generate an OPF file for the downloaded audiobook/magazine/ebook.",
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


def extract_bundled_contents(
    libby_client: LibbyClient,
    overdrive_client: OverDriveClient,
    selected_loan: Dict,
    cards: List[Dict],
    args: argparse.Namespace,
):
    format_id = libby_client.get_loan_format(selected_loan)
    format_info: Dict = next(
        iter([f for f in selected_loan.get("formats", []) if f["id"] == format_id]),
        {},
    )
    card: Dict = next(
        iter([c for c in cards if c["cardId"] == selected_loan["cardId"]]), {}
    )
    if format_info.get("isBundleParent") and format_info.get("bundledContent", []):
        bundled_contents_ids = list(
            set([bc["titleId"] for bc in format_info["bundledContent"]])
        )
        for bundled_content_id in bundled_contents_ids:
            bundled_media = overdrive_client.library_media(
                card["advantageKey"], bundled_content_id
            )
            if not libby_client.is_downloadable_ebook_loan(bundled_media):
                continue
            # patch in cardId from parent loan details
            bundled_media["cardId"] = selected_loan["cardId"]
            extract_loan_file(libby_client, bundled_media, args)


def extract_loan_file(
    libby_client: LibbyClient, selected_loan: Dict, args: argparse.Namespace
) -> Optional[Path]:
    """
    Extracts the ODM / ACSM / EPUB(open) file

    :param libby_client:
    :param selected_loan:
    :param args:
    :return: The path to the ODM file
    """
    try:
        format_id = LibbyClient.get_loan_format(selected_loan)
    except ValueError as err:
        err_msg = str(err)
        if "kindle" in str(err):
            logger.error(
                "You may have already sent the loan to your Kindle device: %s",
                colored(err_msg, "red"),
            )
        else:
            logger.error(colored(err_msg, "red"))
        return None

    file_ext = "odm"
    file_name = f'{selected_loan["title"]} {selected_loan["id"]}'
    loan_file_path = Path(
        args.download_dir, f"{slugify(file_name, allow_unicode=True)}.{file_ext}"
    )
    if (
        args.libby_direct
        and libby_client.has_format(selected_loan, LibbyFormats.EBookOverdrive)
        and not (
            # don't do direct downloads for PDF loans because these turn out badly
            libby_client.has_format(selected_loan, LibbyFormats.EBookPDFAdobe)
            or libby_client.has_format(selected_loan, LibbyFormats.EBookPDFOpen)
        )
    ):
        format_id = LibbyFormats.EBookOverdrive

    openbook: Dict = {}
    rosters: List[Dict] = []
    # pre-extract openbook first so that we can use it to create the book folder
    # with the creator names (needed to place the cover.jpg download)
    if format_id in (LibbyFormats.EBookOverdrive, LibbyFormats.MagazineOverDrive):
        _, openbook, rosters = libby_client.process_ebook(selected_loan)

    cover_path = None
    if format_id in (
        LibbyFormats.EBookEPubAdobe,
        LibbyFormats.EBookEPubOpen,
        LibbyFormats.EBookOverdrive,
        LibbyFormats.MagazineOverDrive,
        LibbyFormats.EBookPDFAdobe,
        LibbyFormats.EBookPDFOpen,
    ):
        file_ext = (
            "acsm"
            if format_id in (LibbyFormats.EBookEPubAdobe, LibbyFormats.EBookPDFAdobe)
            else "pdf"
            if format_id == LibbyFormats.EBookPDFOpen
            else "epub"
        )
        book_folder, book_file_name = generate_names(
            title=selected_loan["title"],
            series=selected_loan.get("series") or "",
            series_reading_order=selected_loan.get("detailedSeries", {}).get(
                "readingOrder", ""
            ),
            authors=extract_authors_from_openbook(openbook)
            or (
                [selected_loan["firstCreatorName"]]
                if selected_loan.get("firstCreatorName")
                else []
            ),  # for open-epub
            edition=selected_loan.get("edition") or "",
            title_id=selected_loan["id"],
            args=args,
            logger=logger,
        )
        loan_file_path = book_file_name.with_suffix(f".{file_ext}")
        if (
            format_id
            in (
                LibbyFormats.EBookOverdrive,
                LibbyFormats.MagazineOverDrive,
            )
            and not loan_file_path.exists()
        ):
            # we need the cover for embedding
            cover_path, _ = generate_cover(
                book_folder=book_folder,
                cover_url=get_best_cover_url(selected_loan),
                session=init_session(args.retries),
                timeout=args.timeout,
                logger=logger,
                force_square=False,
            )

    # don't re-download odm if it already exists so that we don't
    # needlessly use up the fulfillment limits
    if not loan_file_path.exists():
        if format_id in (LibbyFormats.EBookOverdrive, LibbyFormats.MagazineOverDrive):
            process_ebook_loan(
                loan=selected_loan,
                cover_path=cover_path,
                openbook=openbook,
                rosters=rosters,
                libby_client=libby_client,
                args=args,
                logger=logger,
            )
        else:
            # formats: odm, acsm, open-epub, open-pdf
            try:
                odm_res_content = libby_client.fulfill_loan_file(
                    selected_loan["id"], selected_loan["cardId"], format_id
                )
                with loan_file_path.open("wb") as f:
                    f.write(odm_res_content)
                    logger.info(
                        'Downloaded %s to "%s"',
                        file_ext,
                        colored(str(loan_file_path), "magenta"),
                    )
            except ClientError as ce:
                if ce.http_status == 400 and libby_client.is_downloadable_ebook_loan(
                    selected_loan
                ):
                    logger.error(
                        "%s %s",
                        colored(
                            f"Unable to download {file_ext}.", "red", attrs=["bold"]
                        ),
                        colored("You may have sent the loan to a Kindle.", "red"),
                    )
                    return None
                raise
    else:
        logger.info(
            "Already downloaded %s file %s",
            file_ext,
            colored(str(loan_file_path), "magenta"),
        )

    if cover_path and cover_path.exists() and not args.always_keep_cover:
        # clean up
        cover_path.unlink()

    return loan_file_path


def run(custom_args: Optional[List[str]] = None, be_quiet: bool = False) -> None:
    """

    :param custom_args: Used by unittests
    :param be_quiet: Used by unittests
    :return:
    """
    parser = argparse.ArgumentParser(
        prog="odmpy",
        description="Manage your OverDrive loans",
        epilog=(
            f"Version {__version__}. "
            f"[Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}-{sys.platform}] "
            f"Source at {REPOSITORY_URL}"
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
    parser.add_argument(
        "--noversioncheck",
        dest="dont_check_version",
        default=False,
        action="store_true",
        help="Do not check if newer version is available.",
    )

    subparsers = parser.add_subparsers(
        title="Available commands",
        dest="command_name",
        help="To get more help, use the -h option with the command.",
    )

    # libby download parser
    parser_libby = subparsers.add_parser(
        OdmpyCommands.Libby,
        description="Interactive Libby Interface for downloading loans.",
        help="Download audiobook/ebook/magazine loans via Libby.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_common_libby_arguments(parser_libby)
    add_common_download_arguments(parser_libby)
    parser_libby.add_argument(
        "--direct",
        dest="libby_direct",
        action="store_true",
        help=(
            "Process the download directly from Libby without "
            "\ndownloading an odm/acsm file. For audiobooks/eBooks."
        ),
    )
    parser_libby.add_argument(
        "--keepodm",
        action="store_true",
        help="Keep the downloaded odm and license files. For audiobooks.",
    )
    parser_libby.add_argument(
        "--latest",
        dest=OdmpyNoninteractiveOptions.DownloadLatestN,
        type=positive_int,
        default=0,
        metavar="N",
        help="Non-interactive mode that downloads the latest N number of loans.",
    )
    parser_libby.add_argument(
        "--select",
        dest=OdmpyNoninteractiveOptions.DownloadSelectedN,
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
        "--selectid",
        dest=OdmpyNoninteractiveOptions.DownloadSelectedId,
        type=positive_int,
        nargs="+",
        metavar="ID",
        help=(
            "Non-interactive mode that downloads loans by the loan ID entered.\n"
            'For example, "--selectid 12345" will download the loan with the ID 12345.\n'
            "If the loan with the ID does not exist, it will be skipped."
        ),
    )
    parser_libby.add_argument(
        "--exportloans",
        dest=OdmpyNoninteractiveOptions.ExportLoans,
        metavar="LOANS_JSON_FILEPATH",
        type=str,
        help="Non-interactive mode that exports loan information into a json file at the path specified.",
    )
    parser_libby.add_argument(
        "--reset",
        dest="reset_settings",
        action="store_true",
        help="Remove previously saved odmpy Libby settings.",
    )
    parser_libby.add_argument(
        "--check",
        dest=OdmpyNoninteractiveOptions.Check,
        action="store_true",
        help="Non-interactive mode that displays Libby signed-in status and token if authenticated.",
    )
    parser_libby.add_argument(
        "--debug",
        dest="is_debug_mode",
        action="store_true",
        help="Debug switch for use during development. Please do not use.",
    )

    # libby return parser
    parser_libby_return = subparsers.add_parser(
        OdmpyCommands.LibbyReturn,
        description="Interactive Libby Interface for returning loans.",
        help="Return loans via Libby.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_common_libby_arguments(parser_libby_return)

    # libby renew parser
    parser_libby_renew = subparsers.add_parser(
        OdmpyCommands.LibbyRenew,
        description="Interactive Libby Interface for renewing loans.",
        help="Renew loans via Libby.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_common_libby_arguments(parser_libby_renew)

    # odm download parser
    parser_dl = subparsers.add_parser(
        OdmpyCommands.Download,
        description="Download from an audiobook loan file (odm).",
        help="Download from an audiobook loan file (odm).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser_dl.add_argument("odm_file", type=str, help="ODM file path.")
    add_common_download_arguments(parser_dl)

    # odm return parser
    parser_ret = subparsers.add_parser(
        OdmpyCommands.Return,
        description="Return an audiobook loan file (odm).",
        help="Return an audiobook loan file (odm).",
    )
    parser_ret.add_argument("odm_file", type=str, help="ODM file path.")

    # odm info parser
    parser_info = subparsers.add_parser(
        OdmpyCommands.Information,
        description="Get information about an audiobook loan file (odm).",
        help="Get information about an audiobook loan file (odm).",
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

    args = parser.parse_args(custom_args)

    if be_quiet:
        # in test mode
        ch.setLevel(logging.ERROR)
    elif args.verbose:
        logger.setLevel(logging.DEBUG)
        requests_logger.setLevel(logging.DEBUG)
        HTTPConnection.debuglevel = 1

    if hasattr(args, "download_dir") and args.download_dir:
        download_dir = Path(args.download_dir)
        if not download_dir.exists():
            # prevents FileNotFoundError when using libby odm-based downloads
            # because the odm is first downloaded into the download dir
            # without a book folder
            download_dir.mkdir(parents=True, exist_ok=True)
        args.download_dir = str(download_dir.expanduser())

    if hasattr(args, "settings_folder") and args.settings_folder:
        args.settings_folder = str(Path(args.settings_folder).expanduser())
    if hasattr(args, "export_loans_path") and args.export_loans_path:
        args.export_loans_path = str(Path(args.export_loans_path).expanduser())

    # suppress warnings
    logging.getLogger("eyed3").setLevel(
        logging.WARNING if logger.level == logging.DEBUG else logging.ERROR
    )

    if not args.dont_check_version:
        check_version(args.timeout, args.retries)

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

    try:
        # Libby-based commands
        if args.command_name in (
            OdmpyCommands.Libby,
            OdmpyCommands.LibbyReturn,
            OdmpyCommands.LibbyRenew,
        ):
            logger.info(
                "%s Interactive Client for Libby", colored("odmpy", attrs=["bold"])
            )
            logger.info("-" * 70)

            token = os.environ.get("LIBBY_TOKEN")
            if token:
                # use token auth if available
                libby_client = LibbyClient(
                    identity_token=token,
                    max_retries=args.retries,
                    timeout=args.timeout,
                    logger=logger,
                )
            else:
                libby_client = LibbyClient(
                    settings_folder=args.settings_folder,
                    max_retries=args.retries,
                    timeout=args.timeout,
                    logger=logger,
                )

            overdrive_client = OverDriveClient(
                user_agent=libby_client.user_agent,
                timeout=args.timeout,
                retry=args.retries,
            )

            if args.command_name == OdmpyCommands.Libby and args.reset_settings:
                libby_client.clear_settings()
                logger.info("Cleared settings.")
                return

            if args.command_name == OdmpyCommands.Libby and args.check_signed_in:
                if not libby_client.get_token():
                    raise LibbyNotConfiguredError("Libby has not been setup.")
                if not libby_client.is_logged_in():
                    raise LibbyNotConfiguredError("Libby is not signed-in.")
                logger.info(
                    "Libby is signed-in with token:\n%s", libby_client.get_token()
                )
                return

            # detect if non-interactive command options are selected before setup
            if not libby_client.get_token():
                if [
                    opt_name
                    for opt_name in OdmpyNoninteractiveOptions
                    if hasattr(args, opt_name) and getattr(args, opt_name)
                ]:
                    raise OdmpyRuntimeError(
                        'Libby has not been setup. Please run "odmpy libby" first.'
                    )

            if not libby_client.get_token():
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
                        raise OdmpyRuntimeError(
                            "Could not log in with code.\n"
                            "Make sure that you have entered the right code and within the time limit.\n"
                            "You also need to have at least 1 registered library card."
                        )
                    logger.info("Login successful.\n")
                except ClientError as ce:
                    libby_client.clear_settings()
                    raise OdmpyRuntimeError(
                        "Could not log in with code.\n"
                        "Make sure that you have entered the right code and within the time limit."
                    ) from ce

            synced_state = libby_client.sync()
            cards = synced_state.get("cards", [])
            # sort by checkout date so that recent most is at the bottom
            libby_loans = sorted(
                [
                    book
                    for book in synced_state.get("loans", [])
                    if (
                        (not args.exclude_audiobooks)
                        and libby_client.is_downloadable_audiobook_loan(book)
                    )
                    or (
                        args.include_ebooks
                        and libby_client.is_downloadable_ebook_loan(book)
                    )
                    or (
                        args.include_magazines
                        and libby_client.is_downloadable_magazine_loan(book)
                    )
                ],
                key=lambda ln: ln["checkoutDate"],  # type: ignore[no-any-return]
            )

            if args.command_name == OdmpyCommands.Libby and args.export_loans_path:
                logger.info(
                    "Non-interactive mode. Exporting loans json to %s...",
                    colored(args.export_loans_path, "magenta"),
                )
                with open(args.export_loans_path, "w", encoding="utf-8") as f:
                    json.dump(libby_loans, f)
                    logger.info(
                        'Saved loans as "%s"',
                        colored(args.export_loans_path, "magenta", attrs=["bold"]),
                    )
                return

            if args.command_name == OdmpyCommands.LibbyRenew:
                libby_loans = [
                    loan for loan in libby_loans if libby_client.is_renewable(loan)
                ]
                if not libby_loans:
                    logger.info("No renewable loans found.")
                    return

            if not libby_loans:
                logger.info("No downloadable loans found.")
                return

            if args.command_name == OdmpyCommands.Libby and (
                args.selected_loans_indices
                or args.download_latest_n
                or args.selected_loans_ids
            ):
                # Non-interactive selection
                selected_loans_indices = []
                total_loans_count = len(libby_loans)
                if args.selected_loans_indices:
                    selected_loans_indices.extend(
                        [
                            j
                            for j in args.selected_loans_indices
                            if j <= total_loans_count
                        ]
                    )
                    logger.info(
                        "Non-interactive mode. Downloading selected %s %s...",
                        ps(len(selected_loans_indices), "loan"),
                        colored(
                            ", ".join([str(i) for i in selected_loans_indices]),
                            "blue",
                            attrs=["bold"],
                        ),
                    )
                if args.download_latest_n:
                    logger.info(
                        "Non-interactive mode. Downloading latest %s %s...",
                        colored(str(args.download_latest_n), "blue"),
                        ps(args.download_latest_n, "loan"),
                    )
                    selected_loans_indices.extend(
                        list(range(1, len(libby_loans) + 1))[-args.download_latest_n :]
                    )
                if args.selected_loans_ids:
                    selected_loans_ids = [str(i) for i in args.selected_loans_ids]
                    logger.info(
                        "Non-interactive mode. Downloading loans with %s %s...",
                        ps(len(selected_loans_ids), "ID"),
                        ", ".join([colored(i, "blue") for i in selected_loans_ids]),
                    )
                    for n, loan in enumerate(libby_loans, start=1):
                        if loan["id"] in selected_loans_ids:
                            selected_loans_indices.append(n)
                selected_loans_indices = sorted(list(set(selected_loans_indices)))
                selected_loans: List[Dict] = [
                    libby_loans[j - 1] for j in selected_loans_indices
                ]
                if args.libby_direct:
                    for selected_loan in selected_loans:
                        logger.info(
                            'Opening %s "%s"...',
                            selected_loan.get("type", {}).get("id"),
                            colored(selected_loan["title"], "blue"),
                        )
                        if libby_client.is_downloadable_audiobook_loan(selected_loan):
                            openbook, toc = libby_client.process_audiobook(
                                selected_loan
                            )
                            process_audiobook_loan(
                                selected_loan,
                                openbook,
                                toc,
                                libby_client.libby_session,
                                args,
                                logger,
                            )
                            extract_bundled_contents(
                                libby_client,
                                overdrive_client,
                                selected_loan,
                                cards,
                                args,
                            )
                            continue
                        elif libby_client.is_downloadable_ebook_loan(
                            selected_loan
                        ) or libby_client.is_downloadable_magazine_loan(selected_loan):
                            extract_loan_file(libby_client, selected_loan, args)
                            continue
                    return

                for selected_loan in selected_loans:
                    logger.info(
                        'Opening %s "%s"...',
                        selected_loan.get("type", {}).get("id"),
                        colored(selected_loan["title"], "blue"),
                    )
                    if libby_client.is_downloadable_audiobook_loan(selected_loan):
                        process_odm(
                            extract_loan_file(libby_client, selected_loan, args),
                            selected_loan,
                            args,
                            logger,
                            cleanup_odm_license=not args.keepodm,
                        )
                        extract_bundled_contents(
                            libby_client,
                            overdrive_client,
                            selected_loan,
                            cards,
                            args,
                        )

                    elif libby_client.is_downloadable_ebook_loan(
                        selected_loan
                    ) or libby_client.is_downloadable_magazine_loan(selected_loan):
                        extract_loan_file(libby_client, selected_loan, args)
                        continue

                return  # non-interactive libby downloads

            # Interactive mode
            holds = synced_state.get("holds", [])
            logger.info(
                "Found %s %s.",
                colored(str(len(libby_loans)), "blue"),
                ps(len(libby_loans), "loan"),
            )
            for index, loan in enumerate(libby_loans, start=1):
                expiry_date = parse_datetime(loan["expireDate"])
                hold = next(
                    iter(
                        [
                            h
                            for h in holds
                            if h["cardId"] == loan["cardId"] and h["id"] == loan["id"]
                        ]
                    ),
                    None,
                )
                hold_date = parse_datetime(hold["placedDate"]) if hold else None

                logger.info(
                    "%s: %-55s  %s %-25s  \n    * %s  %s%s",
                    colored(f"{index:2d}", attrs=["bold"]),
                    colored(loan["title"], attrs=["bold"]),
                    "📰"
                    if args.include_magazines
                    and libby_client.is_downloadable_magazine_loan(loan)
                    else "📕"
                    if args.include_ebooks
                    and libby_client.is_downloadable_ebook_loan(loan)
                    else "🎧"
                    if args.include_ebooks or args.include_magazines
                    else "",
                    loan["firstCreatorName"]
                    if loan.get("firstCreatorName")
                    else loan.get("edition", ""),
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
                    ""
                    if not libby_client.is_renewable(loan)
                    else (
                        f'\n    * {loan.get("availableCopies", 0)} '
                        f'{ps(loan.get("availableCopies", 0), "copy", "copies")} available'
                    )
                    + (f" (hold placed: {hold_date:%Y-%m-%d})" if hold else ""),
                )
            loan_choices: List[str] = []

            # Loans display and user choice prompt
            libby_mode = "download"
            if args.command_name == OdmpyCommands.LibbyReturn:
                libby_mode = "return"
            elif args.command_name == OdmpyCommands.LibbyRenew:
                libby_mode = "renew"
            while True:
                user_loan_choice_input = input(
                    f'\n{colored(libby_mode.title(), "magenta", attrs=["bold"])}. '
                    f'Choose from {colored(f"1-{len(libby_loans)}", attrs=["bold"])} '
                    "(separate choices with a space or leave blank to quit), \n"
                    "then press enter: "
                ).strip()
                if not user_loan_choice_input:
                    # abort choice if user enters blank
                    break

                loan_choices = list(set(user_loan_choice_input.split(" ")))
                loan_choices_isvalid = True
                for loan_index_selected in loan_choices:
                    if (
                        (not loan_index_selected.isdigit())
                        or int(loan_index_selected) < 0
                        or int(loan_index_selected) > len(libby_loans)
                    ):
                        logger.warning(f"Invalid choice: {loan_index_selected}")
                        loan_choices_isvalid = False
                        loan_choices = []
                        break
                if loan_choices_isvalid:
                    break

            if not loan_choices:
                # abort if no choices made
                return

            loan_choices = sorted(loan_choices, key=int)

            if args.command_name == OdmpyCommands.LibbyReturn:
                # do returns
                for c in loan_choices:
                    selected_loan = libby_loans[int(c) - 1]
                    logger.info(
                        'Returning loan "%s"...',
                        colored(selected_loan["title"], "blue"),
                    )
                    libby_client.return_loan(selected_loan)
                    logger.info(
                        'Returned "%s".',
                        colored(selected_loan["title"], "blue"),
                    )
                return  # end libby return command

            if args.command_name == OdmpyCommands.LibbyRenew:
                # do renewals
                for c in loan_choices:
                    selected_loan = libby_loans[int(c) - 1]
                    logger.info(
                        'Renewing loan "%s"...',
                        colored(selected_loan["title"], "blue"),
                    )
                    try:
                        _ = libby_client.renew_loan(selected_loan)
                        logger.info(
                            'Renewed "%s".',
                            colored(selected_loan["title"], "blue"),
                        )
                    except ClientBadRequestError as badreq_err:
                        logger.warning(
                            'Error encountered while renewing "%s": %s',
                            selected_loan["title"],
                            colored(badreq_err.msg, "red"),
                        )
                        if selected_loan.get("availableCopies", 0) == 0 and not [
                            h
                            for h in holds
                            if h["cardId"] == selected_loan["cardId"]
                            and h["id"] == selected_loan["id"]
                        ]:
                            # offer to make a hold
                            make_hold = input(
                                "Do you wish to place a hold instead? (y/n): "
                            ).strip()
                            if make_hold == "y":
                                hold = libby_client.create_hold(
                                    selected_loan["id"], selected_loan["cardId"]
                                )
                                logger.info(
                                    "Hold successfully created for %s. You are #%s in line. %s %s in use. Available in ~%s %s.",
                                    colored(hold["title"], attrs=["bold"]),
                                    hold.get("holdListPosition", 0),
                                    hold.get("ownedCopies"),
                                    ps(hold.get("ownedCopies", 0), "copy", "copies"),
                                    hold.get("estimatedWaitDays", 0),
                                    ps(hold.get("estimatedWaitDays", 0), "day"),
                                )

                return  # end libby renew command

            if args.command_name == OdmpyCommands.Libby:
                # do downloads
                if args.libby_direct:
                    for c in loan_choices:
                        selected_loan = libby_loans[int(c) - 1]
                        logger.info(
                            'Opening %s "%s"...',
                            selected_loan.get("type", {}).get("id"),
                            colored(selected_loan["title"], "blue"),
                        )
                        if libby_client.is_downloadable_audiobook_loan(selected_loan):
                            openbook, toc = libby_client.process_audiobook(
                                selected_loan
                            )
                            process_audiobook_loan(
                                selected_loan,
                                openbook,
                                toc,
                                libby_client.libby_session,
                                args,
                                logger,
                            )
                            extract_bundled_contents(
                                libby_client,
                                overdrive_client,
                                selected_loan,
                                cards,
                                args,
                            )
                            continue
                        elif libby_client.is_downloadable_ebook_loan(
                            selected_loan
                        ) or libby_client.is_downloadable_magazine_loan(selected_loan):
                            extract_loan_file(libby_client, selected_loan, args)
                            continue

                    return

                for c in loan_choices:
                    selected_loan = libby_loans[int(c) - 1]
                    logger.info(
                        'Opening %s "%s"...',
                        selected_loan.get("type", {}).get("id"),
                        colored(selected_loan["title"], "blue"),
                    )
                    if libby_client.is_downloadable_audiobook_loan(selected_loan):
                        process_odm(
                            extract_loan_file(libby_client, selected_loan, args),
                            selected_loan,
                            args,
                            logger,
                            cleanup_odm_license=not args.keepodm,
                        )
                        extract_bundled_contents(
                            libby_client, overdrive_client, selected_loan, cards, args
                        )
                        continue
                    elif libby_client.is_downloadable_ebook_loan(
                        selected_loan
                    ) or libby_client.is_downloadable_magazine_loan(selected_loan):
                        extract_loan_file(libby_client, selected_loan, args)
                        continue
                return

            return  # end libby commands

        # Legacy ODM-based commands from here on

        # because py<=3.6 does not support `add_subparsers(required=True)`
        try:
            # test for odm file
            args.odm_file
        except AttributeError:
            parser.print_help()
            return

        # Return Book
        if args.command_name == OdmpyCommands.Return:
            process_odm_return(args, logger)
            return

        if args.command_name in (OdmpyCommands.Download, OdmpyCommands.Information):
            if args.command_name == OdmpyCommands.Download:
                logger.info(
                    'Opening odm "%s"...',
                    colored(args.odm_file, "blue"),
                )
            process_odm(Path(args.odm_file), {}, args, logger)
            return

    except OdmpyRuntimeError as run_err:
        logger.error(
            "%s %s",
            colored("Error:", attrs=["bold"]),
            colored(str(run_err), "red"),
        )
        raise

    except Exception:  # noqa, pylint: disable=broad-except
        logger.exception(colored("An unexpected error has occurred", "red"))
        raise

    # we shouldn't get this error
    logger.error("Unknown command: %s", colored(args.command_name, "red"))

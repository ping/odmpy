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
import json
import logging
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional, NamedTuple, Dict, List, Tuple
from typing import OrderedDict as OrderedDictType
from urllib import request

from odmpy.libby_errors import (
    ClientConnectionError,
    ClientTimeoutError,
    ErrorHandler,
)

if sys.version_info >= (3, 8):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter, Retry

#
# Client for the Libby web API, and helper functions to make sense
# of the stuff returned
#


class ChapterMarker(NamedTuple):
    title: str
    part_name: str
    start_second: float
    end_second: float


# TypedDict to hold the metadata about an audiobook part
PartMeta = TypedDict(
    "PartMeta",
    {
        "chapters": List[ChapterMarker],
        "url": str,
        "audio-duration": float,
        "file-length": int,
        "spine-position": int,
    },
)

FILE_PART_RE = re.compile(
    r"(?P<part_name>{[A-F0-9\-]{36}}[^#]+)(#(?P<second_stamp>\d+(\.\d+)?))?$"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_1) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/14.0.2 Safari/605.1.15"
)
AUDIOBOOK_MP3_FORMAT = "audiobook-mp3"
EBOOK_EPUB_ADOBE_FORMAT = "ebook-epub-adobe"
EBOOK_EPUB_OPEN_FORMAT = "ebook-epub-open"
EBOOK_OVERDRIVE_FORMAT = "ebook-overdrive"
EBOOK_EPUB_FORMATS = (
    EBOOK_EPUB_ADOBE_FORMAT,
    EBOOK_EPUB_OPEN_FORMAT,
    EBOOK_OVERDRIVE_FORMAT,
)
DOWNLOADABLE_FORMATS = (
    AUDIOBOOK_MP3_FORMAT,
    EBOOK_EPUB_ADOBE_FORMAT,
    EBOOK_EPUB_OPEN_FORMAT,
    EBOOK_OVERDRIVE_FORMAT,
)


def parse_part_path(title: str, part_path: str) -> ChapterMarker:
    """
    Extracts chapter marker info from the part path,
    e.g. {AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part03.mp3#3000
    yields `ChapterMarker(title, "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part03.mp3", 3000)`

    :param title:
    :param part_path:
    :return:
    """
    mobj = FILE_PART_RE.match(part_path)
    if not mobj:
        raise ValueError(f"Unexpected path format: {part_path}")
    return ChapterMarker(
        title=title,
        part_name=mobj.group("part_name"),
        start_second=float(mobj.group("second_stamp"))
        if mobj.group("second_stamp")
        else 0,
        end_second=0,
    )


def parse_toc(
    base_url: str, toc: List[Dict], spine: List[Dict]
) -> OrderedDictType[str, PartMeta]:
    """
    Parses `openbook["nav"]["toc"]` and `openbook["spine"]` to a format
    suitable for processing.

    :param base_url:
    :param toc:
    :param spine:
    :return:
    """
    entries: List[ChapterMarker] = []
    for item in toc:
        entries.append(parse_part_path(item["title"], item["path"]))
        for content in item.get("contents", []):
            # we use the original `item["title"]` instead of `content["title"]`
            # so that we can de-dup these entries later
            entries.append(parse_part_path(item["title"], content["path"]))

    # use an OrderedDict to ensure that we can consistently test this
    parsed_toc: OrderedDictType[str, PartMeta] = OrderedDict()

    for entry in entries:
        if entry.part_name not in parsed_toc:
            parsed_toc[entry.part_name] = {
                "chapters": [],
                "url": "",
                "audio-duration": 0,
                "file-length": 0,
                "spine-position": 0,
            }
        if not parsed_toc[entry.part_name]["chapters"]:
            # first entry for the part_name
            parsed_toc[entry.part_name]["chapters"].append(entry)
            continue
        # de-dup entries because OD sometimes generates timestamped chapter titles marks
        # for the same chapter in the same part, e.g. "Chapter 2 (00:00)", "Chapter 2 (12:34)"
        if entry.title == parsed_toc[entry.part_name]["chapters"][-1].title:
            continue
        parsed_toc[entry.part_name]["chapters"].append(entry)

    for s in spine:
        parsed_toc[s["-odread-original-path"]].update(
            {
                "url": urljoin(base_url, s["path"]),
                "audio-duration": s["audio-duration"],
                "file-length": s["-odread-file-bytes"],
                "spine-position": s["-odread-spine-position"],
            }
        )
    for chapter_mark in parsed_toc.values():  # type: PartMeta
        chapters = chapter_mark["chapters"]
        updated_chapters = []
        for i, chapter in enumerate(chapters):
            # update end_second mark
            updated_chapter = ChapterMarker(
                title=chapter.title,
                part_name=chapter.part_name,
                start_second=chapter.start_second,
                end_second=(
                    chapters[i + 1].start_second
                    if i < (len(chapters) - 1)
                    else chapter_mark["audio-duration"]
                ),
            )
            updated_chapters.append(updated_chapter)
        chapter_mark["chapters"] = updated_chapters

    return parsed_toc


def merge_toc(toc: Dict) -> List[ChapterMarker]:
    """
    Generates a list of ChapterMarker for the merged audiobook based on the parsed toc.

    :param toc: parsed toc
    :return:
    """
    chapters = OrderedDict()
    parts = list(toc.values())
    for i, part in enumerate(parts):
        cumu_part_duration = sum([p["audio-duration"] for p in parts[:i]])
        for marker in part["chapters"]:
            if marker.title not in chapters:
                chapters[marker.title] = {
                    "start": cumu_part_duration + marker.start_second,
                    "end": 0,
                }
            chapters[marker.title]["end"] = cumu_part_duration + marker.end_second

    return [
        ChapterMarker(
            title=title,
            part_name="",
            start_second=marker["start"],
            end_second=marker["end"],
        )
        for title, marker in list(chapters.items())
    ]


class LibbyClient(object):
    # Original reverse engineering of the libby endpoints is thanks to https://github.com/lullius/pylibby
    def __init__(
        self,
        settings_folder: str,
        max_retries: int = 0,
        timeout: int = 10,
        logger=Optional[logging.Logger],
        **kwargs,
    ) -> None:
        if not logger:
            logger = logging.getLogger(__name__)
        self.logger = logger
        self.settings_folder = settings_folder
        if not os.path.exists(self.settings_folder):
            os.makedirs(self.settings_folder, exist_ok=True)
        self.temp_folder = os.path.join(self.settings_folder, "temp")
        if not os.path.exists(self.temp_folder):
            os.makedirs(self.temp_folder, exist_ok=True)

        self.timeout = timeout
        self.identity = {}
        self.identity_settings_file = os.path.join(self.settings_folder, "libby.json")
        if os.path.exists(self.identity_settings_file):
            with open(self.identity_settings_file, "r", encoding="utf-8") as f:
                self.identity = json.load(f)

        # migrate old sync code storage key
        if self.identity.get("__odmpy_sync_code"):
            if not self.identity.get("__libby_sync_code"):
                self.identity["__libby_sync_code"] = self.identity["__odmpy_sync_code"]
            del self.identity["__odmpy_sync_code"]
            with open(self.identity_settings_file, "w", encoding="utf-8") as f:
                json.dump(self.identity, f)

        self.max_retries = max_retries
        libby_session = requests.Session()
        adapter = HTTPAdapter(max_retries=Retry(total=max_retries, backoff_factor=0.1))
        for prefix in ("http://", "https://"):
            libby_session.mount(prefix, adapter)
        self.libby_session = libby_session
        self.user_agent = kwargs.pop("user_agent", USER_AGENT)
        self.api_base = "https://sentry-read.svc.overdrive.com/"

    @staticmethod
    def is_valid_sync_code(code: str) -> bool:
        return code.isdigit() and len(code) == 8

    def default_headers(self) -> Dict:
        """
        Default HTTP headers.

        :return:
        """
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }

    def make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        method: Optional[str] = None,
        authenticated: bool = True,
        session: Optional[requests.sessions.Session] = None,
        return_res: bool = False,
        allow_redirects: bool = True,
    ):
        endpoint_url = urljoin(self.api_base, endpoint)
        if not method:
            # try to set a HTTP method
            if data is not None:
                method = "POST"
            else:
                method = "GET"
        if headers is None:
            headers = self.default_headers()
        if authenticated and self.has_chip():
            headers["Authorization"] = f'Bearer {self.identity["identity"]}'

        req = requests.Request(
            method,
            endpoint_url,
            headers=headers,
            params=params,
            data=data,
            json=json_data,
        )
        if not session:
            # default session
            session = self.libby_session

        try:
            res = session.send(
                session.prepare_request(req),
                timeout=self.timeout,
                allow_redirects=allow_redirects,
            )
            self.logger.debug("body: %s", res.text)

            res.raise_for_status()
            if return_res:
                return res
            return res.json()
        except requests.ConnectionError as conn_err:
            raise ClientConnectionError(str(conn_err)) from conn_err
        except requests.Timeout as timeout_err:
            raise ClientTimeoutError(str(timeout_err)) from timeout_err
        except requests.HTTPError as http_err:
            ErrorHandler.process(http_err)

    def save_settings(self, updates: Dict) -> None:
        """
        Persist identity settings.

        :param updates:
        :return:
        """
        self.identity.update(updates)
        with open(self.identity_settings_file, "w", encoding="utf-8") as f:
            json.dump(self.identity, f)

    def clear_settings(self) -> None:
        """
        Wipe previously saved settings.

        :return:
        """
        if os.path.exists(self.identity_settings_file):
            os.remove(self.identity_settings_file)
        self.identity = {}

    def has_chip(self) -> bool:
        """
        Check if client has identity token.

        :return:
        """
        return bool(self.identity.get("identity"))

    def has_sync_code(self) -> bool:
        """
        Check if client has linked account.

        :return:
        """
        return bool(
            self.identity.get("__libby_sync_code")
            or self.identity.get("__odmpy_sync_code")  # for backwards compat
        )

    def get_chip(self, auto_save: bool = True, authenticated: bool = False) -> Dict:
        """
        Get an identity chip (contains auth token).

        :param auto_save:
        :param authenticated:
        :return:
        """
        res: Dict = self.make_request(
            "/chip",
            params={"client": "dewey"},
            method="POST",
            authenticated=authenticated,
        )
        if auto_save:
            # persist to settings
            self.save_settings(res)
        return res

    def clone_by_code(self, code: str, auto_save: bool = True) -> Dict:
        """
        Link account to identy token retrieved in `get_chip()`.

        :param code:
        :param auto_save:
        :return:
        """
        if not self.is_valid_sync_code(code):
            raise ValueError(f"Invalid code: {code}")

        res: Dict = self.make_request("chip/clone/code", data={"code": code})
        if auto_save:
            # persist to settings
            self.save_settings({"__libby_sync_code": code})
        return res

    def sync(self) -> Dict:
        """
        Get the user account state, which includes loans, holds, etc.

        :return:
        """
        res: Dict = self.make_request("chip/sync")
        return res

    def is_logged_in(self) -> bool:
        """
        Check if successfully logged in.

        :return:
        """
        synced_state = self.sync()
        return synced_state.get("result", "") == "synchronized" and bool(
            synced_state.get("cards")
        )

    @staticmethod
    def is_downloadable_audiobook_loan(book: Dict) -> bool:
        """
        Verify if book is a downloadable audiobook.

        :param book:
        :return:
        """
        return bool(
            [f for f in book.get("formats", []) if f["id"] == AUDIOBOOK_MP3_FORMAT]
        )

    @staticmethod
    def is_downloadble_ebook_loan(book: Dict) -> bool:
        """
        Verify if book is a downloadable ebook.

        :param book:
        :return:
        """
        return bool(
            [f for f in book.get("formats", []) if f["id"] in EBOOK_EPUB_FORMATS]
        )

    @staticmethod
    def has_format(loan: Dict, format_id: str) -> bool:
        return bool(
            next(iter([f["id"] for f in loan["formats"] if f["id"] == format_id]), None)
        )

    @staticmethod
    def get_loan_format(loan: Dict) -> str:
        locked_in_format = next(
            iter([f["id"] for f in loan["formats"] if f["isLockedIn"]]), None
        )
        if locked_in_format:
            if locked_in_format in DOWNLOADABLE_FORMATS:
                return locked_in_format
            raise ValueError(
                f'Loan is locked to a non-downloadable format "{locked_in_format}"'
            )

        if not locked_in_format:
            if LibbyClient.is_open_ebook_loan(loan) and LibbyClient.has_format(
                loan, EBOOK_EPUB_OPEN_FORMAT
            ):
                return EBOOK_EPUB_OPEN_FORMAT
            elif LibbyClient.is_downloadble_ebook_loan(loan) and LibbyClient.has_format(
                loan, EBOOK_EPUB_ADOBE_FORMAT
            ):
                return EBOOK_EPUB_ADOBE_FORMAT
            elif LibbyClient.is_downloadable_audiobook_loan(
                loan
            ) and LibbyClient.has_format(loan, AUDIOBOOK_MP3_FORMAT):
                return AUDIOBOOK_MP3_FORMAT

        raise ValueError("Unable to find a downloadable format")

    @staticmethod
    def is_open_ebook_loan(book: Dict) -> bool:
        """
        Verify if book is an open epub.

        :param book:
        :return:
        """
        return bool(
            [f for f in book.get("formats", []) if f["id"] == EBOOK_EPUB_OPEN_FORMAT]
        )

    @staticmethod
    def is_renewable(loan: Dict) -> bool:
        """
        Check if loan can be renewed.

        :param loan:
        :return:
        """
        if not loan.get("renewableOn"):
            raise ValueError("Unable to get renewable date")
        # Example: 2023-02-23T07:33:55Z
        renewable_on = datetime.strptime(
            loan["renewableOn"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        return renewable_on <= datetime.utcnow().replace(tzinfo=timezone.utc)

    def get_loans(self) -> List[Dict]:
        """
        Get loans

        :return:
        """
        return self.sync().get("loans", [])

    def get_holds(self) -> List[Dict]:
        """
        Get holds

        :return:
        """
        return self.sync().get("holds", [])

    def get_downloadable_audiobook_loans(self) -> List[Dict]:
        """
        Get downloadable audiobook loans.

        :return:
        """
        return [
            book
            for book in self.sync().get("loans", [])
            if self.is_downloadable_audiobook_loan(book)
        ]

    def fulfill(self, loan_id: str, card_id: str, format_id: str) -> Dict:
        """
        Get the fulfillment details for a loan.

        :param loan_id:
        :param card_id:
        :param format_id:
        :return:
        """
        if format_id not in DOWNLOADABLE_FORMATS:
            raise ValueError(f"Invalid format_id: {format_id}")
        res: Dict = self.make_request(
            f"card/{card_id}/loan/{loan_id}/fulfill/{format_id}",
            return_res=True,
        )
        return res

    @staticmethod
    def _urlretrieve(
        endpoint: str, headers: Optional[Dict] = None, timeout: int = 15
    ) -> bytes:
        """
        Workaround for downloading an open (non-drm) epub.

        The fulfillment url 403s when using requests but
        works in curl, request.urlretrieve, etc.

        GET API fulfill endpoint -> 302 https://fulfill.contentreserve.com (fulfillment url)
        GET https://fulfill.contentreserve.com -> 302 https://openepub-gk.cdn.overdrive.com
        GET https://openepub-gk.cdn.overdrive.com 403

        Fresh session doesn't work either, headers doesn't seem to
        matter.

        .. code-block:: python
            sess = requests.Session()
            sess.headers.update({"User-Agent": USER_AGENT})
            res = sess.get(res_redirect.headers["Location"], timeout=self.timeout)
            res.raise_for_status()
            return res.content

        :param endpoint: fulfillment url
        :param headers:
        :param timeout:
        :return:
        """
        if not headers:
            headers = {}

        opener = request.build_opener()
        req = request.Request(endpoint, headers=headers)
        res = opener.open(req, timeout=timeout)
        return res.read()

    def fulfill_loan_file(self, loan_id: str, card_id: str, format_id: str) -> bytes:
        """
        Returns the loan file contents directly for MP3 audiobooks (.odm)
        and DRM epub (.acsm) loans.
        For open epub loans, the actual epub contents are returned.

        :param loan_id:
        :param card_id:
        :param format_id:
        :return:
        """
        if format_id not in DOWNLOADABLE_FORMATS:
            raise ValueError(f"Unsupported format_id: {format_id}")

        headers = self.default_headers()
        headers["Accept"] = "*/*"

        if format_id == EBOOK_EPUB_OPEN_FORMAT:
            res_redirect: requests.Response = self.make_request(
                f"card/{card_id}/loan/{loan_id}/fulfill/{format_id}",
                headers=headers,
                return_res=True,
                allow_redirects=False,
            )
            return self._urlretrieve(
                res_redirect.headers["Location"], headers=headers, timeout=self.timeout
            )

        res: requests.Response = self.make_request(
            f"card/{card_id}/loan/{loan_id}/fulfill/{format_id}",
            headers=headers,
            return_res=True,
        )
        return res.content

    def open_loan(self, loan_type: str, card_id: str, title_id: str) -> Dict:
        """
        Gets the meta urls needed to fulfill a loan.

        :param loan_type:
        :param card_id:
        :param title_id:
        :return:
        """
        res: Dict = self.make_request(
            f"open/{loan_type}/card/{card_id}/title/{title_id}"
        )
        return res

    def process_audiobook(
        self, loan: Dict
    ) -> Tuple[Dict, OrderedDictType[str, PartMeta]]:
        """
        Returns the data needed to download an audiobook.

        :param loan:
        :return:
        """
        loan_type = "audiobook" if loan["type"]["id"] == "audiobook" else "book"
        card_id = loan["cardId"]
        title_id = loan["id"]
        meta = self.open_loan(loan_type, card_id, title_id)
        download_base = meta["urls"]["web"]

        # Sets a needed cookie
        web_url = download_base + "?" + meta["message"]
        _ = self.make_request(
            web_url,
            headers={"Accept": "*/*"},
            method="HEAD",
            authenticated=False,
            return_res=True,
        )

        # contains nav/toc and spine
        openbook = self.make_request(meta["urls"]["openbook"])
        toc = parse_toc(download_base, openbook["nav"]["toc"], openbook["spine"])
        return openbook, toc

    def return_title(self, title_id: str, card_id: str) -> None:
        """
        Return book.
        If `return_all` is True, all loans with the title_id will be returned
        otherwise, only the oldest checked out loan is returned.

        :param title_id:
        :param card_id:
        :return:
        """
        self.make_request(
            f"card/{card_id}/loan/{title_id}", method="DELETE", return_res=True
        )

    def return_loan(self, loan: Dict) -> None:
        """
        Return a loan.

        :param loan:
        :return:
        """
        self.return_title(loan["id"], loan["cardId"])

    def borrow_title(
        self, title_id: str, title_format: str, card_id: str, days: int = 21
    ) -> Dict:
        """
        Return a title.

        :param title_id:
        :param title_format: Type ID
        :param card_id:
        :param days:
        :return:
        """
        data = {
            "period": days,
            "units": "days",
            "lucky_day": None,
            "title_format": title_format,
        }

        res: Dict = self.make_request(
            f"card/{card_id}/loan/{title_id}", json_data=data, method="POST"
        )
        return res

    def borrow_hold(self, hold: Dict) -> Dict:
        """
        Borrow a hold.

        :param hold:
        :return:
        """
        return self.borrow_title(hold["id"], hold["type"]["id"], hold["cardId"])

    def renew_title(
        self, title_id: str, title_format: str, card_id: str, days: int = 21
    ) -> Dict:
        """
        Return a title.

        :param title_id:
        :param title_format: Type ID
        :param card_id:
        :param days:
        :return:
        """
        data = {
            "period": days,
            "units": "days",
            "lucky_day": None,
            "title_format": title_format,
        }

        res: Dict = self.make_request(
            f"card/{card_id}/loan/{title_id}", json_data=data, method="PUT"
        )
        return res

    def renew_loan(self, loan: Dict) -> Dict:
        """
        Renew a loan.

        :param loan:
        :return:
        """
        return self.renew_title(loan["id"], loan["type"]["id"], loan["cardId"])

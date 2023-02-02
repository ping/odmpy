import glob
import logging
import os
import json
import re

import requests
from requests.adapters import HTTPAdapter, Retry


class LibbyClient(object):
    # Reverse engineering of the libby endpoints is thanks to https://github.com/lullius/pylibby
    def __init__(self, settings_folder, max_retries=0, timeout=10, logger=None):
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
        libby_session = requests.Session()
        thunder_session = requests.Session()
        adapter = HTTPAdapter(max_retries=Retry(total=max_retries, backoff_factor=0.1))
        for prefix in ("http://", "https://"):
            libby_session.mount(prefix, adapter)
            thunder_session.mount(prefix, adapter)
        self.libby_session = libby_session
        self.thunder_session = thunder_session

    def save_settings(self, updates):
        """
        Persist identity settings
        :param updates:
        :return:
        """
        self.identity.update(updates)
        with open(self.identity_settings_file, "w", encoding="utf-8") as f:
            json.dump(self.identity, f)

    def clear_settings(self):
        """
        Wipe previously saved settings
        :return:
        """
        if os.path.exists(self.identity_settings_file):
            os.remove(self.identity_settings_file)

    def has_chip(self):
        """
        Check if client has identity token
        :return:
        """
        return self.identity.get("identity")

    def has_sync_code(self):
        """
        Check if client has linked account
        :return:
        """
        return self.identity.get("__odmpy_sync_code")

    @staticmethod
    def default_headers(accept_json=True):
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        if accept_json:
            headers["Accept"] = "application/json"
        return headers

    def make_request(
        self,
        endpoint_url,
        params=None,
        data=None,
        headers=None,
        method=None,
        authenticated=True,
        session=None,
        return_res=False,
    ):
        if not method:
            # try to set a HTTP method
            if data is not None:
                method = "POST"
            else:
                method = "GET"
        if not headers:
            headers = self.default_headers()
        if authenticated and self.has_chip():
            headers["Authorization"] = f'Bearer {self.identity["identity"]}'

        req = requests.Request(
            method, endpoint_url, headers=headers, params=params, data=data
        )
        if not session:
            # default session
            session = self.libby_session

        self.logger.debug("REQUEST URL: %s", req.url)
        self.logger.debug("REQUEST HEADERS: %s", req.headers)

        res = session.send(session.prepare_request(req), timeout=self.timeout)
        self.logger.debug("RESPONSE URL: %s", res.url)
        self.logger.debug("RESPONSE HEADERS: %s", res.headers)
        self.logger.debug("RESPONSE BODY: %s", res.text)

        res.raise_for_status()
        if return_res:
            return res
        return res.json()

    def get_chip(self, auto_save=True, authenticated=False):
        """
        Get an identity chip (contains auth token)
        :param auto_save:
        :param authenticated:
        :return:
        """
        res = self.make_request(
            "https://sentry-read.svc.overdrive.com/chip",
            params={"client": "dewey"},
            method="POST",
            authenticated=authenticated,
        )
        if auto_save:
            # persist to settings
            self.save_settings(res)
        return res

    def clone_by_code(self, code, auto_save=True):
        """
        Link account to identy token retrieved in `get_chip()`
        :param code:
        :param auto_save:
        :return:
        """
        res = self.make_request(
            "https://sentry-read.svc.overdrive.com/chip/clone/code", data={"code": code}
        )
        if auto_save:
            # persist to settings
            self.save_settings({"__odmpy_sync_code": code})
        return res

    def sync(self):
        """
        Get the user account state, which includes loans, holds, etc
        :return:
        """
        return self.make_request("https://sentry-read.svc.overdrive.com/chip/sync")

    def is_logged_in(self):
        """
        Check if successfully logged in
        :return:
        """
        synced_state = self.sync()
        return synced_state.get("result", "") == "synchronized" and synced_state.get(
            "cards"
        )

    def media_info(self, media_id, refresh=False):
        """
        Get media info. For a loan, `media_id` is the `loan["id"]`.
        :param media_id:
        :param refresh:
        :return:
        """
        # [!] not used, not tested
        cached_media_info_file = os.path.join(
            self.temp_folder, f"{media_id}.media.json"
        )
        if os.path.exists(cached_media_info_file) and not refresh:
            with open(cached_media_info_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return self.make_request(
            f"https://thunder.api.overdrive.com/v2/media/{media_id}",
            session=self.thunder_session,
            authenticated=False,
        )

    def clean_media_cache(self, keep_ids=None):
        # [!] not used, not tested
        if not keep_ids:
            keep_ids = []
        media_id_re = re.compile(r"(?P<media_id>\d+)\.media\.json")

        cached_media_files = glob.glob(f"{self.temp_folder}/*.media.json")
        for cached_file in cached_media_files:
            mobj = media_id_re.match(os.path.basename(cached_file))
            if mobj and mobj.group("media_id") not in keep_ids:
                os.remove(cached_file)

    @staticmethod
    def is_audiobook_loan(book):
        """
        Verify if book is a downloadable audiobook
        :param book:
        :return:
        """
        return [f for f in book.get("formats", []) if f["id"] == "audiobook-mp3"]

    def get_audiobook_loans(self):
        """
        Get audiobook loans
        :return:
        """
        return [
            book
            for book in self.sync().get("loans", [])
            if self.is_audiobook_loan(book)
        ]

    def fulfill(self, loan_id, card_id, format_id):
        """
        Get the fulfillment details for a loan

        :param loan_id:
        :param card_id:
        :param format_id:
        :return:
        """
        endpoint_url = f"https://sentry-read.svc.overdrive.com/card/{card_id}/loan/{loan_id}/fulfill/{format_id}"
        return self.make_request(endpoint_url, return_res=True)

    def fulfill_odm(self, loan_id, card_id, format_id):
        """
        Returns the odm contents directly

        :param loan_id:
        :param card_id:
        :param format_id:
        :return:
        """
        endpoint_url = f"https://sentry-read.svc.overdrive.com/card/{card_id}/loan/{loan_id}/fulfill/{format_id}"
        return self.make_request(
            endpoint_url,
            headers=self.default_headers(accept_json=False),
            return_res=True,
        ).content

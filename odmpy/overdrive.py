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
from typing import Optional, Dict
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter, Retry

#
# Basic skeletal client for the OverDrive Thunder API
#

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_1) AppleWebKit/605.1.15 (KHTML, like Gecko) "  # noqa
    "Version/14.0.2 Safari/605.1.15"
)
SITE_URL = "https://libbyapp.com"
THUNDER_API_URL = "https://thunder.api.overdrive.com/v2/"
CLIENT_ID = "dewey"


class OverDriveClient(object):
    """
    A really simplified OverDrive Thunder API client
    """

    def __init__(self, **kwargs) -> None:
        """
        Constructor.

        :param kwargs:
            - user_agent: User Agent string for requests
            - timeout: The timeout interval for a network request. Default 15 (seconds).
            - retries: The number of times to retry a network request on failure. Default 0.
        """
        self.logger = logging.getLogger(__name__)
        self.user_agent = kwargs.pop("user_agent", USER_AGENT)
        self.timeout = int(kwargs.pop("timeout", 15))
        self.retries = int(kwargs.pop("retry", 0))

        session = requests.Session()
        adapter = HTTPAdapter(max_retries=Retry(total=self.retries, backoff_factor=0.1))
        # noinspection HttpUrlsUsage
        for prefix in ("http://", "https://"):
            session.mount(prefix, adapter)
        self.session = kwargs.pop("session", None) or session

    def default_headers(self) -> Dict:
        """
        Default http request headers.

        :return:
        """
        headers = {
            "User-Agent": self.user_agent,
            "Referer": SITE_URL + "/",
            "Origin": SITE_URL,
        }
        return headers

    def default_params(self) -> Dict:
        """
        Default set of GET request parameters.

        :return:
        """
        params = {"x-client-id": CLIENT_ID}
        return params

    def make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        method: Optional[str] = None,
    ):
        """
        Sends an API request.

        :param endpoint: Relative path to endpoint
        :param params: URL query parameters
        :param data: POST data parameters
        :param method: HTTP method, e.g. 'PUT'
        :param headers: Custom headers
        :return: Union[List, Dict, str]
        """
        endpoint_url = urljoin(THUNDER_API_URL, endpoint)
        headers = headers or self.default_headers()
        if not method:
            # try to set an HTTP method
            if data is not None:
                method = "POST"
            else:
                method = "GET"

        req = requests.Request(
            method,
            endpoint_url,
            headers=headers,
            params=params,
            data=data,
        )
        res = self.session.send(self.session.prepare_request(req), timeout=self.timeout)
        self.logger.debug("body: %s", res.text)
        res.raise_for_status()

        if res.headers.get("content-type", "").startswith("application/json"):
            return res.json()
        return res.text

    def media(self, title_id: str, **kwargs) -> Dict:
        """
        Retrieve a title.
        Title id can also be a reserve id.

        :param title_id: A unique id that identifies the content.
        :return:
        """
        params = self.default_params()
        params.update(kwargs)
        return self.make_request(f"media/{title_id}", params=params)

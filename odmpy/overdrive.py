import logging
from typing import Optional
from urllib.parse import urljoin

import requests

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
        self.logger = logging.getLogger(__name__)
        self.user_agent = kwargs.pop("user_agent", USER_AGENT)
        self.timeout = kwargs.pop("timeout", 10)
        self.session = kwargs.pop("session", None) or requests.Session()

    def default_headers(self) -> dict:
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

    def default_params(self) -> dict:
        """
        Default set of GET request parameters.

        :param paging:
        :return:
        """
        params = {"x-client-id": CLIENT_ID}
        return params

    def make_request(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        headers: Optional[dict] = None,
        method: Optional[str] = None,
    ):
        """
        Sends an API request.

        :param endpoint: Relative path to endpoint
        :param params: URL query parameters
        :param data: POST data parameters
        :param method: HTTP method, e.g. 'PUT'
        :param headers: Custom headers
        :return: Union[List, dict, str]
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

    def media(self, title_id: str, **kwargs) -> dict:
        """
        Retrieve a title.
        Title id can also be a reserve id.

        :param title_id: A unique id that identifies the content.
        :return:
        """
        params = self.default_params()
        params.update(kwargs)
        return self.make_request(f"media/{title_id}", params=params)

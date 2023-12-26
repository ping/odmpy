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
from http import HTTPStatus

import requests as requests

#
# For use with LibbyClient
#


class ClientError(Exception):
    """Generic error class, catch-all for most client issues."""

    def __init__(
        self,
        msg: str,
        http_status: int = 0,
        error_response: str = "",
    ):
        self.http_status = http_status or 0
        self.error_response = error_response
        try:
            self.error_response_obj = json.loads(self.error_response)
        except ValueError:
            self.error_response_obj = {}
        super(ClientError, self).__init__(msg)

    @property
    def msg(self):
        return self.args[0]

    def __str__(self):
        return (
            f"<{type(self).__module__}.{type(self).__name__}; http_status={self.http_status}, "
            f"msg='{self.msg}', error_response='{self.error_response}''>"
        )


class ClientConnectionError(ClientError):
    """Connection error"""


class ClientTimeoutError(ClientError):
    """Timeout error"""


class ClientBadRequestError(ClientError):
    """Raised when an HTTP 400 response is received."""


class ErrorHandler(object):
    @staticmethod
    def process(http_err: requests.HTTPError) -> None:
        """
        Try to process an HTTP error from the api appropriately.

        :param http_err: requests.HTTPError instance
        :raises ClientError:
        :return:
        """
        # json response
        if http_err.response is not None:
            if hasattr(http_err.response, "json") and callable(http_err.response.json):
                if (
                    http_err.response.status_code == HTTPStatus.BAD_REQUEST
                    and http_err.response.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                ):
                    error = http_err.response.json()
                    if error.get("result", "") == "upstream_failure":
                        upstream = error.get("upstream", {})
                        if upstream:
                            raise ClientBadRequestError(
                                msg=f'{upstream.get("userExplanation", "")} [errorcode: {upstream.get("errorCode", "")}]',
                                http_status=http_err.response.status_code,
                                error_response=http_err.response.text,
                            ) from http_err

                        raise ClientBadRequestError(
                            msg=str(error),
                            http_status=http_err.response.status_code,
                            error_response=http_err.response.text,
                        ) from http_err

                # final fallback
                raise ClientError(
                    msg=str(http_err),
                    http_status=http_err.response.status_code,
                    error_response=http_err.response.text,
                ) from http_err

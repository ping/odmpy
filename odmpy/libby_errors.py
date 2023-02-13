import json
from http import HTTPStatus

import requests as requests


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
        Try to process a HTTP error from the api appropriately.

        :param http_err: requests.HTTPError instance
        :raises ClientError:
        :return:
        """
        # json response
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

import json
import logging
import os
import platform
import shutil
import sys
import unittest
import warnings
from http.client import HTTPConnection
from pathlib import Path

test_logger = logging.getLogger(__name__)
test_logger.setLevel(logging.WARNING)
requests_logger = logging.getLogger("urllib3")
requests_logger.setLevel(logging.WARNING)
requests_logger.propagate = True

is_windows = os.name == "nt" or platform.system().lower() == "windows"

# detect if running on CI
is_on_ci = False
try:
    # https://docs.github.com/en/actions/learn-github-actions/variables#default-environment-variables
    _ = os.environ["CI"]
    is_on_ci = True
except KeyError:
    pass


class BaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        warnings.filterwarnings(
            action="ignore", message="unclosed", category=ResourceWarning
        )
        self.test_data_dir = Path(__file__).absolute().parent.joinpath("data")
        self.test_downloads_dir = self.test_data_dir.joinpath("downloads")
        if not self.test_downloads_dir.exists():
            self.test_downloads_dir.mkdir(parents=True, exist_ok=True)

        # disable color output
        os.environ["NO_COLOR"] = "1"

        self.logger = test_logger
        # hijack unittest -v arg to toggle log verbosity in test
        self.is_verbose = "-vv" in sys.argv
        if self.is_verbose:
            self.logger.setLevel(logging.DEBUG)
            requests_logger.setLevel(logging.DEBUG)
            HTTPConnection.debuglevel = 1
            logging.basicConfig(stream=sys.stdout)

    def tearDown(self) -> None:
        del os.environ["NO_COLOR"]
        if self.test_downloads_dir.exists():
            shutil.rmtree(self.test_downloads_dir, ignore_errors=True)

    def _generate_fake_settings(self) -> Path:
        """
        Generate fake settings file for odmpy/libby.

        :return:
        """
        settings_folder = self.test_downloads_dir.joinpath("settings")
        if not settings_folder.exists():
            settings_folder.mkdir(parents=True, exist_ok=True)

        # generate fake settings
        with settings_folder.joinpath("libby.json").open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "chip": "12345",
                    "identity": "abcdefgh",
                    "syncable": False,
                    "primary": True,
                    "__libby_sync_code": "12345678",
                },
                f,
            )
        return settings_folder

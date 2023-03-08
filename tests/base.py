import logging
import os
import shutil
import sys
import unittest
import warnings
from http.client import HTTPConnection

test_logger = logging.getLogger(__name__)
test_logger.setLevel(logging.WARNING)
requests_logger = logging.getLogger("urllib3")
requests_logger.setLevel(logging.WARNING)
requests_logger.propagate = True


class BaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        warnings.filterwarnings(
            action="ignore", message="unclosed", category=ResourceWarning
        )
        self.test_data_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data"
        )
        self.test_downloads_dir = os.path.join(self.test_data_dir, "downloads")
        if not os.path.isdir(self.test_downloads_dir):
            os.makedirs(self.test_downloads_dir)

        self.logger = test_logger
        # hijack unittest -v arg to toggle log verbosity in test
        self.is_verbose = "-vv" in sys.argv
        if self.is_verbose:
            self.logger.setLevel(logging.DEBUG)
            requests_logger.setLevel(logging.DEBUG)
            HTTPConnection.debuglevel = 1
            logging.basicConfig(stream=sys.stdout)

    def tearDown(self) -> None:
        if os.path.isdir(self.test_downloads_dir):
            shutil.rmtree(self.test_downloads_dir, ignore_errors=True)

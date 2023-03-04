import logging
import sys
import unittest
from http.client import HTTPConnection

from odmpy.overdrive import OverDriveClient

test_logger = logging.getLogger(__name__)
test_logger.setLevel(logging.WARNING)
client_logger = logging.getLogger(OverDriveClient.__module__)
client_logger.setLevel(logging.WARNING)
requests_logger = logging.getLogger("urllib3")
requests_logger.setLevel(logging.WARNING)
requests_logger.propagate = True


class OverDriveClientTests(unittest.TestCase):
    def setUp(self):
        self.logger = test_logger
        # hijack unittest -v arg to toggle log verbosity in test
        is_verbose = "-vv" in sys.argv
        if is_verbose:
            self.logger.setLevel(logging.DEBUG)
            client_logger.setLevel(logging.DEBUG)
            requests_logger.setLevel(logging.DEBUG)
            HTTPConnection.debuglevel = 1
            logging.basicConfig(stream=sys.stdout)

        self.client = OverDriveClient(retry=1)

    def tearDown(self) -> None:
        self.client.session.close()

    def test_media(self):
        item = self.client.media("284716")
        for k in (
            "id",
            "title",
            "sortTitle",
            "description",
            "fullDescription",
            "shortDescription",
            "publishDate",
            "type",
            "formats",
            "covers",
            "languages",
            "creators",
            "subjects",
            "starRating",
            "starRatingCount",
            "unitsSold",
            "popularity",
        ):
            self.assertIn(k, item, msg=f'"{k}" not found')

    def test_media_bulk(self):
        items = self.client.media_bulk(["284716", "5704038"])
        self.assertEqual(len(items), 2)
        for item in items:
            for k in (
                "id",
                "title",
                "sortTitle",
                "description",
                "fullDescription",
                "shortDescription",
                "publishDate",
                "type",
                "formats",
                "covers",
                "languages",
                "creators",
                "subjects",
                "starRating",
                "starRatingCount",
                "unitsSold",
                "popularity",
            ):
                self.assertIn(k, item, msg=f'"{k}" not found')

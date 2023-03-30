import logging

from odmpy.overdrive import OverDriveClient
from tests.base import BaseTestCase

test_logger = logging.getLogger(__name__)
test_logger.setLevel(logging.WARNING)
client_logger = logging.getLogger(OverDriveClient.__module__)
client_logger.setLevel(logging.WARNING)
requests_logger = logging.getLogger("urllib3")
requests_logger.setLevel(logging.WARNING)
requests_logger.propagate = True


class OverDriveClientTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client = OverDriveClient(retry=1)

    def tearDown(self) -> None:
        super().tearDown()
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
            with self.subTest(key=k):
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
                with self.subTest(key=k):
                    self.assertIn(k, item, msg=f'"{k}" not found')

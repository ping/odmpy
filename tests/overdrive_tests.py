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

    def test_library(self):
        for library_key in ("lapl", "ocpl"):
            with self.subTest(library_key=library_key):
                library = self.client.library(library_key)
                for k in (
                    "recommendToLibraryEnabled",
                    "lastModifiedDate",
                    "allowAnonymousSampling",
                    "allowDeepSearch",
                    "isDemo",
                    "areLuckyDayTitlesAllocated",
                    "canAddLibrariesInSora",
                    "isLuckyDayEnabled",
                    "isLexisNexis",
                    "isAuroraEnabled",
                    "isInstantAccessEnabled",
                    "hasAdvantageAccounts",
                    "isAutocompleteEnabled",
                    "allowRecommendToLibrary",
                    "isConsortium",
                    "accessId",
                    "websiteId",
                    "accounts",
                    "settings",
                    "links",
                    "messages",
                    "defaultLanguage",
                    "supportedLanguages",
                    "formats",
                    "enabledPlatforms",
                    "visitableLibraries",
                    "luckyDayPreferredLendingPeriods",
                    "visitorsHaveLowerHoldPriority",
                    "visitorsCanRecommendTitles",
                    "visitorsCanPlaceHolds",
                    "isReadingHistoryEnabled",
                    "parentCRAccessId",
                    "showcaseTarget",
                    "type",
                    "status",
                    "name",
                    "fulfillmentId",
                    "visitorKey",
                    "preferredKey",
                    "id",
                ):
                    with self.subTest(key=k):
                        self.assertIn(k, library, msg=f'"{k}" not found')

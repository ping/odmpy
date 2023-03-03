import logging
import os
import sys
import unittest
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from http.client import HTTPConnection

from odmpy.libby import (
    LibbyClient,
    parse_toc,
    merge_toc,
    ChapterMarker,
    parse_part_path,
    LibbyFormats,
)

test_logger = logging.getLogger(__name__)
test_logger.setLevel(logging.WARNING)
requests_logger = logging.getLogger("urllib3")
requests_logger.setLevel(logging.WARNING)
requests_logger.propagate = True


class LibbyClientTests(unittest.TestCase):
    def setUp(self):
        self.logger = test_logger
        # hijack unittest -v arg to toggle log verbosity in test
        is_verbose = "-vv" in sys.argv
        if is_verbose:
            self.logger.setLevel(logging.DEBUG)
            requests_logger.setLevel(logging.DEBUG)
            HTTPConnection.debuglevel = 1
            logging.basicConfig(stream=sys.stdout)

        try:
            token = os.environ["LIBBY_TEST_TOKEN"]
            self.client = LibbyClient(
                identity_token=token,
                logger=self.logger,
                max_retries=1,
                timeout=15,
            )
        except KeyError:
            self.client = LibbyClient(
                settings_folder="./odmpy_settings",
                logger=self.logger,
                max_retries=1,
                timeout=15,
            )

    def tearDown(self) -> None:
        self.client.libby_session.close()

    def test_parse_part_path(self):
        marker = parse_part_path(
            "Test", "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part01.mp3"
        )
        self.assertEqual(marker.title, "Test")
        self.assertEqual(marker.start_second, 0)
        self.assertEqual(
            marker.part_name, "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part01.mp3"
        )

        marker = parse_part_path(
            "Test", "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part01.mp3#123"
        )
        self.assertEqual(marker.title, "Test")
        self.assertEqual(marker.start_second, 123)
        self.assertEqual(
            marker.part_name, "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part01.mp3"
        )

        marker = parse_part_path(
            "Test", "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part01.mp3#123.456"
        )
        self.assertEqual(marker.title, "Test")
        self.assertEqual(marker.start_second, 123.456)
        self.assertEqual(
            marker.part_name, "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part01.mp3"
        )

    def test_parse_toc(self):
        base_url = "http://localhost/"
        toc = [
            {
                "title": "Chapter 1",
                "path": "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part01.mp3",
                "contents": [
                    {
                        "title": "Chapter 1 (34:29)",
                        "path": "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part01.mp3#2069",
                    }
                ],
            },
            {
                "title": "Chapter 2",
                "path": "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part02.mp3",
                "contents": [
                    {
                        "title": "Chapter 2 (00:00)",
                        "path": "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part03.mp3",
                    },
                    {
                        "title": "Chapter 2 (08:18)",
                        "path": "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part03.mp3#498",
                    },
                ],
            },
            {
                "title": "Chapter 3",
                "path": "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part03.mp3#2140",
            },
            {
                "title": "Chapter 4",
                "path": "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part03.mp3#3000",
            },
        ]
        spine = [
            {
                "path": "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part01.mp3?cmpt=___",
                "audio-duration": 3600,
                "-odread-spine-position": 0,
                "-odread-file-bytes": 100000,
                "-odread-original-path": "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part01.mp3",
            },
            {
                "path": "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part02.mp3?cmpt=___",
                "audio-duration": 3660,
                "-odread-spine-position": 1,
                "-odread-file-bytes": 200000,
                "-odread-original-path": "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part02.mp3",
            },
            {
                "path": "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part03.mp3?cmpt=___",
                "audio-duration": 3720,
                "-odread-spine-position": 2,
                "-odread-file-bytes": 300000,
                "-odread-original-path": "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part03.mp3",
            },
        ]
        expected_result = OrderedDict(
            {
                "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part01.mp3": {
                    "url": "http://localhost/{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part01.mp3?cmpt=___",
                    "audio-duration": 3600,
                    "file-length": 100000,
                    "spine-position": 0,
                    "chapters": [
                        ChapterMarker(
                            title="Chapter 1",
                            part_name="{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part01.mp3",
                            start_second=0,
                            end_second=3600,
                        ),
                    ],
                },
                "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part02.mp3": {
                    "url": "http://localhost/{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part02.mp3?cmpt=___",
                    "audio-duration": 3660,
                    "file-length": 200000,
                    "spine-position": 1,
                    "chapters": [
                        ChapterMarker(
                            title="Chapter 2",
                            part_name="{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part02.mp3",
                            start_second=0,
                            end_second=3660,
                        ),
                    ],
                },
                "{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part03.mp3": {
                    "url": "http://localhost/{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part03.mp3?cmpt=___",
                    "audio-duration": 3720,
                    "file-length": 300000,
                    "spine-position": 2,
                    "chapters": [
                        ChapterMarker(
                            title="Chapter 2",
                            part_name="{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part03.mp3",
                            start_second=0,
                            end_second=2140,
                        ),
                        ChapterMarker(
                            title="Chapter 3",
                            part_name="{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part03.mp3",
                            start_second=2140,
                            end_second=3000,
                        ),
                        ChapterMarker(
                            title="Chapter 4",
                            part_name="{AAAAAAAA-BBBB-CCCC-9999-ABCDEF123456}Fmt425-Part03.mp3",
                            start_second=3000,
                            end_second=3720,
                        ),
                    ],
                },
            }
        )
        expected_merged_result = [
            ChapterMarker(
                title="Chapter 1",
                part_name="",
                start_second=0,
                end_second=3600,
            ),
            ChapterMarker(
                title="Chapter 2",
                part_name="",
                start_second=3600,
                end_second=9400,
            ),
            ChapterMarker(
                title="Chapter 3",
                part_name="",
                start_second=9400,
                end_second=10260,
            ),
            ChapterMarker(
                title="Chapter 4",
                part_name="",
                start_second=10260,
                end_second=10980,
            ),
        ]

        self.assertEqual(parse_toc(base_url, toc, spine), expected_result)
        self.assertEqual(
            merge_toc(parse_toc(base_url, toc, spine)), expected_merged_result
        )

    def test_loans(self):
        if not self.client.get_token():
            self.skipTest("Libby not logged in.")
            return

        formats_keys = {
            "audiobook": [
                "firstCreatorName",
                "firstCreatorSortName",
                "publishDate",
                "publishDateText",
            ],
            "ebook": [
                "firstCreatorName",
                "firstCreatorSortName",
                # "publishDate",
                # "publishDateText",
            ],
            "magazine": [
                "parentMagazineTitleId",
                "pages",
                "frequency",
                "edition",
                # "publishDate",
                "publishDateText",
            ],
        }
        res = self.client.get_loans()
        for loan in res:
            for k in (
                "id",
                "title",
                "sortTitle",
                "checkoutDate",
                "expireDate",
                "expires",
                "renewableOn",
                "title",
                "checkoutId",
                "formats",
                "covers",
                "isLuckyDayCheckout",
                "isHoldable",
                "isOwned",
                "isAssigned",
                "isBundledChild",
                "isFormatLockedIn",
                "isReturnable",
                "subjects",
                "type",
                "publisherAccount",
                "firstCreatorId",
                "reserveId",
                "websiteId",
                "cardId",
                "ownedCopies",
                "availableCopies",
                "holdsCount",
                "availabilityType",
                "sample",
                "bundledContent",
                "overDriveFormat",
                "otherFormats",
                "readiverseFormat",
                "constraints",
                "privateAccountId",
            ):
                self.assertIn(k, loan, msg=f"'{k}' not found in loan")

            self.assertIn(loan["type"]["id"], ("audiobook", "ebook", "magazine"))
            self.assertIn(loan["type"]["name"], ("Audiobook", "eBook", "Magazine"))

            for k in formats_keys.get(loan["type"]["id"], []):
                self.assertIn(
                    k, loan, msg=f'"{k}" not found in {loan["type"]["id"]} loan'
                )

    def test_holds(self):
        if not self.client.get_token():
            self.skipTest("Libby not logged in.")
            return

        res = self.client.get_holds()
        for hold in res:
            for k in (
                "id",
                "title",
                "sortTitle",
                "title",
                "formats",
                "covers",
                "isHoldable",
                "isOwned",
                "subjects",
                "type",
                "publisherAccount",
                "firstCreatorId",
                "cardId",
                "ownedCopies",
                "availableCopies",
                "holdsCount",
                # "sample",
                # "overDriveFormat",
                "otherFormats",
                # "readiverseFormat",
            ):
                self.assertIn(k, hold, msg=f"'{k}' not found in hold")

            for k in (
                "placedDate",
                "isFastlane",
                "isAvailable",
                "isPreReleaseTitle",
                "suspensionFlag",
                "autoRenewFlag",
                "autoCheckoutFlag",
                "holdListPosition",
                "holdsCount",
                "redeliveriesRequestedCount",
                "redeliveriesAutomatedCount",
                # "patronHoldsRatio",
                # "estimatedWaitDays",
                "holdsRatio",
                "estimatedReleaseDate",
            ):
                self.assertIn(k, hold, msg=f"'{k}' not found in hold")

    def test_is_renewable(self):
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        loan = {
            "renewableOn": (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        self.assertFalse(LibbyClient.is_renewable(loan))

        loan = {
            "renewableOn": (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        self.assertTrue(LibbyClient.is_renewable(loan))

    @unittest.skip("May get blocked by libby servers during CI/CD")
    def test_unauthed_libby_client(self):
        client = LibbyClient(logger=self.logger)
        try:
            chip_res = client.get_chip(auto_save=False)
            for k in ("chip", "identity", "syncable", "primary"):
                self.assertIn(k, chip_res)
        finally:
            client.libby_session.close()  # avoid ResourceWarning

        client = LibbyClient(logger=self.logger, identity_token=chip_res["identity"])
        try:
            res = client.sync()
            for k in ("cards", "summary"):
                self.assertFalse(res.get(k))
        finally:
            client.libby_session.close()  # avoid ResourceWarning

    def test_alt_authed_libby_client(self):
        token = None
        try:
            token = os.environ["LIBBY_TEST_TOKEN"]
        except KeyError:
            self.skipTest("No libby token setup in environ")

        client = LibbyClient(logger=self.logger, identity_token=token)
        try:
            res = client.sync()
            for k in ("cards", "summary"):
                self.assertTrue(res.get(k))
            with self.assertRaises(ValueError) as _:
                client.save_settings({"identity": token})
        finally:
            client.libby_session.close()  # avoid ResourceWarning

    def test_string_enum(self):
        self.assertEqual(f"{LibbyFormats.AudioBookMP3}", "audiobook-mp3")
        self.assertEqual(str(LibbyFormats.AudioBookMP3), "audiobook-mp3")
        self.assertEqual("" + LibbyFormats.AudioBookMP3, "audiobook-mp3")
        self.assertEqual("%s" % LibbyFormats.AudioBookMP3, "audiobook-mp3")
        self.assertEqual("{}".format(LibbyFormats.AudioBookMP3), "audiobook-mp3")
        self.assertEqual(LibbyFormats.AudioBookMP3.value, "audiobook-mp3")
        self.assertEqual(LibbyFormats.AudioBookMP3, "audiobook-mp3")
        self.assertEqual(LibbyFormats.AudioBookMP3, LibbyFormats("audiobook-mp3"))

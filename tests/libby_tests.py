import logging
import os
import unittest
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from http import HTTPStatus

import responses
from responses import matchers

from odmpy.libby import (
    LibbyClient,
    parse_toc,
    merge_toc,
    ChapterMarker,
    parse_part_path,
    LibbyFormats,
)
from odmpy.libby_errors import ClientBadRequestError, ClientError
from tests.base import BaseTestCase, is_on_ci

test_logger = logging.getLogger(__name__)
test_logger.setLevel(logging.WARNING)
requests_logger = logging.getLogger("urllib3")
requests_logger.setLevel(logging.WARNING)
requests_logger.propagate = True


class LibbyClientTests(BaseTestCase):
    def setUp(self):
        super().setUp()
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
        super().tearDown()
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
                with self.subTest(key=k):
                    self.assertIn(k, loan, msg=f"'{k}' not found in loan")

            self.assertIn(loan["type"]["id"], ("audiobook", "ebook", "magazine"))
            self.assertIn(loan["type"]["name"], ("Audiobook", "eBook", "Magazine"))

            for k in formats_keys.get(loan["type"]["id"], []):
                with self.subTest(key=k):
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
                with self.subTest(key=k):
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
                # "holdsRatio",     # not present in if there are multi-holds per title
                "estimatedReleaseDate",
            ):
                with self.subTest(key=k):
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

    @unittest.skipIf(is_on_ci, "May get blocked by libby servers during CI/CD")
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

    @responses.activate
    def test_libby_error_badrequest(self):
        err_result = {
            "result": "upstream_failure",
            "upstream": {
                "userExplanation": "TestUserExplanation",
                "errorCode": "99999",
            },
        }
        responses.get(
            "https://sentry-read.svc.overdrive.com/chip/sync",
            content_type="application/json",
            status=HTTPStatus.BAD_REQUEST,
            json=err_result,
        )
        client = LibbyClient(logger=self.logger, identity_token=".")
        with self.assertRaises(ClientBadRequestError) as context:
            _ = client.sync()
        self.assertEqual(
            context.exception.msg, "TestUserExplanation [errorcode: 99999]"
        )
        self.assertEqual(context.exception.http_status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(context.exception.error_response_obj, err_result)

    @responses.activate
    def test_libby_error_forbidden(self):
        responses.get(
            "https://sentry-read.svc.overdrive.com/chip/sync",
            status=HTTPStatus.FORBIDDEN,
            body="",
        )
        client = LibbyClient(logger=self.logger, identity_token=".")
        with self.assertRaises(ClientError) as context:
            _ = client.sync()
        self.assertEqual(
            context.exception.msg,
            "403 Client Error: Forbidden for url: https://sentry-read.svc.overdrive.com/chip/sync",
        )
        self.assertEqual(context.exception.http_status, HTTPStatus.FORBIDDEN)
        self.assertEqual(context.exception.error_response, "")

    @responses.activate
    def test_libby_borrow_hold(self):
        hold = {"id": "123456", "type": {"id": "ebook"}, "cardId": "99999"}
        responses.post(
            f'https://sentry-read.svc.overdrive.com/card/{hold["cardId"]}/loan/{hold["id"]}',
            json={},
            match=[
                matchers.json_params_matcher(
                    {
                        "period": 21,
                        "units": "days",
                        "lucky_day": None,
                        "title_format": hold["type"]["id"],
                    }
                )
            ],
        )
        client = LibbyClient(logger=self.logger, identity_token=".")
        client.borrow_hold(hold)

    @responses.activate
    def test_libby_link_card(self):
        website_id = "78"
        username = "12345678"
        password = "1234"
        responses.post(
            f"https://sentry-read.svc.overdrive.com/auth/link/{website_id}",
            json={},
            match=[
                matchers.json_params_matcher(
                    {"ils": "default", "username": username, "password": password}
                )
            ],
        )
        client = LibbyClient(logger=self.logger, identity_token=".")
        client.link_card(website_id, username, password)

    @responses.activate
    def test_libby_update_card_name(self):
        card_id = "12345678"
        card_name = "Test"
        responses.put(
            f"https://sentry-read.svc.overdrive.com/card/{card_id}",
            json={"message": card_name},
            match=[matchers.query_param_matcher({"card_name": card_name})],
        )
        client = LibbyClient(logger=self.logger, identity_token=".")
        client.update_card_name(card_id, card_name)

    def test_libby_auth_form(self):
        client = LibbyClient(logger=self.logger, identity_token=".")
        for website_id in ("243",):
            with self.subTest(website_id=website_id):
                lib_auth_form = client.auth_form(website_id)
                for k in (
                    "websiteId",
                    "forms",
                    "pinResetForms",
                    "ghost",
                    "features",
                    "captcha",
                ):
                    with self.subTest(key=k):
                        self.assertIn(k, lib_auth_form, msg=f'"{k}" not found')
                self.assertEqual(int(website_id), lib_auth_form["websiteId"])
                self.assertTrue(lib_auth_form["forms"])
                for form in lib_auth_form["forms"]:
                    for k in ("type", "ilsName", "local"):
                        with self.subTest(key=k):
                            self.assertIn(k, form, msg=f'"{k}" not found in form')
                    form_variables = form["local"]
                    for k in ("username", "password"):
                        with self.subTest(key=k):
                            self.assertTrue(form_variables.get(k))
                            self.assertIn("enabled", form_variables[k])

    def test_has_chip(self):
        client = LibbyClient(logger=self.logger, identity_token=".")
        self.assertFalse(client.has_chip())

        settings_folder = self._generate_fake_settings()
        client = LibbyClient(settings_folder=str(settings_folder))
        self.assertTrue(client.has_chip())

    def test_has_sync_code(self):
        settings_folder = self._generate_fake_settings()
        client = LibbyClient(settings_folder=str(settings_folder))
        self.assertTrue(client.has_sync_code())

    def test_string_enum(self):
        self.assertEqual(f"{LibbyFormats.AudioBookMP3}", "audiobook-mp3")
        self.assertEqual(str(LibbyFormats.AudioBookMP3), "audiobook-mp3")
        self.assertEqual("" + LibbyFormats.AudioBookMP3, "audiobook-mp3")
        self.assertEqual("%s" % LibbyFormats.AudioBookMP3, "audiobook-mp3")
        self.assertEqual("{}".format(LibbyFormats.AudioBookMP3), "audiobook-mp3")
        self.assertEqual(LibbyFormats.AudioBookMP3.value, "audiobook-mp3")
        self.assertEqual(LibbyFormats.AudioBookMP3, "audiobook-mp3")
        self.assertEqual(LibbyFormats.AudioBookMP3, LibbyFormats("audiobook-mp3"))

    def test_get_loan_format(self):
        with self.assertRaises(ValueError) as context:
            LibbyClient.get_loan_format(
                {
                    "formats": [
                        {"id": LibbyFormats.EBookKindle, "isLockedIn": True},
                        {"id": LibbyFormats.EBookOverdrive, "isLockedIn": False},
                        {"id": LibbyFormats.EBookEPubAdobe, "isLockedIn": False},
                    ]
                }
            )
        self.assertEqual(
            str(context.exception),
            f'Loan is locked to a non-downloadable format "{LibbyFormats.EBookKindle}"',
        )
        self.assertEqual(
            LibbyClient.get_loan_format(
                {
                    "formats": [
                        {"id": LibbyFormats.EBookKindle, "isLockedIn": False},
                        {"id": LibbyFormats.EBookOverdrive, "isLockedIn": False},
                        {"id": LibbyFormats.EBookEPubAdobe, "isLockedIn": True},
                        {"id": LibbyFormats.EBookEPubOpen, "isLockedIn": False},
                    ]
                }
            ),
            LibbyFormats.EBookEPubAdobe,
        )
        self.assertEqual(
            LibbyClient.get_loan_format(
                {
                    "formats": [
                        {"id": LibbyFormats.EBookKindle, "isLockedIn": False},
                        {"id": LibbyFormats.EBookOverdrive, "isLockedIn": False},
                        {"id": LibbyFormats.EBookEPubAdobe, "isLockedIn": False},
                    ]
                }
            ),
            LibbyFormats.EBookEPubAdobe,
        )
        self.assertEqual(
            LibbyClient.get_loan_format(
                {
                    "formats": [
                        {"id": LibbyFormats.EBookKindle, "isLockedIn": False},
                        {"id": LibbyFormats.EBookOverdrive, "isLockedIn": False},
                        {"id": LibbyFormats.EBookEPubAdobe, "isLockedIn": False},
                        {"id": LibbyFormats.EBookEPubOpen, "isLockedIn": False},
                    ]
                }
            ),
            LibbyFormats.EBookEPubOpen,
        )
        self.assertEqual(
            LibbyClient.get_loan_format(
                {
                    "formats": [
                        {"id": LibbyFormats.EBookKindle, "isLockedIn": False},
                        {"id": LibbyFormats.EBookOverdrive, "isLockedIn": False},
                        {"id": LibbyFormats.EBookEPubAdobe, "isLockedIn": False},
                        {"id": LibbyFormats.EBookEPubOpen, "isLockedIn": False},
                    ]
                },
                prefer_open_format=False,
            ),
            LibbyFormats.EBookEPubAdobe,
        )
        self.assertEqual(
            LibbyClient.get_loan_format(
                {
                    "formats": [
                        {"id": LibbyFormats.EBookOverdrive, "isLockedIn": False},
                        {"id": LibbyFormats.EBookPDFAdobe, "isLockedIn": False},
                        {"id": LibbyFormats.EBookPDFOpen, "isLockedIn": False},
                    ]
                }
            ),
            LibbyFormats.EBookPDFOpen,
        )
        self.assertEqual(
            LibbyClient.get_loan_format(
                {
                    "formats": [
                        {"id": LibbyFormats.EBookOverdrive, "isLockedIn": False},
                        {"id": LibbyFormats.EBookPDFAdobe, "isLockedIn": False},
                        {"id": LibbyFormats.EBookPDFOpen, "isLockedIn": False},
                    ]
                },
                prefer_open_format=False,
            ),
            LibbyFormats.EBookPDFAdobe,
        )
        self.assertEqual(
            LibbyClient.get_loan_format(
                {
                    "formats": [
                        {"id": LibbyFormats.EBookOverdrive, "isLockedIn": False},
                        {"id": LibbyFormats.EBookPDFAdobe, "isLockedIn": False},
                    ]
                }
            ),
            LibbyFormats.EBookPDFAdobe,
        )
        self.assertEqual(
            LibbyClient.get_loan_format(
                {
                    "formats": [
                        {"id": LibbyFormats.AudioBookMP3, "isLockedIn": False},
                        {"id": LibbyFormats.AudioBookOverDrive, "isLockedIn": False},
                    ]
                }
            ),
            LibbyFormats.AudioBookMP3,
        )
        self.assertEqual(
            LibbyClient.get_loan_format(
                {
                    "formats": [
                        {"id": LibbyFormats.MagazineOverDrive, "isLockedIn": False},
                    ]
                }
            ),
            LibbyFormats.MagazineOverDrive,
        )

    def test_parse_datetime(self):
        for value in (
            "2017-06-06T04:00:00Z",  # estimatedReleaseDate, publishDate
            "2023-08-10T23:00:01.000Z",  # expireDate
            "2023-07-31T08:00:01.000+00:00",  # placedDate
            "2023-08-01T10:00:01.000Z",  # placedDate
            "2023-09-14T07:20:30+00:00",  # expireDate
            "05/30/2023",
        ):
            with self.subTest(value=value):
                LibbyClient.parse_datetime(value)

        with self.assertRaises(ValueError):
            LibbyClient.parse_datetime("2023/05/30 23:01:14")

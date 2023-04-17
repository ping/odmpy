# Copyright (c) 2020 https://github.com/ping
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

import json
from http import HTTPStatus

import responses
from lxml import etree  # type: ignore[import]

from odmpy.errors import OdmpyRuntimeError
from odmpy.odm import run
from odmpy.overdrive import OverDriveClient
from .base import BaseTestCase
from .data import (
    get_expected_result,
)


# [i] USE run_tests.sh


class OdmpyTests(BaseTestCase):
    def setUp(self):
        super().setUp()

        # test1.odm - book with ascii meta
        # test2.odm - book with non-ascii meta
        # test3.odm - Issue using mutagen, ref #17
        # test4.odm - HTML entities decoding, ref #19
        self.test_odms = ["test1.odm", "test2.odm", "test3.odm", "test4.odm"]

    def test_info(self):
        """
        `odmpy info test.odm`
        """
        for test_odm_file in self.test_odms:
            with self.subTest(odm=test_odm_file):
                expected_file = self.test_data_dir.joinpath(
                    f"{test_odm_file}.info.expected.txt"
                )
                with self.assertLogs(run.__module__, level="INFO") as context:
                    run(
                        [
                            "--noversioncheck",
                            "info",
                            str(self.test_data_dir.joinpath(test_odm_file)),
                        ],
                        be_quiet=True,
                    )
                with expected_file.open("r", encoding="utf-8") as expected:
                    self.assertEqual(
                        "\n".join([r.msg for r in context.records]) + "\n",
                        expected.read(),
                    )

    def test_info_json(self):
        """
        `odmpy info test.odm` --format json`
        """
        for test_odm_file in self.test_odms:
            with self.subTest(odm=test_odm_file):
                with self.assertLogs(run.__module__, level="INFO") as context:
                    run(
                        [
                            "--noversioncheck",
                            "info",
                            str(self.test_data_dir.joinpath(test_odm_file)),
                            "--format",
                            "json",
                        ],
                        be_quiet=True,
                    )
                info = json.loads("\n".join([r.msg for r in context.records]))
                for tag in [
                    "title",
                    "creators",
                    "publisher",
                    "subjects",
                    "languages",
                    "description",
                    "total_duration",
                ]:
                    with self.subTest(tag=tag):
                        self.assertTrue(
                            info.get(tag), msg="'{}' is not set".format(tag)
                        )

    def _setup_common_responses(self):
        with self.test_data_dir.joinpath("audiobook", "cover.jpg").open("rb") as c:
            img_bytes = c.read()
            # cover from OD API
            responses.get(
                "https://ic.od-cdn.com/resize?type=auto&width=510&height=510&force=true&quality=80&url=%2Fodmpy%2Ftest_data%2Fcover.jpg",
                content_type="image/jpeg",
                body=img_bytes,
            )
        responses.get(
            "https://ic.od-cdn.com/resize?type=auto&width=510&height=510&force=true&quality=80&url=%2Fodmpy%2Ftest_data%2Fcover_NOTFOUND.jpg",
            status=404,
        )
        # responses.add_passthru("https://ping.github.io/odmpy/test_data/")
        odm_test_data_dir = self.test_data_dir.joinpath("audiobook", "odm")
        with odm_test_data_dir.joinpath("test.license").open(
            "r", encoding="utf-8"
        ) as license_file:
            responses.get(
                "https://ping.github.io/odmpy/test_data/test.license",
                content_type="application/xml",
                body=license_file.read(),
            )
        for mp3 in (
            "book1/ceremonies_herrick_bk_64kb.mp3",
            "book1/ceremonies_herrick_cjph_64kb.mp3",
            "book1/ceremonies_herrick_gg_64kb.mp3",
            "book3/01_ceremonies_herrick_cjph_64kb.mp3",
        ):
            with odm_test_data_dir.joinpath(mp3).open("rb") as m:
                responses.get(
                    f"https://ping.github.io/odmpy/test_data/{mp3}",
                    content_type="audio/mp3",
                    body=m.read(),
                )
        with odm_test_data_dir.joinpath("media.json").open("r", encoding="utf-8") as m:
            responses.get(
                "https://thunder.api.overdrive.com/v2/media/0fef5121-bb1f-42a5-b62a-d9fded939d50",
                content_type="application/json",
                body=m.read(),
            )
        responses.get(
            "https://ping.github.io/odmpy/test_data/cover_NOTFOUND.jpg",
            status=HTTPStatus.NOT_FOUND,
        )

    @responses.activate
    def test_cover_fail_ref24(self):
        """
        Test for #24 error downloading cover
        """
        self._setup_common_responses()
        test_odm_file = "test_ref24.odm"
        run(
            [
                "--noversioncheck",
                "dl",
                str(self.test_data_dir.joinpath(test_odm_file)),
                "--downloaddir",
                str(self.test_downloads_dir),
                "--keepcover",
                "--hideprogress",
            ],
            be_quiet=True,
        )
        expected_result = get_expected_result(self.test_downloads_dir, test_odm_file)
        self.assertTrue(expected_result.book_folder.is_dir())
        for i in range(1, expected_result.total_parts + 1):
            book_file = expected_result.book_folder.joinpath(
                expected_result.mp3_name_format.format(i)
            )
            self.assertTrue(book_file.exists())
        self.assertFalse(expected_result.book_folder.joinpath("cover.jpg").exists())

    @responses.activate
    def test_opf(self):
        """
        `odmpy dl test.odm --opf`

        Test for #26 opf generation
        """
        self._setup_common_responses()
        test_odm_file = "test1.odm"
        run(
            [
                "--noversioncheck",
                "dl",
                str(self.test_data_dir.joinpath(test_odm_file)),
                "--downloaddir",
                str(self.test_downloads_dir),
                "--keepcover",
                "--opf",
                "--hideprogress",
            ],
            be_quiet=True,
        )
        expected_result = get_expected_result(self.test_downloads_dir, test_odm_file)

        # schema file has been edited to remove the legacy toc attribute for spine
        schema_file = self.test_data_dir.joinpath("opf.schema.xml")
        test_file = expected_result.book_folder.joinpath("ceremonies-for-christmas.opf")
        self.assertTrue(test_file.exists())

        with test_file.open("r", encoding="utf-8") as actual, schema_file.open(
            "r", encoding="utf-8"
        ) as schema:
            # pylint: disable=c-extension-no-member
            actual_opf = etree.parse(actual)
            relaxng = etree.RelaxNG(etree.parse(schema))
            self.assertTrue(relaxng.validate(actual_opf))

            root = actual_opf.getroot()
            metadata = root.find("metadata", root.nsmap)
            self.assertIsNotNone(metadata)

            metadata_nsmap = {k: v for k, v in metadata.nsmap.items() if k}

            overdrive_reserve_identifier = metadata.xpath(
                "//dc:identifier[@opf:scheme='OverDriveReserveId']",
                namespaces=metadata_nsmap,
            )
            self.assertEqual(len(overdrive_reserve_identifier), 1)
            overdrive_reserve_id = overdrive_reserve_identifier[0].text
            self.assertTrue(overdrive_reserve_id)

            od = OverDriveClient()
            try:
                media_info = od.media(overdrive_reserve_id)

                # title
                self.assertEqual(
                    metadata.find("dc:title", metadata_nsmap).text, media_info["title"]
                )
                # language
                self.assertEqual(
                    metadata.find("dc:language", metadata_nsmap).text,
                    media_info["languages"][0]["id"],
                )
                # publisher
                self.assertEqual(
                    metadata.find("dc:publisher", metadata_nsmap).text,
                    media_info["publisher"]["name"],
                )
                # description
                self.assertEqual(
                    metadata.find("dc:description", metadata_nsmap).text,
                    media_info["description"],
                )

                # pub date
                pub_date = metadata.find("dc:date", metadata_nsmap)
                self.assertIsNotNone(pub_date)
                self.assertEqual(
                    pub_date.get(f"{{{metadata_nsmap['opf']}}}event"), "publication"
                )
                self.assertEqual(pub_date.text, media_info["publishDate"])

                # book ID, isbn
                self.assertEqual(
                    metadata.xpath(
                        "//dc:identifier[@id='publication-id']",
                        namespaces=metadata_nsmap,
                    )[0].text,
                    [f for f in media_info["formats"] if f["id"] == "audiobook-mp3"][0][
                        "isbn"
                    ],
                )

                # authors
                authors = metadata.xpath(
                    "//dc:creator[@opf:role='aut']", namespaces=metadata_nsmap
                )
                authors_od = [
                    c for c in media_info["creators"] if c["role"] == "Author"
                ]
                self.assertTrue(len(authors), len(authors_od))
                for author_opf, author_od in zip(authors, authors_od):
                    self.assertEqual(author_opf.text, author_od["name"])
                    self.assertEqual(
                        author_opf.get(f"{{{metadata_nsmap['opf']}}}file-as"),
                        author_od["sortName"],
                    )

                # narrators
                narrators = metadata.xpath(
                    "//dc:creator[@opf:role='nrt']", namespaces=metadata_nsmap
                )
                narrators_od = [
                    c for c in media_info["creators"] if c["role"] == "Narrator"
                ]
                self.assertTrue(len(narrators), len(narrators_od))
                for narrator_opf, narrator_od in zip(narrators, narrators_od):
                    self.assertEqual(narrator_opf.text, narrator_od["name"])
                    self.assertEqual(
                        narrator_opf.get(f"{{{metadata_nsmap['opf']}}}file-as"),
                        narrator_od["sortName"],
                    )

                # manifest
                manifest = root.find("manifest", root.nsmap)
                self.assertIsNotNone(manifest)
                cover_ele = next(
                    iter(
                        [
                            i
                            for i in manifest.findall("item", namespaces=manifest.nsmap)
                            if i.get("id") == "cover"
                        ]
                    ),
                    None,
                )
                self.assertIsNotNone(cover_ele)
                self.assertEqual(cover_ele.get("href"), "cover.jpg")
                self.assertEqual(cover_ele.get("media-type"), "image/jpeg")
                manifest_audio_files = [
                    i
                    for i in manifest.findall("item", namespaces=manifest.nsmap)
                    if i.get("media-type") == "audio/mpeg"
                ]
                self.assertEqual(
                    len(manifest_audio_files),
                    expected_result.total_parts,
                )

                # spine
                spine = root.find("spine", root.nsmap)
                self.assertIsNotNone(spine)
                sprine_audio_files = [
                    i for i in spine.findall("itemref", namespaces=spine.nsmap)
                ]
                self.assertEqual(len(sprine_audio_files), len(manifest_audio_files))

            finally:
                # close this to prevent "ResourceWarning: unclosed socket" error
                od.session.close()

    @responses.activate
    def test_odm_return(self):
        """
        `odmpy ret test.odm`
        """
        responses.get("https://ping.github.io/odmpy/test_data")
        run(
            [
                "--noversioncheck",
                "ret",
                str(self.test_data_dir.joinpath(self.test_odms[0])),
            ],
            be_quiet=True,
        )

    @responses.activate
    def test_odm_return_fail(self):
        """
        `odmpy ret test.odm`
        """
        responses.get(
            "https://ping.github.io/odmpy/test_data", status=HTTPStatus.FORBIDDEN
        )
        with self.assertLogs(run.__module__, level="INFO") as context:
            run(
                [
                    "--noversioncheck",
                    "ret",
                    str(self.test_data_dir.joinpath(self.test_odms[0])),
                ],
                be_quiet=True,
            )
        self.assertIn(
            "Loan is probably already returned.", [r.msg for r in context.records]
        )

    @responses.activate
    def test_odm_return_error(self):
        """
        `odmpy ret test.odm`
        """
        responses.get(
            "https://ping.github.io/odmpy/test_data", status=HTTPStatus.BAD_REQUEST
        )
        with self.assertRaisesRegex(OdmpyRuntimeError, "HTTP error returning odm"):
            run(
                [
                    "--noversioncheck",
                    "ret",
                    str(self.test_data_dir.joinpath(self.test_odms[0])),
                ],
                be_quiet=True,
            )

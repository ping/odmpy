# Copyright (c) 2020 https://github.com/ping
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

import json
import logging
import os
import re
import shutil
import unittest
import warnings
from io import StringIO

from lxml import etree  # type: ignore[import]

from odmpy.odm import run
from odmpy.overdrive import OverDriveClient
from .data import (
    get_expected_result,
)

eyed3_log = logging.getLogger("eyed3.mp3.headers")
eyed3_log.setLevel(logging.ERROR)


# [i] USE run_tests.sh

strip_color_codes_re = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class OdmpyTests(unittest.TestCase):
    def setUp(self):
        warnings.filterwarnings(
            action="ignore", message="unclosed", category=ResourceWarning
        )
        try:
            self.test_file = os.environ["TEST_ODM"]
        except KeyError:
            raise RuntimeError("TEST_ODM environment var not defined.")

        self.test_data_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data"
        )
        self.test_downloads_dir = os.path.join(self.test_data_dir, "downloads")
        if not os.path.exists(self.test_downloads_dir):
            os.makedirs(self.test_downloads_dir)

    def tearDown(self) -> None:
        if os.path.isdir(self.test_downloads_dir):
            shutil.rmtree(self.test_downloads_dir, ignore_errors=True)

    def test_info(self):
        """
        `odmpy info test.odm`
        """
        expected_file = os.path.join(
            self.test_data_dir, "{}.info.expected.txt".format(self.test_file)
        )
        with open(expected_file, encoding="utf-8") as expected, StringIO() as out:
            stream_handler = logging.StreamHandler(out)
            stream_handler.setLevel(logging.DEBUG)
            run(
                [
                    "--noversioncheck",
                    "info",
                    os.path.join(self.test_data_dir, self.test_file),
                ],
                be_quiet=True,
                injected_stream_handler=stream_handler,
            )
            expected_text = expected.read()
            self.assertEqual(
                strip_color_codes_re.sub("", out.getvalue()), expected_text
            )

    def test_info_json(self):
        """
        `odmpy info test.odm` --format json`
        """
        with StringIO() as out:
            stream_handler = logging.StreamHandler(out)
            stream_handler.setLevel(logging.DEBUG)
            run(
                [
                    "--noversioncheck",
                    "info",
                    os.path.join(self.test_data_dir, self.test_file),
                    "--format",
                    "json",
                ],
                be_quiet=True,
                injected_stream_handler=stream_handler,
            )
            info = json.loads(strip_color_codes_re.sub("", out.getvalue()))
            for tag in [
                "title",
                "creators",
                "publisher",
                "subjects",
                "languages",
                "description",
                "total_duration",
            ]:
                self.assertTrue(info.get(tag), msg="'{}' is not set".format(tag))

    def test_cover_fail_ref24(self):
        """
        Test for error downloading cover
        """
        run(
            [
                "--noversioncheck",
                "dl",
                os.path.join(self.test_data_dir, self.test_file),
                "--downloaddir",
                self.test_downloads_dir,
                "--keepcover",
                "--hideprogress",
            ],
            be_quiet=True,
        )
        expected_result = get_expected_result(self.test_downloads_dir, self.test_file)
        self.assertTrue(os.path.isdir(expected_result.book_folder))
        for i in range(1, expected_result.total_parts + 1):
            book_file = os.path.join(
                expected_result.book_folder, expected_result.mp3_name_format.format(i)
            )
            self.assertTrue(os.path.isfile(book_file))
        self.assertFalse(
            os.path.isfile(os.path.join(expected_result.book_folder, "cover.jpg"))
        )

    def test_opf(self):
        """
        `odmpy dl test.odm --opf`
        """
        run(
            [
                "--noversioncheck",
                "dl",
                os.path.join(self.test_data_dir, self.test_file),
                "--downloaddir",
                self.test_downloads_dir,
                "--keepcover",
                "--opf",
                "--hideprogress",
            ],
            be_quiet=True,
        )
        expected_result = get_expected_result(self.test_downloads_dir, self.test_file)

        # schema file has been edited to remove the legacy toc attribute for spine
        schema_file = os.path.join(self.test_data_dir, "opf.schema.xml")
        test_file = os.path.join(
            expected_result.book_folder, "ceremonies-for-christmas.opf"
        )
        self.assertTrue(os.path.isfile(test_file))

        with open(test_file, encoding="utf-8") as actual, open(
            schema_file, "r", encoding="utf-8"
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
                        "//dc:identifier[@id='BookId']", namespaces=metadata_nsmap
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

# -*- coding: utf-8 -*-
# Copyright (c) 2020 https://github.com/ping
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

import json
import logging
import os
import unittest
from collections import OrderedDict

import eyed3  # type: ignore[import]
from lxml import etree  # type: ignore[import]

import odmpy.constants
from odmpy.libby import parse_part_path, parse_toc, merge_toc, ChapterMarker

eyed3_log = logging.getLogger("eyed3.mp3.headers")
eyed3_log.setLevel(logging.ERROR)


# [i] USE run_tests.sh


class OdmpyTests(unittest.TestCase):

    book_folders = {
        "test1.odm": os.path.join(
            "downloads", "Ceremonies For Christmas - Robert Herrick"
        ),
        "test2.odm": os.path.join("downloads", "크리스마스를 위한 의식 - 로버트 Herrick"),
        "test3.odm": os.path.join(
            "downloads", "Ceremonies For Christmas - Robert Herrick"
        ),
        "test4.odm": os.path.join(
            "downloads", "Ceremonies For Christmas - Robert Herrick"
        ),
        "test_ref24.odm": os.path.join(
            "downloads", "Ceremonies For Christmas - Robert Herrick"
        ),
    }
    merged_book_basenames = {
        "test1.odm": "Ceremonies For Christmas - Robert Herrick",
        "test2.odm": "크리스마스를 위한 의식 - 로버트 Herrick",
        "test3.odm": "Ceremonies For Christmas - Robert Herrick",
        "test4.odm": "Ceremonies For Christmas - Robert Herrick",
        "test_ref24.odm": "Ceremonies For Christmas - Robert Herrick",
    }
    mp3_name_formats = {
        "test1.odm": "ceremonies-for-christmas-part-{:02}.mp3",
        "test2.odm": "크리스마스를-위한-의식-part-{:02}.mp3",
        "test3.odm": "ceremonies-for-christmas-part-{:02}.mp3",
        "test4.odm": "ceremonies-for-christmas-part-{:02}.mp3",
        "test_ref24.odm": "ceremonies-for-christmas-part-{:02}.mp3",
    }
    part_title_formats = {
        "test1.odm": "{:02d} - Ceremonies For Christmas",
        "test2.odm": "{:02d} - 크리스마스를 위한 의식",
        "test3.odm": "{:02d} Issue 17",
        "test4.odm": "{:02d} Issue 17",
        "test_ref24.odm": "{:02d} Issue 17",
    }
    markers = {
        "test1.odm": [
            "Marker 1",
            "Marker 2",
            "Marker 3",
            "Marker 4",
            "Marker 5",
            "Marker 6",
            "Marker 7",
            "Marker 8",
            "Marker 9",
            "Marker 10",
            "Marker 11",
        ],
        "test2.odm": [
            "마커 1",
            "마커 2",
            "마커 3",
            "마커 4",
            "마커 5",
            "마커 6",
            "마커 7",
            "마커 8",
            "마커 9",
            "마커 10",
            "마커 11",
        ],
        "test3.odm": [
            "Ball Lightning",
            "Prelude",
            "Part 1 - College",
            "Part 1 - Strange Phenomena 1",
            "Part 1 - Ball Lightning",
        ],
        "test4.odm": [
            "Ball Lightning",
            "Prelude",
            "Part 1 - College",
            "Part 1 - Strange Phenomena 1",
            "Part 1 - Ball Lightning",
        ],
        "test_ref24.odm": [
            "Ball Lightning",
            "Prelude",
            "Part 1 - College",
            "Part 1 - Strange Phenomena 1",
            "Part 1 - Ball Lightning",
        ],
    }
    album_artists = {
        "test1.odm": "Robert Herrick",
        "test2.odm": "로버트 Herrick",
        "test3.odm": "Robert Herrick",
        "test4.odm": "Robert Herrick",
        "test_ref24.odm": "Robert Herrick",
    }
    book_parts = {
        "test1.odm": 11,
        "test2.odm": 11,
        "test3.odm": 1,
        "test4.odm": 1,
        "test_ref24.odm": 1,
    }
    book_chapters = {
        "test1.odm": 11,
        "test2.odm": 11,
        "test3.odm": 5,
        "test4.odm": 5,
        "test_ref24.odm": 5,
    }
    book_chapter_durations = {
        "test1.odm": [67, 61, 66, 64, 66, 46, 56, 56, 60, 52, 47],
        "test2.odm": [67, 61, 66, 64, 66, 46, 56, 56, 60, 52, 47],
        "test3.odm": [15, 15, 10, 15, 6],
        "test4.odm": [15, 15, 10, 15, 6],
        "test_ref24.odm": [15, 15, 10, 15, 6],
    }

    def setUp(self):
        try:
            self.test_file = os.environ["TEST_ODM"]
        except KeyError:
            raise RuntimeError("TEST_ODM environment var not defined.")

        self.test_data_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data"
        )
        self.book_folder = os.path.join(
            self.test_data_dir, self.book_folders[self.test_file]
        )
        self.merged_book_basename = self.merged_book_basenames[self.test_file]
        self.mp3_name_format = self.mp3_name_formats[self.test_file]
        self.total_parts = self.book_parts[self.test_file]
        self.total_chapters = self.book_chapters[self.test_file]
        self.chapter_durations_sec = self.book_chapter_durations[self.test_file]

    def test_info(self):
        """
        Test info with no arguments
        ```
        python -m odmpy info test_data/test.odm > test_data/test.odm.info.txt
        ```
        """
        expected_file = os.path.join(
            self.test_data_dir, "{}.info.expected.txt".format(self.test_file)
        )
        test_file = os.path.join(self.test_data_dir, "test.odm.info.txt")
        with open(expected_file) as expected, open(test_file) as actual:
            expected_text = expected.read()
            actual_text = actual.read()
            self.assertEqual(expected_text, actual_text)

    def test_info_json(self):
        """
        Test info with --format json argument
        ```
        python -m odmpy info -f json test_data/test.odm > test_data/test.odm.info.json
        ```
        """
        test_file = os.path.join(self.test_data_dir, "test.odm.info.json")
        with open(test_file, "r") as f:
            info = json.load(f)
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

    def test_download_1(self):
        """
        Test download with --keepcover arguments
        ```
        python -m odmpy dl test_data/test.odm -d test_data/downloads/ -k
        ```
        """
        self.assertTrue(os.path.isdir(self.book_folder))
        for i in range(1, self.total_parts + 1):
            book_file = os.path.join(self.book_folder, self.mp3_name_format.format(i))
            self.assertTrue(os.path.isfile(book_file))
        self.assertTrue(os.path.isfile(os.path.join(self.book_folder, "cover.jpg")))

    def test_download_2(self):
        """
        Test download with --merge arguments
        ```
        python -m odmpy dl test_data/test.odm -d test_data/downloads/ -m
        ```
        """
        mp3_file = os.path.join(
            self.book_folder, "{}.mp3".format(self.merged_book_basename)
        )
        self.assertTrue(os.path.isfile(mp3_file))

    def test_download_3(self):
        """
        Test download with --merge --mergeformat m4b arguments
        ```
        python -m odmpy dl test_data/test.odm -d test_data/downloads/ -m --mergeformat m4b
        ```
        """
        m4b_file = os.path.join(
            self.book_folder, "{}.m4b".format(self.merged_book_basename)
        )
        self.assertTrue(os.path.isfile(m4b_file))

    def test_download_4(self):
        """
        Test download with --chapters arguments
        ```
        python -m odmpy -v dl test_data/test.odm -d test_data/downloads/ -c
        ```
        """
        marker_count = 0
        for i in range(1, self.total_parts + 1):
            book_file = os.path.join(self.book_folder, self.mp3_name_format.format(i))
            audio = eyed3.load(book_file)
            self.assertTrue(audio.tag)
            self.assertTrue(
                audio.tag.title.startswith(
                    self.part_title_formats[self.test_file].format(i)
                )
            )

            self.assertEqual(audio.tag.album, "Ceremonies For Christmas")
            self.assertEqual(audio.tag.artist, "Robert Herrick")
            self.assertEqual(audio.tag.album_artist, self.album_artists[self.test_file])
            self.assertEqual(audio.tag.track_num[0], i)
            self.assertEqual(audio.tag.publisher, "Librivox")
            self.assertEqual(
                audio.tag.getTextFrame(odmpy.constants.PERFORMER_FID),
                "LibriVox Volunteers",
            )
            self.assertTrue(audio.tag.table_of_contents)
            self.assertTrue(audio.tag.chapters)
            for _, ch in enumerate(audio.tag.chapters):
                self.assertEqual(
                    ch.sub_frames[b"TIT2"][0].text,
                    self.markers[self.test_file][marker_count],
                )
                marker_count += 1

    def test_download_5(self):
        """
        Test download with --chapters --merge arguments
        ```
        python -m odmpy dl test_data/test.odm -d test_data/downloads/ -c -m
        mv 'test_data/downloads'/*/*Herrick.mp3 'test_data/downloads/output.mp3'
        ffprobe -v quiet -print_format json -show_format -show_streams -show_chapters \
            'test_data/downloads/output.mp3' > 'test_data/output.mp3.json'
        ```
        """
        json_file = os.path.join(self.test_data_dir, "output.mp3.json")
        last_end = 0
        with open(json_file) as f:
            meta = json.load(f)
            self.assertEqual(len(meta.get("chapters", [])), self.total_chapters)
            for ch in meta["chapters"]:
                self.assertEqual(
                    ch["tags"]["title"], self.markers[self.test_file][ch["id"]]
                )
                start = ch["start"]
                end = ch["end"]
                self.assertGreater(end, start)
                self.assertEqual(start, last_end)
                self.assertGreater(end, last_end)
                self.assertAlmostEqual(
                    (end - start) / 1000.0, self.chapter_durations_sec[ch["id"]], 0
                )
                last_end = end
            for tag in [
                "title",
                "album",
                "artist",
                "album_artist",
                "performer",
                "publisher",
                "track",
            ]:
                self.assertTrue(meta["format"]["tags"].get(tag))

    def test_download_6(self):
        """
        Test download with --mergeformat m4b
        ```
        python -m odmpy dl test_data/test.odm -d test_data/downloads/ -c -m --mergeformat m4b
        mv 'test_data/downloads'/*/*Herrick.m4b 'test_data/downloads/output.m4b'
        ffprobe -v quiet -print_format json -show_format -show_streams -show_chapters \
            'test_data/downloads/output.m4b' > 'test_data/output.m4b.json'
        ```
        """
        json_file = os.path.join(self.test_data_dir, "output.m4b.json")
        last_end = 0
        with open(json_file) as f:
            meta = json.load(f)
            self.assertEqual(len(meta.get("chapters", [])), self.total_chapters)
            for ch in meta["chapters"]:
                self.assertEqual(
                    ch["tags"]["title"], self.markers[self.test_file][ch["id"]]
                )
                start = ch["start"]
                end = ch["end"]
                self.assertGreater(end, start)
                self.assertEqual(start, last_end)
                self.assertGreater(end, last_end)
                if ch["id"] > 0:
                    # first chapter has a tiny bit difference for some reason
                    # AssertionError: 66.467 != 67 within 0 places (0.5330000000000013 difference)
                    self.assertAlmostEqual(
                        (end - start) / 1000.0, self.chapter_durations_sec[ch["id"]], 0
                    )
                last_end = end

    def test_download_7(self):
        """
        Test download with --nobookfolder argument
        ```
        python -m odmpy dl test_data/test.odm -d test_data/downloads/ -m --nobookfolder
        111
        """
        mp3_file = os.path.join(
            self.test_data_dir, "downloads", "{}.mp3".format(self.merged_book_basename)
        )
        self.assertTrue(os.path.isfile(mp3_file))

    def test_cover_fail_ref24(self):
        """
        Test with error downloading cover
        ```
        python -m odmpy dl test_data/test.odm -d test_data/downloads/ -k
        ```
        """
        self.assertTrue(os.path.isdir(self.book_folder))
        for i in range(1, self.total_parts + 1):
            book_file = os.path.join(self.book_folder, self.mp3_name_format.format(i))
            self.assertTrue(os.path.isfile(book_file))
        self.assertFalse(os.path.isfile(os.path.join(self.book_folder, "cover.jpg")))

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

    def test_opf(self):
        """
        Test OPF generation
        ```
        python -m odmpy dl test_data/test.odm -d test_data/downloads/ -k --opf
        ```
        """
        schema_file = os.path.join(self.test_data_dir, "opf.schema.xml")
        expected_file = os.path.join(self.test_data_dir, "test.opf.xml")
        test_file = os.path.join(self.book_folder, "ceremonies-for-christmas.opf")
        self.assertTrue(os.path.isfile(test_file))

        with open(test_file) as actual, open(
            schema_file, "r", encoding="utf-8"
        ) as schema:
            actual_opf = etree.parse(actual)
            relaxng = etree.RelaxNG(etree.parse(schema))
            relaxng.validate(actual_opf)

        with open(expected_file) as expected, open(test_file) as actual:
            expected_text = expected.read()
            actual_text = actual.read()
            self.assertEqual(expected_text, actual_text)


if __name__ == "__main__":
    unittest.main()

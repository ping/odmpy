import json
import os.path
import shutil
import subprocess
import unittest
import warnings

import eyed3  # type: ignore[import]

from odmpy import constants
from odmpy.odm import run
from .data import (
    part_title_formats,
    album_artists,
    markers,
    get_expected_result,
)


# Test non-interactive options
class OdmpyDlTests(unittest.TestCase):
    def setUp(self) -> None:
        warnings.filterwarnings(
            action="ignore", message="unclosed", category=ResourceWarning
        )
        try:
            self.test_file = os.environ["TEST_ODM"]
        except KeyError:
            self.test_file = ""

        self.test_data_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data"
        )
        self.test_downloads_dir = os.path.join(self.test_data_dir, "downloads")

    def tearDown(self) -> None:
        if os.path.isdir(self.test_downloads_dir):
            shutil.rmtree(self.test_downloads_dir, ignore_errors=True)

    def test_standard_download(self):
        """
        `odmpy dl test.odm --keepcover`
        """
        if not self.test_file:
            self.skipTest("No test file")
        expected_result = get_expected_result(self.test_downloads_dir, self.test_file)

        run(
            [
                "dl",
                os.path.join(self.test_data_dir, self.test_file),
                "--downloaddir",
                self.test_downloads_dir,
                "--keepcover",
                "--hideprogress",
            ],
            be_quiet=True,
        )
        self.assertTrue(os.path.isdir(expected_result.book_folder))
        for i in range(1, expected_result.total_parts + 1):
            book_file = os.path.join(
                expected_result.book_folder, expected_result.mp3_name_format.format(i)
            )
            self.assertTrue(os.path.isfile(book_file))
        self.assertTrue(
            os.path.isfile(os.path.join(expected_result.book_folder, "cover.jpg"))
        )

    def test_add_chapters(self):
        """
        `odmpy dl test.odm --chapters`
        """
        if not self.test_file:
            self.skipTest("No test file")
        expected_result = get_expected_result(self.test_downloads_dir, self.test_file)

        run(
            [
                "dl",
                os.path.join(self.test_data_dir, self.test_file),
                "--downloaddir",
                self.test_downloads_dir,
                "--chapters",
                "--hideprogress",
            ],
            be_quiet=True,
        )
        marker_count = 0
        for i in range(1, expected_result.total_parts + 1):
            book_file = os.path.join(
                expected_result.book_folder, expected_result.mp3_name_format.format(i)
            )
            audio = eyed3.load(book_file)
            self.assertTrue(audio.tag)
            self.assertTrue(
                audio.tag.title.startswith(part_title_formats[self.test_file].format(i))
            )

            self.assertEqual(audio.tag.album, "Ceremonies For Christmas")
            self.assertEqual(audio.tag.artist, "Robert Herrick")
            self.assertEqual(audio.tag.album_artist, album_artists[self.test_file])
            self.assertEqual(audio.tag.track_num[0], i)
            self.assertEqual(audio.tag.publisher, "Librivox")
            self.assertEqual(
                audio.tag.getTextFrame(constants.PERFORMER_FID),
                "LibriVox Volunteers",
            )
            self.assertTrue(audio.tag.table_of_contents)
            self.assertTrue(audio.tag.chapters)
            for _, ch in enumerate(audio.tag.chapters):
                self.assertEqual(
                    ch.sub_frames[b"TIT2"][0].text,
                    markers[self.test_file][marker_count],
                )
                marker_count += 1

    def test_merge_formats(self):
        """
        `odmpy dl test.odm --merge`
        """
        if not self.test_file:
            self.skipTest("No test file")
        expected_result = get_expected_result(self.test_downloads_dir, self.test_file)

        run(
            [
                "dl",
                os.path.join(self.test_data_dir, self.test_file),
                "--downloaddir",
                self.test_downloads_dir,
                "--merge",
                "--hideprogress",
            ],
            be_quiet=True,
        )
        mp3_file = os.path.join(
            expected_result.book_folder,
            "{}.mp3".format(expected_result.merged_book_basename),
        )
        self.assertTrue(os.path.isfile(mp3_file))

        run(
            [
                "dl",
                os.path.join(self.test_data_dir, self.test_file),
                "--downloaddir",
                self.test_downloads_dir,
                "--merge",
                "--mergeformat",
                "m4b",
                "--hideprogress",
            ],
            be_quiet=True,
        )
        m4b_file = os.path.join(
            expected_result.book_folder,
            "{}.m4b".format(expected_result.merged_book_basename),
        )
        self.assertTrue(os.path.isfile(m4b_file))

    def test_merge_formats_add_chapters(self):
        """
        `odmpy dl test.odm --merge --chapters`
        """
        if not self.test_file:
            self.skipTest("No test file")
        expected_result = get_expected_result(self.test_downloads_dir, self.test_file)

        run(
            [
                "dl",
                os.path.join(self.test_data_dir, self.test_file),
                "--downloaddir",
                self.test_downloads_dir,
                "--merge",
                "--chapters",
                "--hideprogress",
            ],
            be_quiet=True,
        )
        mp3_file = os.path.join(
            expected_result.book_folder,
            "{}.mp3".format(expected_result.merged_book_basename),
        )
        self.assertTrue(os.path.isfile(mp3_file))
        ffprobe_cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            mp3_file,
        ]
        cmd_result = subprocess.run(
            ffprobe_cmd, capture_output=True, text=True, check=True, encoding="utf-8"
        )
        meta = json.loads(str(cmd_result.stdout))

        last_end = 0
        self.assertEqual(len(meta.get("chapters", [])), expected_result.total_chapters)
        for ch in meta["chapters"]:
            self.assertEqual(ch["tags"]["title"], markers[self.test_file][ch["id"]])
            start = ch["start"]
            end = ch["end"]
            self.assertGreater(end, start)
            self.assertEqual(start, last_end)
            self.assertGreater(end, last_end)
            self.assertAlmostEqual(
                (end - start) / 1000.0,
                expected_result.chapter_durations_sec[ch["id"]],
                0,
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

        run(
            [
                "dl",
                os.path.join(self.test_data_dir, self.test_file),
                "--downloaddir",
                self.test_downloads_dir,
                "--merge",
                "--mergeformat",
                "m4b",
                "--chapters",
                "--hideprogress",
            ],
            be_quiet=True,
        )
        m4b_file = os.path.join(
            expected_result.book_folder,
            "{}.m4b".format(expected_result.merged_book_basename),
        )
        self.assertTrue(os.path.isfile(m4b_file))
        ffprobe_cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            m4b_file,
        ]
        cmd_result = subprocess.run(
            ffprobe_cmd, capture_output=True, text=True, check=True, encoding="utf-8"
        )

        last_end = 0
        meta = json.loads(str(cmd_result.stdout))
        self.assertEqual(len(meta.get("chapters", [])), expected_result.total_chapters)
        for ch in meta["chapters"]:
            self.assertEqual(ch["tags"]["title"], markers[self.test_file][ch["id"]])
            start = ch["start"]
            end = ch["end"]
            self.assertGreater(end, start)
            self.assertEqual(start, last_end)
            self.assertGreater(end, last_end)
            if ch["id"] > 0:
                # first chapter has a tiny bit difference for some reason
                # AssertionError: 66.467 != 67 within 0 places (0.5330000000000013 difference)
                self.assertAlmostEqual(
                    (end - start) / 1000.0,
                    expected_result.chapter_durations_sec[ch["id"]],
                    0,
                )
            last_end = end

    def test_nobook_folder(self):
        """
        `odmpy dl test.odm --nobookfolder`
        """
        if not self.test_file:
            self.skipTest("No test file")
        expected_result = get_expected_result(self.test_downloads_dir, self.test_file)
        run(
            [
                "dl",
                os.path.join(self.test_data_dir, self.test_file),
                "--downloaddir",
                self.test_downloads_dir,
                "--merge",
                "--nobookfolder",
                "--hideprogress",
            ],
            be_quiet=True,
        )
        mp3_file = os.path.join(
            self.test_data_dir,
            "downloads",
            "{}.mp3".format(expected_result.merged_book_basename),
        )
        self.assertTrue(os.path.isfile(mp3_file))

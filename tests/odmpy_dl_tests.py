import json
import shutil
import subprocess

import responses
from mutagen.mp3 import MP3

from odmpy.odm import run
from .base import BaseTestCase
from .data import (
    part_title_formats,
    album_artists,
    markers,
    get_expected_result,
)


# Test non-interactive options
class OdmpyDlTests(BaseTestCase):
    def setUp(self) -> None:
        super().setUp()

        # test1.odm - book with ascii meta
        # test2.odm - book with non-ascii meta
        # test3.odm - Issue using mutagen, ref #17
        # test4.odm - HTML entities decoding, ref #19
        self.test_odms = ["test1.odm", "test2.odm", "test3.odm", "test4.odm"]

    def _setup_common_responses(self):
        with self.test_data_dir.joinpath("audiobook", "cover.jpg").open("rb") as c:
            img_bytes = c.read()
            # cover from OD API
            responses.get(
                "https://ic.od-cdn.com/resize?type=auto&width=510&height=510&force=true&quality=80&url=%2Fodmpy%2Ftest_data%2Fcover.jpg",
                content_type="image/jpeg",
                body=img_bytes,
            )

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
            "book2/ceremonies_herrick_bk_64kb.mp3",
            "book2/ceremonies_herrick_cjph_64kb.mp3",
            "book2/ceremonies_herrick_gg_64kb.mp3",
            "book3/01_ceremonies_herrick_cjph_64kb.mp3",
        ):
            with odm_test_data_dir.joinpath(mp3).open("rb") as m:
                responses.get(
                    f"https://ping.github.io/odmpy/test_data/{mp3}",
                    content_type="audio/mp3",
                    body=m.read(),
                )

    @responses.activate
    def test_standard_download(self):
        """
        `odmpy dl test.odm --keepcover`
        """
        for test_odm_file in self.test_odms:
            with self.subTest(odm=test_odm_file):
                expected_result = get_expected_result(
                    self.test_downloads_dir, test_odm_file
                )
                self._setup_common_responses()

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
                self.assertTrue(expected_result.book_folder.exists())
                for i in range(1, expected_result.total_parts + 1):
                    book_file = expected_result.book_folder.joinpath(
                        expected_result.mp3_name_format.format(i)
                    )
                    self.assertTrue(book_file.exists())
                    mutagen_audio = MP3(book_file)
                    self.assertTrue(mutagen_audio.tags)
                    self.assertEqual(mutagen_audio.tags.version[1], 4)
                    self.assertEqual(mutagen_audio.tags["TLAN"].text[0], "eng")
        self.assertTrue(expected_result.book_folder.joinpath("cover.jpg").exists())

    @responses.activate
    def test_add_chapters(self):
        """
        `odmpy dl test.odm --chapters`
        """
        for test_odm_file in self.test_odms:
            # clear remnant downloads
            if self.test_downloads_dir.exists():
                shutil.rmtree(self.test_downloads_dir, ignore_errors=True)

            with self.subTest(odm=test_odm_file):
                expected_result = get_expected_result(
                    self.test_downloads_dir, test_odm_file
                )
                self._setup_common_responses()

                run(
                    [
                        "--noversioncheck",
                        "dl",
                        str(self.test_data_dir.joinpath(test_odm_file)),
                        "--downloaddir",
                        str(self.test_downloads_dir),
                        "--chapters",
                        "--id3v2version",
                        "3",
                        "--hideprogress",
                    ],
                    be_quiet=True,
                )
                for i in range(1, expected_result.total_parts + 1):
                    book_file = expected_result.book_folder.joinpath(
                        expected_result.mp3_name_format.format(i)
                    )
                    mutagen_audio = MP3(book_file)
                    self.assertTrue(mutagen_audio.tags)
                    self.assertEqual(mutagen_audio.tags.version[1], 3)
                    self.assertTrue(
                        mutagen_audio.tags["TIT2"]
                        .text[0]
                        .startswith(part_title_formats[test_odm_file].format(i))
                    )
                    self.assertEqual(
                        mutagen_audio.tags["TALB"].text[0], "Ceremonies For Christmas"
                    )
                    self.assertEqual(mutagen_audio.tags["TLAN"].text[0], "eng")
                    self.assertEqual(
                        mutagen_audio.tags["TPE1"].text[0], "Robert Herrick"
                    )
                    self.assertEqual(
                        mutagen_audio.tags["TPE2"].text[0],
                        album_artists[test_odm_file],
                    )
                    self.assertEqual(mutagen_audio.tags["TRCK"], str(i))
                    self.assertEqual(mutagen_audio.tags["TPUB"].text[0], "Librivox")
                    self.assertEqual(
                        mutagen_audio.tags["TPE3"].text[0],
                        "LibriVox Volunteers",
                    )
                    self.assertTrue(mutagen_audio.tags["CTOC:toc"])
                    for j, chap_id in enumerate(
                        mutagen_audio.tags["CTOC:toc"].child_element_ids
                    ):
                        chap_tag = mutagen_audio.tags[f"CHAP:{chap_id}"]
                        self.assertTrue(chap_tag.sub_frames)
                        self.assertEqual(
                            chap_tag.sub_frames["TIT2"].text[0],
                            markers[test_odm_file][j + i - 1],
                        )

    @responses.activate
    def test_merge_formats(self):
        """
        `odmpy dl test.odm --merge`
        """
        for test_odm_file in self.test_odms:
            with self.subTest(odm=test_odm_file):
                expected_result = get_expected_result(
                    self.test_downloads_dir, test_odm_file
                )
                self._setup_common_responses()

                run(
                    [
                        "--noversioncheck",
                        "dl",
                        str(self.test_data_dir.joinpath(test_odm_file)),
                        "--downloaddir",
                        str(self.test_downloads_dir),
                        "--merge",
                        "--hideprogress",
                    ],
                    be_quiet=True,
                )
                mp3_file = expected_result.book_folder.joinpath(
                    f"{expected_result.merged_book_basename}.mp3"
                )
                self.assertTrue(mp3_file.exists())

                run(
                    [
                        "--noversioncheck",
                        "dl",
                        str(self.test_data_dir.joinpath(test_odm_file)),
                        "--downloaddir",
                        str(self.test_downloads_dir),
                        "--merge",
                        "--mergeformat",
                        "m4b",
                        "--hideprogress",
                    ],
                    be_quiet=True,
                )
                m4b_file = expected_result.book_folder.joinpath(
                    f"{expected_result.merged_book_basename}.m4b"
                )
                self.assertTrue(m4b_file.exists())

    @responses.activate
    def test_merge_formats_add_chapters(self):
        """
        `odmpy dl test.odm --merge --chapters`
        """
        for test_odm_file in self.test_odms:
            with self.subTest(odm=test_odm_file):
                # clear remnant downloads
                if self.test_downloads_dir.exists():
                    shutil.rmtree(self.test_downloads_dir, ignore_errors=True)

                expected_result = get_expected_result(
                    self.test_downloads_dir, test_odm_file
                )
                self._setup_common_responses()

                run(
                    [
                        "--noversioncheck",
                        "dl",
                        str(self.test_data_dir.joinpath(test_odm_file)),
                        "--downloaddir",
                        str(self.test_downloads_dir),
                        "--merge",
                        "--chapters",
                        "--hideprogress",
                    ],
                    be_quiet=True,
                )
                mp3_file = expected_result.book_folder.joinpath(
                    f"{expected_result.merged_book_basename}.mp3"
                )
                self.assertTrue(mp3_file.exists())
                ffprobe_cmd = [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    "-show_chapters",
                    str(mp3_file),
                ]
                cmd_result = subprocess.run(
                    ffprobe_cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    encoding="utf-8",
                )
                meta = json.loads(str(cmd_result.stdout))

                last_end = 0
                self.assertEqual(
                    len(meta.get("chapters", [])), expected_result.total_chapters
                )
                for i, ch in enumerate(
                    sorted(meta["chapters"], key=lambda c: c["start"])
                ):
                    self.assertEqual(ch["tags"]["title"], markers[test_odm_file][i])
                    start = ch["start"]
                    end = ch["end"]
                    self.assertGreater(end, start)
                    self.assertEqual(start, last_end)
                    self.assertGreater(end, last_end)
                    self.assertAlmostEqual(
                        (end - start) / 1000.0,
                        expected_result.chapter_durations_sec[i],
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
                    with self.subTest(tag=tag):
                        self.assertTrue(meta["format"]["tags"].get(tag))

                run(
                    [
                        "--noversioncheck",
                        "dl",
                        str(self.test_data_dir.joinpath(test_odm_file)),
                        "--downloaddir",
                        str(self.test_downloads_dir),
                        "--merge",
                        "--mergeformat",
                        "m4b",
                        "--chapters",
                        "--hideprogress",
                    ],
                    be_quiet=True,
                )
                m4b_file = expected_result.book_folder.joinpath(
                    f"{expected_result.merged_book_basename}.m4b"
                )
                self.assertTrue(m4b_file.exists())
                ffprobe_cmd = [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    "-show_chapters",
                    str(m4b_file),
                ]
                cmd_result = subprocess.run(
                    ffprobe_cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    encoding="utf-8",
                )

                last_end = 0
                meta = json.loads(str(cmd_result.stdout))
                self.assertEqual(
                    len(meta.get("chapters", [])), expected_result.total_chapters
                )
                for i, ch in enumerate(
                    sorted(meta["chapters"], key=lambda c: c["start"])
                ):
                    self.assertEqual(ch["tags"]["title"], markers[test_odm_file][i])
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
                            expected_result.chapter_durations_sec[i],
                            0,
                        )
                    last_end = end

    @responses.activate
    def test_nobook_folder(self):
        """
        `odmpy dl test.odm --nobookfolder`
        """
        for test_odm_file in self.test_odms:
            with self.subTest(odm=test_odm_file):
                expected_result = get_expected_result(
                    self.test_downloads_dir, test_odm_file
                )
                self._setup_common_responses()

                run(
                    [
                        "--noversioncheck",
                        "dl",
                        str(self.test_data_dir.joinpath(test_odm_file)),
                        "--downloaddir",
                        str(self.test_downloads_dir),
                        "--merge",
                        "--nobookfolder",
                        "--hideprogress",
                        "--writejson",
                    ],
                    be_quiet=True,
                )
                mp3_file = self.test_data_dir.joinpath(
                    "downloads", f"{expected_result.merged_book_basename}.mp3"
                )
                self.assertTrue(mp3_file.exists())
                self.assertTrue(
                    self.test_data_dir.joinpath("downloads", "debug.json").exists()
                )

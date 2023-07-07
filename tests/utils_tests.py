import argparse
import string
import unittest
from datetime import datetime
from pathlib import Path
from random import choices

from odmpy import cli_utils
from odmpy import utils
from tests.base import is_windows


class UtilsTests(unittest.TestCase):
    def test_sanitize_path(self):
        self.assertEqual(
            utils.sanitize_path(r'a<b>c:d"e/f\g|h?i*j_a<b>c:d"e/f\g|h?i*j', ""),
            "abcdefghij_abcdefghij"
            if is_windows
            else r'a<b>c:d"ef\g|h?i*j_a<b>c:d"ef\g|h?i*j',
        )
        self.assertEqual(
            utils.sanitize_path(r'a<b>c:d"e/f\g|h?i*j'),
            "a-b-c-d-e-f-g-h-i-j" if is_windows else r'a<b>c:d"e-f\g|h?i*j',
        )

        self.assertEqual(
            utils.sanitize_path("abc\ndef\tghi"),
            "abcdefghi",
        )
        self.assertEqual(
            utils.sanitize_path("Español 中文 русский 한국어 日本語"),
            "Español 中文 русский 한국어 日本語",
        )
        self.assertEqual(
            utils.sanitize_path("abc_def.,ghi", "-", exclude_chars="_.,"),
            "abc-def--ghi",
        )
        self.assertEqual(
            utils.sanitize_path("abc_def.,ghi", "-", exclude_chars="_.,-"),
            "abcdefghi",
        )

    def test_sanitize_path_mkdir(self):
        # test if the folder and file can actually be created on the OS
        ts = int(datetime.utcnow().timestamp() * 1000)
        random_text = "".join(choices(string.ascii_lowercase, k=10))
        sanitized_path = utils.sanitize_path(
            rf'test_{random_text}_{ts}<>:"/\|?*', sub_text=""
        )
        if is_windows:
            self.assertEqual(sanitized_path, f"test_{random_text}_{ts}")
        test_path = Path(sanitized_path)
        test_file = test_path.joinpath(f"{sanitized_path}.txt")
        try:
            test_path.mkdir(parents=True)
            self.assertTrue(test_path.is_dir())
            with test_file.open("w", encoding="utf-8") as f:
                f.write(sanitized_path)
            self.assertTrue(test_file.is_file())
        finally:
            if test_file.exists():
                test_file.unlink()
            if test_path.exists():
                test_path.rmdir()

    def test_slugify(self):
        self.assertEqual(
            utils.slugify("Español 中文 русский 한국어 日本語", allow_unicode=True),
            "español-中文-русский-한국어-日本語",
        )
        self.assertEqual(
            utils.slugify("Abc Def Ghi!?", allow_unicode=True),
            "abc-def-ghi",
        )

    def test_parse_duration_to_milliseconds(self):
        self.assertEqual(
            utils.parse_duration_to_milliseconds("1:23:45.678"),
            1 * 60 * 60 * 1000 + 23 * 60 * 1000 + 45 * 1000 + 678,
        )
        self.assertEqual(utils.parse_duration_to_milliseconds("12:00"), 12 * 60 * 1000)

    def test_parse_duration_to_seconds(self):
        self.assertEqual(utils.parse_duration_to_seconds("12:00"), 12 * 60)
        self.assertEqual(utils.parse_duration_to_seconds("12:00.6"), 12 * 60 + 1)

    def test_positive_int(self):
        self.assertEqual(cli_utils.positive_int("1"), 1)

        with self.assertRaises(argparse.ArgumentTypeError):
            _ = cli_utils.positive_int("x")

        with self.assertRaises(argparse.ArgumentTypeError):
            _ = cli_utils.positive_int("-1")

    def test_valid_book_folder_file_format(self):
        self.assertEqual(
            cli_utils.valid_book_folder_file_format(
                "%(Author)s/%(Series)s/%(Title)s-%(Edition)s-%(ID)s"
            ),
            "%(Author)s/%(Series)s/%(Title)s-%(Edition)s-%(ID)s",
        )

        with self.assertRaises(argparse.ArgumentTypeError) as context:
            _ = cli_utils.valid_book_folder_file_format("%(X)s")
        self.assertIn("Invalid field 'X'", str(context.exception))

    def test_mimetypes_guess(self):
        for f in (
            "a.xhtml",
            "a.html",
            "a.css",
            "a.png",
            "a.gif",
            "a.jpeg",
            "a.jpg",
            "a.otf",
            "a.ttf",
            "a.eot",
            "a.woff",
            "a.woff2",
            "x/a.svg",
            "http://localhost/x/a.ncx",
        ):
            with self.subTest(file_name=f):
                mime_type = utils.guess_mimetype(f)
                self.assertIsNotNone(mime_type, f"Unable to guess mimetype for {f}")

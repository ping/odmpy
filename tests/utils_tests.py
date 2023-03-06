import argparse
import os
import platform
import string
import unittest
from datetime import datetime
from random import choices

from odmpy import utils
from odmpy import cli_utils


class UtilsTests(unittest.TestCase):
    def test_sanitize_path(self):
        is_windows = os.name == "nt" or platform.system().lower() == "windows"
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

    @unittest.skipUnless(
        os.name == "nt" or platform.system().lower() == "windows", "Not Windows"
    )
    def test_sanitize_path_on_windows(self):
        # test if the folder can actually be created
        ts = int(datetime.utcnow().timestamp() * 1000)
        random_text = "".join(choices(string.ascii_lowercase, k=10))
        sanitized_path = utils.sanitize_path(
            rf'{random_text}_{ts}<>:"/\|?*', sub_text=""
        )
        self.assertEqual(sanitized_path, f"{random_text}_{ts}")
        os.makedirs(sanitized_path)
        os.rmdir(sanitized_path)

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

    def test_unescape_html(self):
        self.assertEqual(
            utils.unescape_html("&lt;b&gt;Hello &amp; Goodbye&lt;/b&gt;"),
            "<b>Hello & Goodbye</b>",
        )

    def test_positive_int(self):
        self.assertEqual(cli_utils.positive_int("1"), 1)

        with self.assertRaises(argparse.ArgumentTypeError):
            _ = cli_utils.positive_int("x")

        with self.assertRaises(argparse.ArgumentTypeError):
            _ = cli_utils.positive_int("-1")

    def test_valid_book_folder_file_format(self):
        self.assertEqual(
            cli_utils.valid_book_folder_file_format(
                "%(Author)s/%(Series)s/%(Title)s-%(Edition)s"
            ),
            "%(Author)s/%(Series)s/%(Title)s-%(Edition)s",
        )

        with self.assertRaises(argparse.ArgumentTypeError) as context:
            _ = cli_utils.valid_book_folder_file_format("%(X)s")
        self.assertIn("Invalid field 'X'", str(context.exception))
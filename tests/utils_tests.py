import os
import platform
import unittest

from odmpy import utils


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

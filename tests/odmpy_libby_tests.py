import json
import os.path
import time
import unittest
from datetime import datetime
from http import HTTPStatus
from typing import Dict
from unittest.mock import patch, MagicMock

import ebooklib  # type: ignore[import]
import responses
from bs4 import BeautifulSoup
from ebooklib import epub
from lxml import etree  # type: ignore[import]
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from responses import matchers

from odmpy.errors import LibbyNotConfiguredError, OdmpyRuntimeError
from odmpy.libby import LibbyClient, LibbyFormats
from odmpy.odm import run
from .base import BaseTestCase


class OdmpyLibbyTests(BaseTestCase):
    # don't know if this is good idea...
    _custom_counter: Dict[str, int] = {}

    @staticmethod
    def add_to_counter(counter_name: str) -> None:
        if not OdmpyLibbyTests._custom_counter.get(counter_name):
            OdmpyLibbyTests._custom_counter[counter_name] = 0
        OdmpyLibbyTests._custom_counter[counter_name] += 1

    @staticmethod
    def get_counter(counter_name: str) -> int:
        return OdmpyLibbyTests._custom_counter.get(counter_name, 0)

    def test_settings_clear(self):
        settings_folder = self._generate_fake_settings()
        settings_file = settings_folder.joinpath("libby.json")
        self.assertTrue(settings_file.exists())
        run(["libby", "--settings", str(settings_folder), "--reset"], be_quiet=True)
        self.assertFalse(settings_file.exists())

    def test_libby_export(self):
        """
        `odmpy libby --exportloans`
        """
        try:
            run(["--noversioncheck", "libby", "--check"], be_quiet=True)
        except LibbyNotConfiguredError:
            self.skipTest("Libby not setup.")

        loans_file_name = self.test_downloads_dir.joinpath(
            f"test_loans_{int(datetime.utcnow().timestamp()*1000)}.json",
        )
        run(
            ["--noversioncheck", "libby", "--exportloans", str(loans_file_name)],
            be_quiet=True,
        )
        self.assertTrue(loans_file_name.exists())
        with loans_file_name.open("r", encoding="utf-8") as f:
            loans = json.load(f)
            for loan in loans:
                self.assertIn("id", loan)

    @unittest.skip("Takes too long")  # turn on/off at will
    def test_libby_download_select(self):
        """
        `odmpy libby --select N`
        """
        try:
            run(["libby", "--check"], be_quiet=True)
        except LibbyNotConfiguredError:
            self.skipTest("Libby not setup.")

        ts = int(datetime.utcnow().timestamp() * 1000)
        loans_file_name = self.test_downloads_dir.joinpath(f"test_loans_{ts}.json")
        download_folder = self.test_downloads_dir.joinpath(f"test_downloads_{ts}")
        download_folder.mkdir(parents=True, exist_ok=True)
        run(["libby", "--exportloans", str(loans_file_name)], be_quiet=True)
        self.assertTrue(loans_file_name.exists())
        with loans_file_name.open("r", encoding="utf-8") as f:
            loans = json.load(f)
        if not loans:
            self.skipTest("No loans.")

        try:
            run(
                [
                    "--noversioncheck",
                    "libby",
                    "--direct",
                    "--downloaddir",
                    str(download_folder),
                    "--select",
                    str(len(loans)),
                    "--hideprogress",
                ],
                be_quiet=True,
            )
        except KeyboardInterrupt:
            self.fail("Test aborted")

        self.assertTrue(download_folder.glob("*/*.mp3"))

    @unittest.skip("Takes too long")  # turn on/off at will
    def test_libby_download_latest(self):
        """
        `odmpy libby --latest N`
        """
        try:
            run(["libby", "--check"], be_quiet=True)
        except LibbyNotConfiguredError:
            self.skipTest("Libby not setup.")
        ts = int(datetime.utcnow().timestamp() * 1000)
        loans_file_name = self.test_downloads_dir.joinpath(f"test_loans_{ts}.json")
        download_folder = self.test_downloads_dir.joinpath(f"test_downloads_{ts}")
        download_folder.mkdir(parents=True, exist_ok=True)
        run(["libby", "--exportloans", str(loans_file_name)], be_quiet=True)
        self.assertTrue(loans_file_name.exists())
        with loans_file_name.open("r", encoding="utf-8") as f:
            loans = json.load(f)
        if not loans:
            self.skipTest("No loans.")

        try:
            run(
                [
                    "--noversioncheck",
                    "libby",
                    "--direct",
                    "--downloaddir",
                    str(download_folder),
                    "--latest",
                    "1",
                    "--hideprogress",
                ],
                be_quiet=True,
            )
        except KeyboardInterrupt:
            self.fail("Test aborted")

        self.assertTrue(download_folder.glob("*/*.mp3"))

    @unittest.skip("Takes too long")  # turn on/off at will
    def test_libby_download_ebook(self):
        """
        `odmpy libby --ebooks --select N`
        """
        try:
            run(["--noversioncheck", "libby", "--check"], be_quiet=True)
        except LibbyNotConfiguredError:
            self.skipTest("Libby not setup.")
        ts = int(datetime.utcnow().timestamp() * 1000)
        loans_file_name = self.test_downloads_dir.joinpath(f"test_loans_{ts}.json")
        download_folder = self.test_downloads_dir.joinpath(f"test_downloads_{ts}")
        download_folder.mkdir(parents=True, exist_ok=True)
        run(["libby", "--ebooks", "--exportloans", str(loans_file_name)], be_quiet=True)
        self.assertTrue(loans_file_name.exists())
        with loans_file_name.open("r", encoding="utf-8") as f:
            loans = json.load(f)
        if not loans:
            self.skipTest("No loans.")

        selected_index = 0
        for i, loan in enumerate(loans, start=1):
            if LibbyClient.get_loan_format(
                loan
            ) == LibbyFormats.EBookEPubAdobe and LibbyClient.has_format(
                loan, LibbyFormats.EBookOverdrive
            ):
                selected_index = i
                break
        if not selected_index:
            self.skipTest("No suitable ebook loan.")

        try:
            run(
                [
                    "--noversioncheck",
                    "libby",
                    "--ebooks",
                    "--downloaddir",
                    str(download_folder),
                    "--select",
                    str(selected_index),
                ],
                be_quiet=True,
            )
        except KeyboardInterrupt:
            self.fail("Test aborted")

        self.assertTrue(download_folder.glob("*/*.acsm"))

    @unittest.skip("Takes too long")  # turn on/off at will
    def test_libby_download_ebook_direct(self):
        """
        `odmpy libby --ebooks --select N`
        """
        try:
            run(["--noversioncheck", "libby", "--check"], be_quiet=True)
        except LibbyNotConfiguredError:
            self.skipTest("Libby not setup.")
        ts = int(datetime.utcnow().timestamp() * 1000)
        loans_file_name = self.test_downloads_dir.joinpath(f"test_loans_{ts}.json")
        download_folder = self.test_downloads_dir.joinpath(f"test_downloads_{ts}")
        download_folder.mkdir(parents=True, exist_ok=True)
        run(["libby", "--ebooks", "--exportloans", str(loans_file_name)], be_quiet=True)
        self.assertTrue(loans_file_name.exists())
        with loans_file_name.open("r", encoding="utf-8") as f:
            loans = json.load(f)
        if not loans:
            self.skipTest("No loans.")

        selected_index = 0
        for i, loan in enumerate(loans, start=1):
            if LibbyClient.get_loan_format(
                loan
            ) == LibbyFormats.EBookEPubAdobe and LibbyClient.has_format(
                loan, LibbyFormats.EBookOverdrive
            ):
                selected_index = i
                break
        if not selected_index:
            self.skipTest("No suitable ebook loan.")

        try:
            run(
                [
                    "libby",
                    "--ebooks",
                    "--direct",
                    "--downloaddir",
                    str(download_folder),
                    "--select",
                    str(selected_index),
                    # "--hideprogress",
                ],
                be_quiet=True,
            )
        except KeyboardInterrupt:
            self.fail("Test aborted")

        self.assertTrue(download_folder.glob("*/*.epub"))

    @responses.activate
    def test_mock_libby_download_magazine(self):
        settings_folder = self._generate_fake_settings()

        with self.test_data_dir.joinpath("magazine", "sync.json").open(
            "r", encoding="utf-8"
        ) as s:
            responses.get(
                "https://sentry-read.svc.overdrive.com/chip/sync", json=json.load(s)
            )
        with self.test_data_dir.joinpath("magazine", "rosters.json").open(
            "r", encoding="utf-8"
        ) as r:
            responses.get(
                "http://localhost/mock/rosters.json",
                json=json.load(r),
            )
        with self.test_data_dir.joinpath("magazine", "openbook.json").open(
            "r", encoding="utf-8"
        ) as o:
            responses.get(
                "http://localhost/mock/openbook.json",
                json=json.load(o),
            )
        responses.head(
            "http://localhost/mock",
            body="",
        )
        responses.get(
            "https://sentry-read.svc.overdrive.com/open/magazine/card/123456789/title/9999999",
            json={
                "message": "xyz",
                "urls": {
                    "web": "http://localhost/mock",
                    "rosters": "http://localhost/mock/rosters.json",
                    "openbook": "http://localhost/mock/openbook.json",
                },
            },
        )
        with self.test_data_dir.joinpath("magazine", "media.json").open(
            "r", encoding="utf-8"
        ) as m:
            responses.get(
                "https://thunder.api.overdrive.com/v2/media/9999999?x-client-id=dewey",
                json=json.load(m),
            )
        with self.test_data_dir.joinpath("magazine", "cover.jpg").open("rb") as c:
            # this is the cover from OD API
            responses.get(
                "http://localhost/mock/cover.jpg",
                content_type="image/jpeg",
                body=c.read(),
            )
        # mock roster title contents
        for page in (
            "pages/Cover.xhtml",
            "stories/story-01.xhtml",
            "stories/story-02.xhtml",
        ):
            with self.test_data_dir.joinpath("magazine", "content", page).open(
                "r", encoding="utf-8"
            ) as f:
                responses.get(
                    f"http://localhost/{page}",
                    content_type="application/xhtml+xml",
                    body=f.read(),
                )
        for img in ("assets/cover.jpg",):
            with self.test_data_dir.joinpath("magazine", "content", img).open(
                "rb"
            ) as f:
                responses.get(
                    f"http://localhost/{img}",
                    content_type="image/jpeg",
                    body=f.read(),
                )
        for css in ("assets/magazine.css", "assets/fontfaces.css"):
            with self.test_data_dir.joinpath("magazine", "content", css).open(
                "r", encoding="utf-8"
            ) as f:
                responses.get(
                    f"http://localhost/{css}",
                    content_type="text/css",
                    body=f.read(),
                )

        test_folder = "test"

        run_command = [
            "libby",
            "--settings",
            str(settings_folder),
            "--magazines",
            "--downloaddir",
            str(self.test_downloads_dir),
            "--bookfolderformat",
            test_folder,
            "--bookfileformat",
            "magazine",
            "--latest",
            "1",
            "--opf",
            "--hideprogress",
        ]
        if self.is_verbose:
            run_command.insert(0, "--verbose")
        run(run_command, be_quiet=not self.is_verbose)
        self.assertTrue(
            self.test_downloads_dir.joinpath(test_folder, "magazine.opf").exists()
        )
        epub_file_path = self.test_downloads_dir.joinpath(test_folder, "magazine.epub")
        self.assertTrue(epub_file_path.exists())

        book = epub.read_epub(epub_file_path, {"ignore_ncx": True})
        stories = [
            d
            for d in list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
            if d.get_name().startswith("stories/")
        ]
        self.assertEqual(len(stories), 2)
        for story in stories:
            soup = BeautifulSoup(story.get_content(), "html.parser")
            self.assertTrue(
                soup.find("h1")
            )  # check that pages are properly de-serialised

        cover = next(
            iter([b for b in list(book.get_items_of_type(ebooklib.ITEM_COVER))]),
            None,
        )
        self.assertTrue(cover)
        with self.test_data_dir.joinpath(
            "magazine", "content", "assets", "cover.jpg"
        ).open("rb") as f:
            self.assertEqual(f.read(), cover.get_content())

        nav = next(
            iter([b for b in list(book.get_items_of_type(ebooklib.ITEM_NAVIGATION))]),
            None,
        )
        self.assertTrue(nav)

        # Check sections are rendered properly in the ncx
        nav_doc = etree.fromstring(nav.get_content())
        ns = {"d": "http://www.daisy.org/z3986/2005/ncx/"}
        nav_map = nav_doc.find(".//d:navMap", namespaces=ns)
        self.assertIsNotNone(nav_map)
        section_nav_point = [c for c in nav_map][2]
        section_articles = section_nav_point.find(".//d:navPoint", namespaces=ns)
        self.assertEqual(len(section_articles), 2)

        # Check sections are rendered properly in the nav.xhtml
        epub_nav = next(
            iter(
                [
                    d
                    for d in list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
                    if type(d) == ebooklib.epub.EpubNav
                ]
            ),
            None,
        )
        self.assertTrue(epub_nav)
        soup = BeautifulSoup(epub_nav.get_content(), features="html.parser")
        toc = soup.find(id="toc")
        sub_ol_ele = toc.select("li ol")
        self.assertEqual(len(sub_ol_ele), 1)
        self.assertEqual(len(sub_ol_ele[0].find_all("li")), 2)

        css = next(
            iter([b for b in list(book.get_items_of_type(ebooklib.ITEM_STYLE))]),
            None,
        )
        self.assertTrue(css)
        for css_file in list(book.get_items_of_type(ebooklib.ITEM_STYLE)):
            self.assertIn(
                css_file.get_name(), ("assets/magazine.css", "assets/fontfaces.css")
            )
            css_content = css_file.get_content().decode("utf-8")
            if css_file.get_name() == "assets/magazine.css":
                # test for patches
                self.assertNotIn("overflow-x", css_content)
                self.assertRegex(css_content, r"font-family:.+?,serif;")
                self.assertRegex(css_content, r"font-weight: 700;")
            if css_file.get_name() == "assets/fontfaces.css":
                self.assertNotIn("src", css_content)

    @responses.activate
    def test_mock_libby_download_ebook_acsm(self):
        settings_folder = self._generate_fake_settings()

        with self.test_data_dir.joinpath("ebook", "sync.json").open(
            "r", encoding="utf-8"
        ) as s:
            responses.get(
                "https://sentry-read.svc.overdrive.com/chip/sync", json=json.load(s)
            )
        with self.test_data_dir.joinpath("ebook", "ebook.acsm").open(
            "r", encoding="utf-8"
        ) as a:
            responses.get(
                "https://sentry-read.svc.overdrive.com/card/123456789/loan/9999999/fulfill/ebook-epub-adobe",
                content_type="application/xml",
                body=a.read(),
            )

        test_folder = "test"

        run_command = [
            "libby",
            "--settings",
            str(settings_folder),
            "--ebooks",
            "--downloaddir",
            str(self.test_downloads_dir),
            "--bookfolderformat",
            test_folder,
            "--bookfileformat",
            "ebook",
            "--select",
            "1",
            "--hideprogress",
        ]
        if self.is_verbose:
            run_command.insert(0, "--verbose")
        run(run_command, be_quiet=not self.is_verbose)
        self.assertTrue(
            self.test_downloads_dir.joinpath(test_folder, "ebook.acsm").exists()
        )

    @responses.activate
    def test_mock_libby_download_ebook_direct(self):
        settings_folder = self._generate_fake_settings()

        with self.test_data_dir.joinpath("ebook", "sync.json").open(
            "r", encoding="utf-8"
        ) as s:
            responses.get(
                "https://sentry-read.svc.overdrive.com/chip/sync", json=json.load(s)
            )
        with self.test_data_dir.joinpath("ebook", "rosters.json").open(
            "r", encoding="utf-8"
        ) as r:
            responses.get(
                "http://localhost/mock/rosters.json",
                json=json.load(r),
            )
        with self.test_data_dir.joinpath("ebook", "openbook.json").open(
            "r", encoding="utf-8"
        ) as o:
            responses.get(
                "http://localhost/mock/openbook.json",
                json=json.load(o),
            )
        responses.head(
            "http://localhost/mock",
            body="",
        )
        responses.get(
            "https://sentry-read.svc.overdrive.com/open/book/card/123456789/title/9999999",
            json={
                "message": "xyz",
                "urls": {
                    "web": "http://localhost/mock",
                    "rosters": "http://localhost/mock/rosters.json",
                    "openbook": "http://localhost/mock/openbook.json",
                },
            },
        )
        with self.test_data_dir.joinpath("ebook", "media.json").open(
            "r", encoding="utf-8"
        ) as m:
            responses.get(
                "https://thunder.api.overdrive.com/v2/media/9999999?x-client-id=dewey",
                json=json.load(m),
            )
        with self.test_data_dir.joinpath("ebook", "cover.jpg").open("rb") as c:
            # this is the cover from OD API
            responses.get(
                "http://localhost/mock/cover.jpg",
                content_type="image/jpeg",
                body=c.read(),
            )
        # mock roster title contents
        for page in (
            "pages/Cover.xhtml",
            "pages/page-01.xhtml",
            "pages/page-02.xhtml",
        ):
            with self.test_data_dir.joinpath("ebook", "content", page).open(
                "r", encoding="utf-8"
            ) as f:
                responses.get(
                    f"http://localhost/{page}",
                    content_type="application/xhtml+xml",
                    body=f.read(),
                )
        for img in ("assets/cover.jpg",):
            with self.test_data_dir.joinpath("ebook", "content", img).open("rb") as f:
                responses.get(
                    f"http://localhost/{img}",
                    content_type="image/jpeg",
                    body=f.read(),
                )
        with self.test_data_dir.joinpath("ebook", "content", "toc.ncx").open(
            "r", encoding="utf-8"
        ) as f:
            responses.get(
                "http://localhost/toc.ncx",
                content_type="application/x-dtbncx+xml",
                body=f.read(),
            )

        test_folder = "test"

        run_command = [
            "libby",
            "--settings",
            str(settings_folder),
            "--ebooks",
            "--downloaddir",
            str(self.test_downloads_dir),
            "--bookfolderformat",
            test_folder,
            "--bookfileformat",
            "ebook",
            "--direct",
            "--select",
            "1",
            "--opf",
            "--hideprogress",
            "--debug",
        ]
        if self.is_verbose:
            run_command.insert(0, "--verbose")
        run(run_command, be_quiet=not self.is_verbose)
        self.assertTrue(
            self.test_downloads_dir.joinpath(test_folder, "ebook.opf").exists()
        )
        epub_file_path = self.test_downloads_dir.joinpath(test_folder, "ebook.epub")
        self.assertTrue(epub_file_path.exists())

        book = epub.read_epub(epub_file_path, {"ignore_ncx": True})
        pages = [
            d
            for d in list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
            if d.get_name().startswith("pages/")
        ]
        self.assertEqual(len(pages), 3)
        for page in pages:
            if page.get_name() == "pages/Cover.xhtml":
                continue
            soup = BeautifulSoup(page.get_content(), "html.parser")
            self.assertTrue(
                soup.find("h1")
            )  # check that pages are properly de-serialised

        cover = next(
            iter([b for b in list(book.get_items_of_type(ebooklib.ITEM_COVER))]),
            None,
        )
        self.assertTrue(cover)
        with self.test_data_dir.joinpath(
            "ebook", "content", "assets", "cover.jpg"
        ).open("rb") as f:
            self.assertEqual(f.read(), cover.get_content())

        nav = next(
            iter([b for b in list(book.get_items_of_type(ebooklib.ITEM_NAVIGATION))]),
            None,
        )
        self.assertTrue(nav)
        self.assertEqual(nav.get_name(), "toc.ncx")
        ncx_soup = BeautifulSoup(nav.get_content(), "xml")
        meta_id = ncx_soup.find("meta", attrs={"name": "dtb:uid"})
        self.assertTrue(meta_id)
        self.assertEqual(meta_id["content"], "9789999999999")

        # test for debug artifacts here as well
        for f in ("loan.json", "media.json", "openbook.json", "rosters.json"):
            self.assertTrue(self.test_downloads_dir.joinpath(test_folder, f).exists())

    @responses.activate
    @patch("urllib.request.OpenerDirector.open")
    def test_mock_libby_download_ebook_open(self, mock_opener):
        settings_folder = self._generate_fake_settings()
        with self.test_data_dir.joinpath("ebook", "sync.json").open(
            "r", encoding="utf-8"
        ) as s:
            responses.get(
                "https://sentry-read.svc.overdrive.com/chip/sync", json=json.load(s)
            )
        responses.get(
            "https://sentry-read.svc.overdrive.com/card/123456789/loan/9999990/fulfill/ebook-epub-open",
            status=302,
            headers={"Location": "https://openepub-gk.cdn.overdrive.com/9999990"},
        )
        with self.test_data_dir.joinpath("ebook", "dummy.epub").open("rb") as a:
            opener_open = MagicMock()
            opener_open.getcode.return_value = 200
            opener_open.read.return_value = a.read()
            mock_opener.return_value = opener_open

            test_folder = "test"

            run_command = [
                "libby",
                "--settings",
                str(settings_folder),
                "--ebooks",
                "--downloaddir",
                str(self.test_downloads_dir),
                "--bookfolderformat",
                test_folder,
                "--bookfileformat",
                "ebook",
                "--latest",
                "1",
                "--hideprogress",
            ]
            if self.is_verbose:
                run_command.insert(0, "--verbose")
            run(run_command, be_quiet=not self.is_verbose)
            self.assertTrue(
                self.test_downloads_dir.joinpath(test_folder, "ebook.epub").exists()
            )

    def _setup_audiobook_direct_responses(self):
        with self.test_data_dir.joinpath("audiobook", "sync.json").open(
            "r", encoding="utf-8"
        ) as s:
            responses.get(
                "https://sentry-read.svc.overdrive.com/chip/sync", json=json.load(s)
            )
        with self.test_data_dir.joinpath("audiobook", "openbook.json").open(
            "r", encoding="utf-8"
        ) as o:
            responses.get(
                "http://localhost/mock/openbook.json",
                json=json.load(o),
            )
        responses.head(
            "http://localhost/mock",
            body="",
        )
        responses.get(
            "https://sentry-read.svc.overdrive.com/open/audiobook/card/123456789/title/9999999",
            json={
                "message": "xyz",
                "urls": {
                    "web": "http://localhost/mock",
                    "rosters": "http://localhost/mock/rosters.json",
                    "openbook": "http://localhost/mock/openbook.json",
                },
            },
        )
        with self.test_data_dir.joinpath("audiobook", "media.json").open(
            "r", encoding="utf-8"
        ) as m:
            json_text = m.read()
            responses.get(
                "https://thunder.api.overdrive.com/v2/media/9999999?x-client-id=dewey",
                json=json.loads(json_text),
            )
            responses.get(
                "https://thunder.api.overdrive.com/v2/media/0fef5121-bb1f-42a5-b62a-d9fded939d50?x-client-id=dewey",
                json=json.loads(json_text),
            )
        with self.test_data_dir.joinpath("audiobook", "cover.jpg").open("rb") as c:
            img_bytes = c.read()
            # this is the cover from OD API
            responses.get(
                "https://ic.od-cdn.com/resize?type=auto&width=510&height=510&force=true&quality=80&url=%2Fmock%2Fcover.jpg",
                content_type="image/jpeg",
                body=img_bytes,
            )
            responses.get(
                "https://ic.od-cdn.com/resize?type=auto&width=510&height=510&force=true&quality=80&url=%2Fodmpy%2Ftest_data%2Fcover.jpg",
                content_type="image/jpeg",
                body=img_bytes,
            )
        with self.test_data_dir.joinpath("audiobook", "book.mp3").open("rb") as c:
            responses.get(
                "http://localhost/%7BAAAAAAAA-BBBB-CCCC-9999-ABCDEF123456%7Dbook.mp3",
                content_type="audio/mp3",
                body=c.read(),
            )

    @responses.activate
    def test_mock_libby_download_audiobook_odm(self):
        settings_folder = self._generate_fake_settings()
        self._setup_audiobook_direct_responses()
        with self.test_data_dir.joinpath("audiobook", "book.odm").open(
            "r", encoding="utf-8"
        ) as b:
            responses.get(
                "https://sentry-read.svc.overdrive.com/card/123456789/loan/9999999/fulfill/audiobook-mp3",
                content_type="application/xml",
                body=b.read(),
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
        for mp3 in ("book3/01_ceremonies_herrick_cjph_64kb.mp3",):
            with odm_test_data_dir.joinpath(mp3).open("rb") as m:
                responses.get(
                    f"https://ping.github.io/odmpy/test_data/{mp3}",
                    content_type="audio/mp3",
                    body=m.read(),
                )

        test_folder = "test"

        run_command = [
            "libby",
            "--settings",
            str(settings_folder),
            "--downloaddir",
            str(self.test_downloads_dir),
            "--bookfolderformat",
            test_folder,
            "--bookfileformat",
            "ebook",
            "--select",
            "1",
            "--opf",
            "--merge",
            "--chapters",
            "--hideprogress",
            "--writejson",
        ]
        if self.is_verbose:
            run_command.insert(0, "--verbose")
        run(run_command, be_quiet=not self.is_verbose)

        mp3_filepath = self.test_downloads_dir.joinpath(test_folder, "ebook.mp3")
        self.assertTrue(mp3_filepath.exists())
        audio_file = MP3(mp3_filepath, ID3=ID3)
        self.assertEqual(audio_file.tags["TIT2"].text[0], "Ceremonies For Christmas")
        self.assertEqual(audio_file.tags["TALB"].text[0], "Ceremonies For Christmas")
        self.assertEqual(audio_file.tags["TPE1"].text[0], "Robert Herrick")
        self.assertEqual(audio_file.tags["TPE2"].text[0], "Robert Herrick")
        self.assertEqual(audio_file.tags["TPE3"].text[0], "LibriVox Volunteers")
        self.assertEqual(audio_file.tags["TPUB"].text[0], "Librivox")
        self.assertTrue(audio_file.tags["CTOC:toc"])
        chapters = [t for t in audio_file.tags.getall("CHAP")]

        for i, chapter in enumerate(chapters):
            # check tags are written in time sequence for merged files
            # because ffmpeg conversion from mp3 to m4b bugs out when
            # CHAPs are not written out in time sequence
            # https://github.com/quodlibet/mutagen/issues/506
            if i > 0:
                self.assertGreater(chapter.start_time, chapters[i - 1].start_time)

        self.assertEqual(audio_file.tags.version[1], 4)
        self.assertEqual(audio_file.tags["TLAN"].text[0], "eng")
        self.assertTrue(
            self.test_downloads_dir.joinpath(test_folder, "ebook.opf").exists()
        )
        self.assertTrue(
            self.test_downloads_dir.joinpath(test_folder, "debug.json").exists()
        )

    @responses.activate
    def test_mock_libby_download_audiobook_direct(self):
        settings_folder = self._generate_fake_settings()
        self._setup_audiobook_direct_responses()
        test_folder = "test"

        run_command = [
            "libby",
            "--settings",
            str(settings_folder),
            "--downloaddir",
            str(self.test_downloads_dir),
            "--bookfolderformat",
            test_folder,
            "--bookfileformat",
            "ebook",
            "--direct",
            "--select",
            "1",
            "--chapters",
            "--overwritetags",
            "--id3v2version",
            "3",
            "--opf",
            "--hideprogress",
            "--debug",
            "--writejson",
        ]
        if self.is_verbose:
            run_command.insert(0, "--verbose")
        run(run_command, be_quiet=not self.is_verbose)
        part_files = self.test_downloads_dir.joinpath(test_folder).glob("*part-*.mp3")
        self.assertTrue(part_files)
        self.assertTrue(
            self.test_downloads_dir.joinpath(test_folder, "test-audiobook.opf").exists()
        )

        with self.test_data_dir.joinpath("audiobook", "sync.json").open(
            "r", encoding="utf-8"
        ) as f:
            loan = json.load(f)["loans"][0]

        # book only has 1 part
        with self.test_data_dir.joinpath("audiobook", "openbook.json").open(
            "r", encoding="utf-8"
        ) as o:
            openbook = json.load(o)
            markers = [toc["title"] for toc in openbook["nav"]["toc"]]

        for part_file in part_files:
            audio_file = MP3(part_file, ID3=ID3)
            self.assertEqual(audio_file.tags["TIT2"].text[0], loan["title"])
            self.assertEqual(audio_file.tags["TALB"].text[0], loan["title"])
            self.assertEqual(audio_file.tags["TPE1"].text[0], loan["firstCreatorName"])
            self.assertEqual(audio_file.tags["TPE2"].text[0], loan["firstCreatorName"])
            self.assertEqual(
                audio_file.tags["TPE3"].text[0],
                [c for c in openbook["creator"] if c["role"] == "narrator"][0]["name"],
            )
            self.assertEqual(
                audio_file.tags["TPUB"].text[0], loan["publisherAccount"]["name"]
            )
            self.assertEqual(
                audio_file.tags["TXXX:ISBN"].text[0],
                [f for f in loan["formats"] if f.get("isbn")][0]["isbn"],
            )
            self.assertEqual(audio_file.tags.version[1], 3)
            self.assertEqual(audio_file.tags["TLAN"].text[0], "eng")
            self.assertTrue(audio_file.tags["CTOC:toc"])
            # check chapters are generated in sequence
            for i, chap_id in enumerate(audio_file.tags["CTOC:toc"].child_element_ids):
                self.assertEqual(chap_id, f"ch{i:02d}")
                chapter = audio_file.tags[f"CHAP:{chap_id}"]
                self.assertEqual(chapter.sub_frames["TIT2"].text[0], markers[i])
                if i > 0:
                    prev_chapter = audio_file.tags[
                        f'CHAP:{audio_file.tags["CTOC:toc"].child_element_ids[i - 1]}'
                    ]
                    self.assertGreater(chapter.start_time, prev_chapter.start_time)
                    self.assertEqual(chapter.start_time, prev_chapter.end_time)

        # test for debug artifacts here as well
        for f in ("loan.json", "openbook.json", "debug.json"):
            self.assertTrue(self.test_downloads_dir.joinpath(test_folder, f).exists())

    @responses.activate
    def test_mock_libby_download_audiobook_direct_merge(self):
        settings_folder = self._generate_fake_settings()
        self._setup_audiobook_direct_responses()

        test_folder = "test"

        run_command = [
            "libby",
            "--settings",
            str(settings_folder),
            "--downloaddir",
            str(self.test_downloads_dir),
            "--bookfolderformat",
            test_folder,
            "--bookfileformat",
            "ebook",
            "--direct",
            "--select",
            "1",
            "--merge",
            "--chapters",
            "--overwritetags",
            "--opf",
            "--hideprogress",
        ]
        if self.is_verbose:
            run_command.insert(0, "--verbose")
        run(run_command, be_quiet=not self.is_verbose)
        self.assertTrue(
            self.test_downloads_dir.joinpath(test_folder, "ebook.opf").exists()
        )
        mp3_filepath = self.test_downloads_dir.joinpath(test_folder, "ebook.mp3")
        self.assertTrue(mp3_filepath.exists())

        with self.test_data_dir.joinpath("audiobook", "sync.json").open(
            "r", encoding="utf-8"
        ) as f:
            loan = json.load(f)["loans"][0]

        # book only has 1 part
        with self.test_data_dir.joinpath("audiobook", "openbook.json").open(
            "r", encoding="utf-8"
        ) as o:
            openbook = json.load(o)
            markers = [toc["title"] for toc in openbook["nav"]["toc"]]

        audio_file = MP3(mp3_filepath, ID3=ID3)
        self.assertEqual(audio_file.tags["TIT2"].text[0], loan["title"])
        self.assertEqual(audio_file.tags["TALB"].text[0], loan["title"])
        self.assertEqual(audio_file.tags["TPE1"].text[0], loan["firstCreatorName"])
        self.assertEqual(audio_file.tags["TPE2"].text[0], loan["firstCreatorName"])
        self.assertEqual(
            audio_file.tags["TPE3"].text[0],
            [c for c in openbook["creator"] if c["role"] == "narrator"][0]["name"],
        )
        self.assertEqual(
            audio_file.tags["TPUB"].text[0], loan["publisherAccount"]["name"]
        )
        self.assertEqual(
            audio_file.tags["TXXX:ISBN"].text[0],
            [f for f in loan["formats"] if f.get("isbn")][0]["isbn"],
        )
        self.assertTrue(audio_file.tags["CTOC:toc"])
        chapters = [t for t in audio_file.tags.getall("CHAP")]
        self.assertEqual(len(markers), len(chapters))

        for i, chapter in enumerate(chapters):
            # check tags are written in time sequence for merged files
            # because ffmpeg conversion from mp3 to m4b bugs out when
            # CHAPs are not written out in time sequence
            # https://github.com/quodlibet/mutagen/issues/506
            self.assertEqual(chapter.sub_frames["TIT2"].text[0], markers[i])
            if i > 0:
                self.assertGreater(chapter.start_time, chapters[i - 1].start_time)

    @responses.activate
    def test_mock_libby_download_audiobook_direct_merge_m4b(self):
        settings_folder = self._generate_fake_settings()
        self._setup_audiobook_direct_responses()

        test_folder = "test"

        run_command = [
            "libby",
            "--settings",
            str(settings_folder),
            "--downloaddir",
            str(self.test_downloads_dir),
            "--bookfolderformat",
            test_folder,
            "--bookfileformat",
            "ebook",
            "--direct",
            "--select",
            "1",
            "--merge",
            "--mergeformat",
            "m4b",
            "--chapters",
            "--overwritetags",
            "--opf",
            "--hideprogress",
        ]
        if self.is_verbose:
            run_command.insert(0, "--verbose")
        run(run_command, be_quiet=not self.is_verbose)
        self.assertTrue(
            self.test_downloads_dir.joinpath(test_folder, "ebook.m4b").exists()
        )
        self.assertTrue(
            self.test_downloads_dir.joinpath(test_folder, "ebook.opf").exists()
        )

    @responses.activate
    def test_mock_libby_exportloans(self):
        """
        `odmpy libby --exportloans`
        """
        settings_folder = self._generate_fake_settings()
        self._setup_audiobook_direct_responses()

        loans_file_name = self.test_downloads_dir.joinpath(
            f"test_loans_{int(datetime.utcnow().timestamp()*1000)}.json"
        )
        run(
            [
                "libby",
                "--settings",
                str(settings_folder),
                "--exportloans",
                str(loans_file_name),
            ],
            be_quiet=True,
        )
        self.assertTrue(loans_file_name.exists())
        with loans_file_name.open("r", encoding="utf-8") as f:
            loans = json.load(f)
            for loan in loans:
                self.assertIn("id", loan)

    @responses.activate
    def test_mock_libby_noaudiobooks(self):
        """
        `odmpy libby --exportloans --noaudiobooks`
        """
        settings_folder = self._generate_fake_settings()
        self._setup_audiobook_direct_responses()

        loans_file_name = self.test_downloads_dir.joinpath(
            f"test_loans_{int(datetime.utcnow().timestamp()*1000)}.json"
        )
        run(
            [
                "libby",
                "--settings",
                str(settings_folder),
                "--exportloans",
                str(loans_file_name),
                "--noaudiobooks",
            ],
            be_quiet=True,
        )
        self.assertTrue(loans_file_name.exists())
        with loans_file_name.open("r", encoding="utf-8") as f:
            loans = json.load(f)
            self.assertEqual(len(loans), 0)

    @staticmethod
    def _libby_setup_prompt(text: str) -> str:
        if "Enter the 8-digit Libby code and press enter" in text:
            return "12345678"
        return ""

    @responses.activate
    @patch("builtins.input", new=_libby_setup_prompt.__func__)  # type: ignore[attr-defined]
    def test_mock_libby_setup(self):
        settings_folder = self.test_downloads_dir.joinpath("settings")
        if not settings_folder.exists():
            settings_folder.mkdir(parents=True, exist_ok=True)
        responses.post(
            "https://sentry-read.svc.overdrive.com/chip?client=dewey",
            content_type="application/json",
            json={"chip": "xxx", "identity": "xxxx"},
        )
        responses.post(
            "https://sentry-read.svc.overdrive.com/chip/clone/code",
            content_type="applications/json",
            json={},
        )
        self._setup_audiobook_direct_responses()
        with self.assertLogs(run.__module__, level="INFO") as context:
            run(["libby", "--settings", str(settings_folder)], be_quiet=True)
        self.assertIn("Login successful.\n", [r.msg for r in context.records])

    @responses.activate
    @patch("builtins.input", new=_libby_setup_prompt.__func__)  # type: ignore[attr-defined]
    def test_mock_libby_setup_fail(self):
        settings_folder = self.test_downloads_dir.joinpath("settings")
        if not settings_folder.exists():
            settings_folder.mkdir(parents=True, exist_ok=True)
        responses.post(
            "https://sentry-read.svc.overdrive.com/chip?client=dewey",
            content_type="application/json",
            json={"chip": "xxx", "identity": "xxxx"},
        )
        responses.post(
            "https://sentry-read.svc.overdrive.com/chip/clone/code",
            content_type="applications/json",
            status=HTTPStatus.BAD_REQUEST,
            json={},
        )
        with self.assertRaisesRegex(OdmpyRuntimeError, "Could not log in with code"):
            run(["libby", "--settings", str(settings_folder)], be_quiet=True)

    @responses.activate
    @patch("builtins.input", new=_libby_setup_prompt.__func__)  # type: ignore[attr-defined]
    def test_mock_libby_setup_sync_fail(self):
        settings_folder = self.test_downloads_dir.joinpath("settings")
        if not settings_folder.exists():
            settings_folder.mkdir(parents=True, exist_ok=True)
        responses.post(
            "https://sentry-read.svc.overdrive.com/chip?client=dewey",
            content_type="application/json",
            json={"chip": "xxx", "identity": "xxxx"},
        )
        responses.post(
            "https://sentry-read.svc.overdrive.com/chip/clone/code",
            content_type="applications/json",
            json={},
        )
        responses.get(
            "https://sentry-read.svc.overdrive.com/chip/sync",
            content_type="applications/json",
            json={},
        )
        with self.assertRaisesRegex(
            OdmpyRuntimeError, "at least 1 registered library card"
        ):
            run(["libby", "--settings", str(settings_folder)], be_quiet=True)

    @responses.activate
    @patch("builtins.input", new=lambda _: "")
    def test_mock_inputs_nodownloads(self):
        settings_folder = self._generate_fake_settings()
        with self.test_data_dir.joinpath("magazine", "sync.json").open(
            "r", encoding="utf-8"
        ) as s:
            responses.get(
                "https://sentry-read.svc.overdrive.com/chip/sync", json=json.load(s)
            )
        with self.assertLogs(run.__module__, level="INFO") as context:
            run(["libby", "--settings", str(settings_folder)], be_quiet=True)
        self.assertIn("No downloadable loans found.", [r.msg for r in context.records])

    @responses.activate
    @patch("builtins.input", new=lambda _: "1")
    def test_mock_inputs_loans_found(self):
        settings_folder = self._generate_fake_settings()
        self._setup_audiobook_direct_responses()
        test_folder = "test"

        run_command = [
            "libby",
            "--settings",
            str(settings_folder),
            "--downloaddir",
            str(self.test_downloads_dir),
            "--bookfolderformat",
            test_folder,
            "--bookfileformat",
            "ebook",
            "--direct",
            "--hideprogress",
        ]
        with self.assertLogs(run.__module__, level="INFO") as context:
            run(run_command, be_quiet=True)
        self.assertIn("INFO:odmpy.odm:Found 1 loan.", context.output)

    @responses.activate
    def test_mock_settings(self):
        settings_folder = self.test_downloads_dir.joinpath("settings")
        if not settings_folder.exists():
            settings_folder.mkdir(parents=True, exist_ok=True)
        with self.assertRaises(LibbyNotConfiguredError):
            run(["libby", "--settings", str(settings_folder), "--check"], be_quiet=True)

        with self.assertRaises(OdmpyRuntimeError):
            run(
                [
                    "libby",
                    "--settings",
                    str(settings_folder),
                    "--exportloans",
                    str(self.test_downloads_dir.joinpath("x.json")),
                ],
                be_quiet=True,
            )

        with self.test_data_dir.joinpath("magazine", "sync.json").open(
            "r", encoding="utf-8"
        ) as s:
            responses.get(
                "https://sentry-read.svc.overdrive.com/chip/sync", json=json.load(s)
            )
        # generate fake settings
        libby_settings = settings_folder.joinpath("libby.json")
        with libby_settings.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "chip": "12345",
                    "identity": "abcdefgh",
                    "syncable": False,
                    "primary": True,
                    "__odmpy_sync_code": "12345678",
                },
                f,
            )
        run_command = ["libby", "--settings", str(settings_folder), "--check"]
        run(run_command, be_quiet=True)
        with libby_settings.open("r", encoding="utf-8") as f:
            settings = json.load(f)
            self.assertNotIn("__odmpy_sync_code", settings)
            self.assertIn("__libby_sync_code", settings)

    @responses.activate
    @patch("builtins.input", new=lambda _: "1")
    def test_mock_libby_return(self):
        settings_folder = self._generate_fake_settings()
        with self.test_data_dir.joinpath("audiobook", "sync.json").open(
            "r", encoding="utf-8"
        ) as f:
            responses.get(
                "https://sentry-read.svc.overdrive.com/chip/sync",
                content_type="application/json",
                json=json.load(f),
            )
            responses.delete(
                "https://sentry-read.svc.overdrive.com/card/123456789/loan/9999999",
                content_type="application/json",
                json={},
            )

        run_command = ["libbyreturn", "--settings", str(settings_folder)]
        if self.is_verbose:
            run_command.insert(0, "--verbose")
        run(run_command, be_quiet=not self.is_verbose)

    @responses.activate
    @patch("builtins.input", new=lambda _: "1")
    def test_mock_libby_renew(self):
        settings_folder = self._generate_fake_settings()
        with self.test_data_dir.joinpath("audiobook", "sync.json").open(
            "r", encoding="utf-8"
        ) as f:
            sync_state = json.load(f)
            responses.get(
                "https://sentry-read.svc.overdrive.com/chip/sync",
                content_type="application/json",
                json=sync_state,
            )
            responses.put(
                "https://sentry-read.svc.overdrive.com/card/123456789/loan/9999999",
                content_type="application/json",
                json=sync_state["loans"][0],
            )

        run_command = ["libbyrenew", "--settings", str(settings_folder)]
        if self.is_verbose:
            run_command.insert(0, "--verbose")
        run(run_command, be_quiet=not self.is_verbose)

    @staticmethod
    def _ret_libby_renew_failure(_: str) -> str:
        counter_name = "renew_failure"
        if OdmpyLibbyTests.get_counter(counter_name) == 0:
            OdmpyLibbyTests.add_to_counter(counter_name)
            return "1"
        if OdmpyLibbyTests.get_counter(counter_name) == 1:
            OdmpyLibbyTests.add_to_counter(counter_name)
            return "y"
        return ""

    @responses.activate
    @patch("builtins.input", new=_ret_libby_renew_failure.__func__)  # type: ignore[attr-defined]
    def test_mock_libby_renew_failure(self):
        settings_folder = self._generate_fake_settings()
        with self.test_data_dir.joinpath("audiobook", "sync.json").open(
            "r", encoding="utf-8"
        ) as f:
            sync_state = json.load(f)
            responses.get(
                "https://sentry-read.svc.overdrive.com/chip/sync",
                content_type="application/json",
                json=sync_state,
            )
            responses.put(
                "https://sentry-read.svc.overdrive.com/card/123456789/loan/9999999",
                content_type="application/json",
                json={
                    "result": "upstream_failure",
                    "upstream": {
                        "userExplanation": "TestRenewFailure",
                        "errorCode": "999",
                    },
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            responses.post(
                "https://sentry-read.svc.overdrive.com/card/123456789/hold/9999999",
                content_type="application/json",
                match=[
                    matchers.json_params_matcher(
                        {"days_to_suspend": 0, "email_address": ""}
                    )
                ],
                json={
                    "title": "Test Audiobook",
                    "holdListPosition": 2,
                    "ownedCopies": 10,
                    "estimatedWaitDays": 21,
                },
            )

        run_command = ["libbyrenew", "--settings", str(settings_folder)]
        if self.is_verbose:
            run_command.insert(0, "--verbose")

        with self.assertLogs(run.__module__, level="INFO") as context:
            run(run_command, be_quiet=not self.is_verbose)

        self.assertTrue(
            [r.msg for r in context.records if r.msg.startswith("Renewing loan")]
        )
        self.assertTrue(
            [
                r.msg
                for r in context.records
                if r.msg.startswith("Hold successfully created for")
            ]
        )

    @staticmethod
    def _ret_invalid_choice(text: str) -> str:
        counter_name = "invalid_choice"
        if "Choose from" in text and OdmpyLibbyTests.get_counter(counter_name) == 0:
            OdmpyLibbyTests.add_to_counter(counter_name)
            return "x"
        return ""

    @responses.activate
    @patch("builtins.input", new=_ret_invalid_choice.__func__)  # type: ignore[attr-defined]
    def test_mock_libby_invalid_choice(self):
        settings_folder = self._generate_fake_settings()
        with self.test_data_dir.joinpath("audiobook", "sync.json").open(
            "r", encoding="utf-8"
        ) as f:
            responses.get(
                "https://sentry-read.svc.overdrive.com/chip/sync",
                content_type="application/json",
                json=json.load(f),
            )
            responses.delete(
                "https://sentry-read.svc.overdrive.com/card/123456789/loan/9999999",
                content_type="application/json",
                json={},
            )

        run_command = ["libbyreturn", "--settings", str(settings_folder)]
        if self.is_verbose:
            run_command.insert(0, "--verbose")
        run(run_command, be_quiet=not self.is_verbose)

    @responses.activate
    def test_mock_libby_download_by_selectid(self):
        settings_folder = self._generate_fake_settings()

        with self.test_data_dir.joinpath("ebook", "sync.json").open(
            "r", encoding="utf-8"
        ) as s:
            responses.get(
                "https://sentry-read.svc.overdrive.com/chip/sync", json=json.load(s)
            )
        with self.test_data_dir.joinpath("ebook", "ebook.acsm").open(
            "r", encoding="utf-8"
        ) as a:
            responses.get(
                "https://sentry-read.svc.overdrive.com/card/123456789/loan/9999999/fulfill/ebook-epub-adobe",
                content_type="application/xml",
                body=a.read(),
            )

        test_folder = "test"

        run_command = [
            "libby",
            "--settings",
            str(settings_folder),
            "--ebooks",
            "--downloaddir",
            str(self.test_downloads_dir),
            "--bookfolderformat",
            test_folder,
            "--bookfileformat",
            "ebook_%(ID)s",
            "--selectid",
            "9999999",
            "--hideprogress",
        ]
        if self.is_verbose:
            run_command.insert(0, "--verbose")
        run(run_command, be_quiet=not self.is_verbose)
        self.assertTrue(
            self.test_downloads_dir.joinpath(test_folder, "ebook_9999999.acsm").exists()
        )

    @responses.activate
    def test_mock_libby_issue_42_odm(self):
        settings_folder = self._generate_fake_settings()
        self._setup_audiobook_direct_responses()
        with self.test_data_dir.joinpath("audiobook", "book.odm").open(
            "r", encoding="utf-8"
        ) as b:
            responses.get(
                "https://sentry-read.svc.overdrive.com/card/123456789/loan/9999999/fulfill/audiobook-mp3",
                content_type="application/xml",
                body=b.read(),
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
        for mp3 in ("book3/01_ceremonies_herrick_cjph_64kb.mp3",):
            with odm_test_data_dir.joinpath(mp3).open("rb") as m:
                responses.get(
                    f"https://ping.github.io/odmpy/test_data/{mp3}",
                    content_type="audio/mp3",
                    body=m.read(),
                )

        test_folder = "test"

        run_command = [
            "libby",
            "--settings",
            str(settings_folder),
            "--downloaddir",
            str(self.test_downloads_dir),
            "--bookfolderformat",
            test_folder,
            "--bookfileformat",
            "ebook",
            "--latest",
            "10",
            "--hideprogress",
        ]
        if self.is_verbose:
            run_command.insert(0, "--verbose")
        run(run_command, be_quiet=not self.is_verbose)
        part_files = self.test_downloads_dir.joinpath(test_folder).glob("*part-*.mp3")

        run1_modfified_time = 0
        for part in part_files:
            run1_modfified_time = os.path.getmtime(part)
        self.assertTrue(run1_modfified_time)

        # delay before second run to ensure that some time has elapsed
        time.sleep(1.5)
        run(run_command, be_quiet=not self.is_verbose)

        part_files = self.test_downloads_dir.joinpath(test_folder).glob("*part-*.mp3")

        run2_modfified_time = 0
        for part in part_files:
            run2_modfified_time = os.path.getmtime(part)
        self.assertTrue(run2_modfified_time)

        self.assertEqual(run1_modfified_time, run2_modfified_time)

    @responses.activate
    def test_mock_libby_issue_42_direct(self):
        settings_folder = self._generate_fake_settings()
        self._setup_audiobook_direct_responses()

        test_folder = "test"

        run_command = [
            "libby",
            "--settings",
            str(settings_folder),
            "--downloaddir",
            str(self.test_downloads_dir),
            "--bookfolderformat",
            test_folder,
            "--bookfileformat",
            "ebook",
            "--direct",
            "--latest",
            "10",
            "--hideprogress",
        ]
        if self.is_verbose:
            run_command.insert(0, "--verbose")
        run(run_command, be_quiet=not self.is_verbose)
        part_files = self.test_downloads_dir.joinpath(test_folder).glob("*part-*.mp3")

        run1_modfified_time = 0
        for part in part_files:
            run1_modfified_time = os.path.getmtime(part)
        self.assertTrue(run1_modfified_time)

        # delay before second run to ensure that some time has elapsed
        time.sleep(1.5)
        run(run_command, be_quiet=not self.is_verbose)

        part_files = self.test_downloads_dir.joinpath(test_folder).glob("*part-*.mp3")

        run2_modfified_time = 0
        for part in part_files:
            run2_modfified_time = os.path.getmtime(part)
        self.assertTrue(run2_modfified_time)

        self.assertEqual(run1_modfified_time, run2_modfified_time)

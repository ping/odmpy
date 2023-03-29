import argparse
from functools import cmp_to_key

from odmpy.processing import shared
from odmpy.processing.ebook import _sort_title_contents
from tests.base import BaseTestCase


class ProcessingSharedTests(BaseTestCase):
    def test_extract_authors_from_openbook(self):
        openbook_mock = {
            "creator": [
                {"name": "A", "role": "author"},
                {"name": "B", "role": "editor"},
            ]
        }
        self.assertEqual(shared.extract_authors_from_openbook(openbook_mock), ["A"])
        openbook_mock = {
            "creator": [
                {"name": "B", "role": "editor"},
                {"name": "B2", "role": "editor"},
                {"name": "C", "role": "publisher"},
            ]
        }
        self.assertEqual(
            shared.extract_authors_from_openbook(openbook_mock), ["B", "B2"]
        )
        openbook_mock = {
            "creator": [
                {"name": "C", "role": "publisher"},
            ]
        }
        self.assertEqual(shared.extract_authors_from_openbook(openbook_mock), ["C"])

    def test_extract_isbn(self):
        formats = [
            {
                "identifiers": [
                    {"value": "9780000000000", "type": "ISBN"},
                    {"value": "tantor_audio#9780000000000", "type": "8"},
                    {"value": "9780000000001", "type": "LibraryISBN"},
                ],
                "isbn": "9780000000001",
                "id": "audiobook-overdrive",
            },
            {
                "identifiers": [
                    {"value": "9780000000000", "type": "ISBN"},
                    {"value": "tantor_audio#9780000000000", "type": "8"},
                    {"value": "9780000000001", "type": "LibraryISBN"},
                ],
                "isbn": "9780000000001",
                "id": "audiobook-mp3",
            },
        ]
        self.assertEqual(
            shared.extract_isbn(formats, ["audiobook-mp3"]), "9780000000001"
        )
        formats = [
            {
                "identifiers": [
                    {"value": "9780000000000", "type": "ISBN"},
                    {"value": "9780000000001", "type": "LibraryISBN"},
                ],
                "id": "audiobook-mp3",
            }
        ]
        self.assertEqual(
            shared.extract_isbn(formats, ["audiobook-mp3"]), "9780000000001"
        )
        formats = [
            {
                "identifiers": [
                    {"value": "9780000000000", "type": "ISBN"},
                    {"value": "9780000000001", "type": "X"},
                ],
                "id": "audiobook-mp3",
            }
        ]
        self.assertEqual(
            shared.extract_isbn(formats, ["audiobook-mp3"]), "9780000000000"
        )

    def test_generate_names(self):
        args = argparse.Namespace(
            book_file_format="%(Title)s - %(Author)s",
            book_folder_format="%(Title)s - %(Author)s",
            download_dir=str(self.test_downloads_dir),
            no_book_folder=False,
        )
        book_folder, book_file_name = shared.generate_names(
            title="Test Title",
            series="",
            authors=["Author1", "Author2"],
            edition="",
            title_id="",
            args=args,
            logger=self.logger,
        )
        self.assertEqual(book_folder.stem, "Test Title - Author1, Author2")
        self.assertEqual(book_file_name.name, "Test Title - Author1, Author2.mp3")

        authors = [f"Test Author {i}" for i in range(1, 50)]
        book_folder, book_file_name = shared.generate_names(
            title="Test Title",
            series="",
            authors=authors,
            edition="",
            title_id="",
            args=args,
            logger=self.logger,
        )
        self.assertEqual(book_folder.stem, f"Test Title - {authors[0]}")
        self.assertEqual(book_file_name.name, f"Test Title - {authors[0]}.mp3")

    def test_sort_title_contents(self):
        entries = [
            {"url": "http://localhost/assets/3.jpg"},
            {"url": "http://localhost/assets/4.css"},
            {"url": "http://localhost/pages/2.xhtml?cmpt=12345"},
            {"url": "http://localhost/pages/1.xhtml?cmpt=12345"},
        ]

        sorted_entries = sorted(entries, key=cmp_to_key(_sort_title_contents))
        self.assertEqual(
            sorted_entries,
            [
                {"url": "http://localhost/pages/1.xhtml?cmpt=12345"},
                {"url": "http://localhost/pages/2.xhtml?cmpt=12345"},
                {"url": "http://localhost/assets/3.jpg"},
                {"url": "http://localhost/assets/4.css"},
            ],
        )

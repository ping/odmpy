import unittest

from odmpy.processing import shared


class ProcessingSharedTests(unittest.TestCase):
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

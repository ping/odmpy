from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class ExpectedResult:
    book_folder: Path
    merged_book_basename: str
    mp3_name_format: str
    total_parts: int
    total_chapters: int
    chapter_durations_sec: List[int]


def get_expected_result(test_downloads_dir: Path, test_file: str) -> ExpectedResult:
    return ExpectedResult(
        book_folder=test_downloads_dir.joinpath(book_folders[test_file]),
        merged_book_basename=merged_book_basenames[test_file],
        mp3_name_format=mp3_name_formats[test_file],
        total_parts=book_parts[test_file],
        total_chapters=book_chapters[test_file],
        chapter_durations_sec=book_chapter_durations[test_file],
    )


book_folders = {
    "test1.odm": "Ceremonies For Christmas - Robert Herrick",
    "test2.odm": "크리스마스를 위한 의식 - 로버트 Herrick",
    "test3.odm": "Ceremonies For Christmas - Robert Herrick",
    "test4.odm": "Ceremonies For Christmas - Robert Herrick",
    "test_ref24.odm": "Ceremonies For Christmas - Robert Herrick",
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
    ],
    "test2.odm": [
        "마커 1",
        "마커 2",
        "마커 3",
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
    "test1.odm": 3,
    "test2.odm": 3,
    "test3.odm": 1,
    "test4.odm": 1,
    "test_ref24.odm": 1,
}
book_chapters = {
    "test1.odm": 3,
    "test2.odm": 3,
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

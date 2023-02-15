import json
import os.path
import shutil
import unittest
import warnings
from datetime import datetime

from odmpy.odm import run


# Test non-interactive options
class OdmpyLibbyTests(unittest.TestCase):
    def setUp(self) -> None:
        warnings.filterwarnings(
            action="ignore", message="unclosed", category=ResourceWarning
        )
        self.test_data_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data"
        )
        self.test_downloads_dir = os.path.join(self.test_data_dir, "downloads")
        if not os.path.isdir(self.test_downloads_dir):
            os.makedirs(self.test_downloads_dir)

    def tearDown(self) -> None:
        if os.path.isdir(self.test_downloads_dir):
            shutil.rmtree(self.test_downloads_dir, ignore_errors=True)

    def test_libby_export(self):
        if run(["libby", "--check"], be_quiet=True):
            self.skipTest("Libby not setup.")

        loans_file_name = os.path.join(
            self.test_downloads_dir,
            f"test_loans_{int(datetime.utcnow().timestamp()*1000)}.json",
        )
        run(["libby", "--exportloans", loans_file_name], be_quiet=True)
        self.assertTrue(os.path.exists(loans_file_name))
        with open(loans_file_name, "r", encoding="utf-8") as f:
            loans = json.load(f)
            for loan in loans:
                self.assertIn("id", loan)

    @unittest.skip("Takes too long")  # turn off at will
    def test_libby_download_select(self):
        if run(["libby", "--check"], be_quiet=True):
            self.skipTest("Libby not setup.")

        ts = int(datetime.utcnow().timestamp() * 1000)
        loans_file_name = os.path.join(self.test_downloads_dir, f"test_loans_{ts}.json")
        download_folder = os.path.join(self.test_downloads_dir, f"test_downloads_{ts}")
        os.makedirs(download_folder)
        run(["libby", "--exportloans", loans_file_name], be_quiet=True)
        self.assertTrue(os.path.exists(loans_file_name))
        with open(loans_file_name, "r", encoding="utf-8") as f:
            loans = json.load(f)
        if not loans:
            return
        run(
            [
                "libby",
                "--downloaddir",
                download_folder,
                "--select",
                str(len(loans)),
            ],
            be_quiet=True,
        )

    @unittest.skip("Takes too long")  # turn off at will
    def test_libby_download_latest(self):
        if run(["libby", "--check"], be_quiet=True):
            self.skipTest("Libby not setup.")

        download_folder = os.path.join(
            self.test_downloads_dir,
            f"test_downloads_{int(datetime.utcnow().timestamp() * 1000)}",
        )
        os.makedirs(download_folder)
        run(
            ["libby", "--downloaddir", download_folder, "--latest", "1"],
            be_quiet=True,
        )

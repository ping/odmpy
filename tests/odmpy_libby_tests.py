import glob
import json
import os.path
import shutil
import unittest
import warnings
from datetime import datetime

from odmpy.errors import LibbyNotConfiguredError
from odmpy.libby import LibbyClient, LibbyFormats
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
        """
        `odmpy libby --exportloans`
        """
        try:
            run(["libby", "--check"], be_quiet=True)
        except LibbyNotConfiguredError:
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
        loans_file_name = os.path.join(self.test_downloads_dir, f"test_loans_{ts}.json")
        download_folder = os.path.join(self.test_downloads_dir, f"test_downloads_{ts}")
        os.makedirs(download_folder)
        run(["libby", "--exportloans", loans_file_name], be_quiet=True)
        self.assertTrue(os.path.exists(loans_file_name))
        with open(loans_file_name, "r", encoding="utf-8") as f:
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
                    download_folder,
                    "--select",
                    str(len(loans)),
                    "--hideprogress",
                ],
                be_quiet=True,
            )
        except KeyboardInterrupt:
            self.fail("Test aborted")

        self.assertTrue(glob.glob(f"{download_folder}/*/*.mp3"))

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
        loans_file_name = os.path.join(self.test_downloads_dir, f"test_loans_{ts}.json")
        download_folder = os.path.join(self.test_downloads_dir, f"test_downloads_{ts}")
        os.makedirs(download_folder)
        run(["libby", "--exportloans", loans_file_name], be_quiet=True)
        self.assertTrue(os.path.exists(loans_file_name))
        with open(loans_file_name, "r", encoding="utf-8") as f:
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
                    download_folder,
                    "--latest",
                    "1",
                    "--hideprogress",
                ],
                be_quiet=True,
            )
        except KeyboardInterrupt:
            self.fail("Test aborted")

        self.assertTrue(glob.glob(f"{download_folder}/*/*.mp3"))

    @unittest.skip("Takes too long")  # turn on/off at will
    def test_libby_download_ebook(self):
        """
        `odmpy libby --ebooks --select N`
        """
        try:
            run(["libby", "--check"], be_quiet=True)
        except LibbyNotConfiguredError:
            self.skipTest("Libby not setup.")
        ts = int(datetime.utcnow().timestamp() * 1000)
        loans_file_name = os.path.join(self.test_downloads_dir, f"test_loans_{ts}.json")
        download_folder = os.path.join(self.test_downloads_dir, f"test_downloads_{ts}")
        os.makedirs(download_folder)
        run(["libby", "--ebooks", "--exportloans", loans_file_name], be_quiet=True)
        self.assertTrue(os.path.exists(loans_file_name))
        with open(loans_file_name, "r", encoding="utf-8") as f:
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
                    "--downloaddir",
                    download_folder,
                    "--select",
                    str(selected_index),
                ],
                be_quiet=True,
            )
        except KeyboardInterrupt:
            self.fail("Test aborted")

        acsm_file = glob.glob(f"{download_folder}/*/*.acsm")
        self.assertTrue(acsm_file)

    @unittest.skip("Takes too long")  # turn on/off at will
    def test_libby_download_ebook_direct(self):
        """
        `odmpy libby --ebooks --select N`
        """
        try:
            run(["libby", "--check"], be_quiet=True)
        except LibbyNotConfiguredError:
            self.skipTest("Libby not setup.")
        ts = int(datetime.utcnow().timestamp() * 1000)
        loans_file_name = os.path.join(self.test_downloads_dir, f"test_loans_{ts}.json")
        download_folder = os.path.join(self.test_downloads_dir, f"test_downloads_{ts}")
        os.makedirs(download_folder)
        run(["libby", "--ebooks", "--exportloans", loans_file_name], be_quiet=True)
        self.assertTrue(os.path.exists(loans_file_name))
        with open(loans_file_name, "r", encoding="utf-8") as f:
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
                    download_folder,
                    "--select",
                    str(selected_index),
                    # "--hideprogress",
                ],
                be_quiet=True,
            )
        except KeyboardInterrupt:
            self.fail("Test aborted")

        epub_file = glob.glob(f"{download_folder}/*/*.epub")
        self.assertTrue(epub_file)

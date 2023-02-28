# Copyright (C) 2023 github.com/ping
#
# This file is part of odmpy.
#
# odmpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# odmpy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with odmpy.  If not, see <http://www.gnu.org/licenses/>.
#
import argparse
from enum import Enum

#
# Stuff for the CLI
#


class OdmpyCommands(str, Enum):
    """
    Command strings
    """

    Information = "info"
    Download = "dl"
    Return = "ret"
    Libby = "libby"
    LibbyReturn = "libbyreturn"
    LibbyRenew = "libbyrenew"

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        # to ensure that proper values are printed out in arg command_name error help
        return str(self.value)


class OdmpyNoninteractiveOptions(str, Enum):
    """
    Non-interactive arguments
    """

    DownloadLatestN = "download_latest_n"
    DownloadSelectedN = "selected_loans_indices"
    ExportLoans = "export_loans_path"
    Check = "check_signed_in"

    def __str__(self):
        return str(self.value)


class LibbyNotConfiguredError(RuntimeError):
    """
    Raised when Libby is not yet configured. Used in `--check`.
    """

    pass


def positive_int(value: str) -> int:
    """
    Ensure that argument is a positive integer

    :param value:
    :return:
    """
    try:
        int_value = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f'"{value}" is not a positive integer value')
    if int_value <= 0:
        raise argparse.ArgumentTypeError(f'"{value}" is not a positive integer value')
    return int_value


def valid_book_folder_file_format(value: str) -> str:
    """
    Ensure that the book folder format is valid

    :param value:
    :return:
    """
    try:
        value % {"Title": "", "Author": "", "Series": "", "Edition": ""}
    except KeyError as err:
        raise argparse.ArgumentTypeError(
            f'"{value}" is not a valid book folder/file name format: Invalid field {err}'
        ) from err
    except Exception as err:
        raise argparse.ArgumentTypeError(
            f'"{value}" is not a valid book folder/file name format: {err}'
        ) from err
    return value

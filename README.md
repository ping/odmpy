# odmpy

A simple console manager for OverDrive audiobook loans.

## Features

1. Downloads the cover and audio files for an audiobook loan
1. Supports the return of a loan

## Install

```bash
# Install / Update
pip install git+https://git@github.com/ping/odmpy.git --upgrade --force-reinstall

# Uninstall
pip uninstall odmpy
```

## Usage

```
usage: odmpy [-h] [-d DOWNLOAD_DIR] [-r] [-v] odm_file

Download/return an Overdrive loan audiobook.

positional arguments:
  odm_file              ODM file path

optional arguments:
  -h, --help            show this help message and exit
  -d DOWNLOAD_DIR, --downloaddir DOWNLOAD_DIR
                        Download folder path.
  -r, --return          Return loan.
  -v, --verbose         Enable more verbose messages for debugging.

Version 0.1.0. Source at https://github.com/ping/odmpy/
```

### Examples

```bash

# Download a book to MyLoans/
odmpy -d 'MyLoans/' MyLoans/Book1.odm

# Return Book1.odm
odmpy -r MyLoans/Book1.odm

```
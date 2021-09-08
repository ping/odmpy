# odmpy ![Python >= 3.5](https://img.shields.io/badge/Python-%3E%3D%203.5-3776ab.svg?maxAge=2592000)

A simple console manager for OverDrive audiobook loans. A python port of [overdrive](https://github.com/chbrown/overdrive).

Requires Python >=3.5.

## Features

1. Downloads the cover and audio files for an audiobook loan
1. Supports the return of a loan

## Install

```bash
# Install / Update to specific version
pip3 install git+https://git@github.com/ping/odmpy.git@0.4.6 --upgrade

# Install / Update from latest source
pip3 install git+https://git@github.com/ping/odmpy.git --upgrade --force-reinstall

# Uninstall
pip3 uninstall odmpy
```

## Usage

```
usage: odmpy [-h] [-v] [-t TIMEOUT] {info,dl,ret} ...

Download/return an Overdrive loan audiobook

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Enable more verbose messages for debugging
  -t TIMEOUT, --timeout TIMEOUT
                        Timeout (seconds) for network requests. Default 10.

Available commands:
  {info,dl,ret}         To get more help, use the -h option with the command.
    info                Get information about a loan file
    dl                  Download from a loan file
    ret                 Return a loan file.

Version 0.4.6. [Python 3.7.4-darwin] Source at https://github.com/ping/odmpy/
```

```
usage: odmpy dl [-h] [-d DOWNLOAD_DIR] [-c] [-m] [--mergeformat {mp3,m4b}]
                [-k] [-f] [--nobookfolder] [-j] [-r RETRIES] [--hideprogress]
                odm_file

Download from a loan file.

positional arguments:
  odm_file              ODM file path

optional arguments:
  -h, --help            show this help message and exit
  -d DOWNLOAD_DIR, --downloaddir DOWNLOAD_DIR
                        Download folder path
  -c, --chapters        Add chapter marks (experimental)
  -m, --merge           Merge into 1 file (experimental, requires ffmpeg)
  --mergeformat {mp3,m4b}
                        Merged file format (m4b is slow, experimental,
                        requires ffmpeg)
  -k, --keepcover       Always generate the cover image file (cover.jpg)
  -f, --keepmp3         Keep downloaded mp3 files (after merging)
  --nobookfolder        Don't create a book subfolder
  -j, --writejson       Generate a meta json file (for debugging)
  -r RETRIES, --retry RETRIES
                        Number of retries if download fails. Default 1.
  --hideprogress        Hide the download progress bar (e.g. during testing)
```

```
usage: odmpy ret [-h] odm_file

Return a loan file.

positional arguments:
  odm_file    ODM file path

optional arguments:
  -h, --help  show this help message and exit
```

```
usage: odmpy info [-h] [-f {text,json}] odm_file

Get information about a loan file.

positional arguments:
  odm_file              ODM file path

optional arguments:
  -h, --help            show this help message and exit
  -f {text,json}, --format {text,json}
                        Format for output
```

### Examples

```bash

# Download a book to MyLoans/
odmpy dl -d "MyLoans/" "MyLoans/Book1.odm"

# Return Book1.odm
odmpy ret "MyLoans/Book1.odm"

# Get information about a loan Book1.odm
odmpy info "MyLoans/Book1.odm"

```

`odmpy` also supports the reading of command options from a file. For example:

```bash
odmpy dl @example.dl.conf MyLoans/MyBook.odm
```
where [`example.dl.conf`](example.dl.conf) contains the command arguments for the `dl` command.


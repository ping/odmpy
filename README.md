# odmpy

A simple console manager for OverDrive audiobook loans. A python port of [overdrive](https://github.com/chbrown/overdrive).

Requires Python >=3.9.

## Features

1. Downloads the cover and audio files for an audiobook loan, with additional options to:
   - merge files into a single `mp3` or `m4b` file
   - add chapters information into the audio file(s)
2. Return a loan
3. Display information about an `odm` loan file
4. Download an audiobook loan directly from Libby

## Install

```bash
# Install / Update to specific version
pip3 install git+https://git@github.com/ping/odmpy.git@0.6.5 --upgrade

# Install / Update from latest source
pip3 install git+https://git@github.com/ping/odmpy.git --upgrade --force-reinstall

# Uninstall
pip3 uninstall odmpy
```

## Usage

```
usage: odmpy [-h] [-v] [-t TIMEOUT] {info,dl,ret,libby} ...

Download/return an OverDrive loan audiobook

options:
  -h, --help            show this help message and exit
  -v, --verbose         Enable more verbose messages for debugging
  -t TIMEOUT, --timeout TIMEOUT
                        Timeout (seconds) for network requests. Default 10.

Available commands:
  {info,dl,ret,libby}   To get more help, use the -h option with the command.
    info                Get information about a loan file
    dl                  Download from a loan file
    ret                 Return a loan file.
    libby               Interact directly with Libby to download audiobooks

Version 0.6.5. [Python 3.10.6-darwin] Source at https://github.com/ping/odmpy/
```

```
usage: odmpy dl [-h] [-d DOWNLOAD_DIR] [-c] [-m] [--mergeformat {mp3,m4b}] [-k] [-f] [--nobookfolder] [-j] [--opf] [--overwritetags] [--tagsdelimiter DELIMITER]
                [-r RETRIES] [--hideprogress]
                odm_file

Download from a loan file.

positional arguments:
  odm_file              ODM file path

options:
  -h, --help            show this help message and exit
  -d DOWNLOAD_DIR, --downloaddir DOWNLOAD_DIR
                        Download folder path
  -c, --chapters        Add chapter marks (experimental)
  -m, --merge           Merge into 1 file (experimental, requires ffmpeg)
  --mergeformat {mp3,m4b}
                        Merged file format (m4b is slow, experimental, requires ffmpeg)
  -k, --keepcover       Always generate the cover image file (cover.jpg)
  -f, --keepmp3         Keep downloaded mp3 files (after merging)
  --nobookfolder        Don't create a book subfolder
  -j, --writejson       Generate a meta json file (for debugging)
  --opf                 Generate an OPF file for the book
  --overwritetags       Always overwrite ID3 tags. By default odmpy tries to non-destructively tag audiofiles. This option forces odmpy to overwrite tags where
                        possible.
  --tagsdelimiter DELIMITER
                        For ID3 tags with multiple values, this defines the delimiter. For example, with the default delimiter ";", authors are written to the
                        artist tag as "Author A;Author B;Author C".
  -r RETRIES, --retry RETRIES
                        Number of retries if download fails. Default 1.
  --hideprogress        Hide the download progress bar (e.g. during testing)
```

```
usage: odmpy ret [-h] odm_file

Return a loan file.

positional arguments:
  odm_file    ODM file path

options:
  -h, --help  show this help message and exit
```

```
usage: odmpy info [-h] [-f {text,json}] odm_file

Get information about a loan file.

positional arguments:
  odm_file              ODM file path

options:
  -h, --help            show this help message and exit
  -f {text,json}, --format {text,json}
                        Format for output
```

```
usage: odmpy libby [-h] [--settings SETTINGS_FOLDER] [--reset] [--direct] [--keepodm] [-d DOWNLOAD_DIR] [-c] [-m] [--mergeformat {mp3,m4b}] [-k] [-f]
                   [--nobookfolder] [-j] [--opf] [--overwritetags] [--tagsdelimiter DELIMITER] [-r RETRIES] [--hideprogress] [--latest N]
                   [--exportloans LOAN_JSON_FILEPATH]

Interactive Libby Interface

options:
  -h, --help            show this help message and exit
  --settings SETTINGS_FOLDER
                        Settings folder to store odmpy required settings, e.g. Libby authentication
  --reset               Remove previously saved odmpy Libby settings
  --direct              Don't download the odm file from Libby but instead process the audiobook download directly
  --keepodm             Keep the downloaded odm and license files
  -d DOWNLOAD_DIR, --downloaddir DOWNLOAD_DIR
                        Download folder path
  -c, --chapters        Add chapter marks (experimental)
  -m, --merge           Merge into 1 file (experimental, requires ffmpeg)
  --mergeformat {mp3,m4b}
                        Merged file format (m4b is slow, experimental, requires ffmpeg)
  -k, --keepcover       Always generate the cover image file (cover.jpg)
  -f, --keepmp3         Keep downloaded mp3 files (after merging)
  --nobookfolder        Don't create a book subfolder
  -j, --writejson       Generate a meta json file (for debugging)
  --opf                 Generate an OPF file for the book
  --overwritetags       Always overwrite ID3 tags. By default odmpy tries to non-destructively tag audiofiles. This option forces odmpy to overwrite tags where
                        possible.
  --tagsdelimiter DELIMITER
                        For ID3 tags with multiple values, this defines the delimiter. For example, with the default delimiter ";", authors are written to the
                        artist tag as "Author A;Author B;Author C".
  -r RETRIES, --retry RETRIES
                        Number of retries if download fails. Default 1.
  --hideprogress        Hide the download progress bar (e.g. during testing)
  --latest N            Non-interactive mode that downloads the latest N number of loans
  --exportloans LOAN_JSON_FILEPATH
                        Non-interactive mode that exports audiobook loans information into a json file at the path specified
```

### Examples

```bash

# Download a book to MyLoans/
odmpy dl -d "MyLoans/" "MyLoans/Book1.odm"

# Return Book1.odm
odmpy ret "MyLoans/Book1.odm"

# Get information about a loan Book1.odm
odmpy info "MyLoans/Book1.odm"

# Start the Libby interface to select an audiobook loan to download
odmpy libby

# Download via Libby without generating the odm file
odmpy libby --direct

```

`odmpy` also supports the reading of command options from a file. For example:

```bash
odmpy dl @example.dl.conf MyLoans/MyBook.odm
```
where [`example.dl.conf`](example.dl.conf) contains the command arguments for the `dl` command.

### Unable to download odm files?

OverDrive no longer shows the odm download links for MacOS 10.15 (Catalina) and newer.
There are many ways to get around this but the easiest for me was to use a 
[bookmarklet](https://support.mozilla.org/en-US/kb/bookmarklets-perform-common-web-page-tasks).
Follow the instructions in this [gist](https://gist.github.com/ping/b58ae66359691db1d08f929a9e57a03d)
to get started.

Alternatively, if you have switched over to Libby, `odmpy` now
supports direct from Libby downloads through the `libby` command.

```bash
# view available options
odmpy libby -h
```

## Credits

- [overdrive](https://github.com/chbrown/overdrive)
- [pylibby](https://github.com/lullius/pylibby)

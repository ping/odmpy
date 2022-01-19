## About

`odmpy` is a simple console manager for OverDrive audiobook loans. A python port of [overdrive](https://github.com/chbrown/overdrive) with additional functionality.

Requires Python >=3.5.

### Features

1. Downloads the cover and audio files for an audiobook loan, with additional options to:
   - merge files into a single `mp3` or `m4b` file
   - add chapters information into the audio file(s)
2. Return a loan
3. Display information about an `odm` loan file

### Install

```bash
# Install / Update to specific version
pip3 install git+https://git@github.com/ping/odmpy.git@0.4.9 --upgrade

# Install / Update from latest source
pip3 install git+https://git@github.com/ping/odmpy.git --upgrade --force-reinstall

# Uninstall
pip3 uninstall odmpy
```

### Usage

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

Version 0.4.9. [Python 3.7.4-darwin] Source at https://github.com/ping/odmpy/
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

#### Examples

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
where [`example.dl.conf`](https://github.com/ping/odmpy/blob/master/example.dl.conf) contains the command arguments for the `dl` command.

### Unable to download odm files?

Overdrive no longer shows the odm download links for MacOS 10.15 (Catalina) and newer. There are many ways to get around this but the easiest for me was to use a [bookmarklet](https://support.mozilla.org/en-US/kb/bookmarklets-perform-common-web-page-tasks). Follow the instructions in this [gist](https://gist.github.com/ping/b58ae66359691db1d08f929a9e57a03d) to get started.
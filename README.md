# odmpy

A simple console manager for OverDrive audiobook loans. A python port of [overdrive](https://github.com/chbrown/overdrive).

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
usage: odmpy [-h] [-v] {info,dl,ret} ...

Download/return an Overdrive loan audiobook.

optional arguments:
  -h, --help     show this help message and exit
  -v, --verbose  Enable more verbose messages for debugging.

Available commands:
  {info,dl,ret}  To get more help, use the -h option with the command.
    info         Get information about a loan file.
    dl           Download from a loan file.
    ret          Return a loan file.

Version 0.1.0. Source at https://github.com/ping/odmpy/
```

### Examples

```bash

# Download a book to MyLoans/
odmpy dl -d 'MyLoans/' MyLoans/Book1.odm

# Return Book1.odm
odmpy ret MyLoans/Book1.odm

```
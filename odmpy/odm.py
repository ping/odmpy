# -*- coding: utf-8 -*-

# Copyright (C) 2018 github.com/ping
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
import os
import sys
import xml.etree.ElementTree
import uuid
import hashlib
import base64
from collections import OrderedDict
import re
import unicodedata
import logging
import math

import requests
from requests.exceptions import HTTPError, ConnectionError
from clint.textui import colored, progress
from mutagen.easyid3 import EasyID3

logger = logging.getLogger(__file__)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
logger.addHandler(ch)
logger.setLevel(logging.INFO)

__version__ = '0.1.0'   # also update ../setup.py

OMC = '1.2.0'
OS = '10.11.6'
UA = 'OverDrive Media Console'
UA_LONG = 'OverDrive Media Console/3.7.0.28 iOS/10.3.3'


# From django
def slugify(value, allow_unicode=False):
    """
    Convert to ASCII if 'allow_unicode' is False. Convert spaces to hyphens.
    Remove characters that aren't alphanumerics, underscores, or hyphens.
    Convert to lowercase. Also strip leading and trailing whitespace.
    """
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
        value = re.sub(r'[^\w\s-]', '', value, flags=re.U).strip().lower()
        return re.sub(r'[-\s]+', '-', value, flags=re.U)
    value = unicodedata.normalize(
        'NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value).strip().lower()
    return re.sub(r'[-\s]+', '-', value)


def run():
    parser = argparse.ArgumentParser(
        prog='odmpy',
        description='Download/return an Overdrive loan audiobook.',
        epilog='Version {}. Source at https://github.com/ping/odmpy/'.format(
            __version__))
    parser.add_argument(
        '-v', '--verbose', dest='verbose', action='store_true',
        help='Enable more verbose messages for debugging.')

    subparsers = parser.add_subparsers(
        title='Available commands', dest='subparser_name',
        help='To get more help, use the -h option with the command.')
    parser_info = subparsers.add_parser(
        'info', description='Get information about a loan file.',
        help='Get information about a loan file.')
    parser_info.add_argument('odm_file', type=str, help='ODM file path')

    parser_dl = subparsers.add_parser(
        'dl', description='Download from a loan file.',
        help='Download from a loan file.')
    parser_dl.add_argument(
        '-d', '--downloaddir', dest='download_dir', default='.',
        help='Download folder path.')
    parser_dl.add_argument('odm_file', type=str, help='ODM file path')

    parser_ret = subparsers.add_parser(
        'ret', description='Return a loan file.',
        help='Return a loan file.')
    parser_ret.add_argument('odm_file', type=str, help='ODM file path')
    # parser_info.add_argument('odm_file', type=str, help='ODM file path')

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    xml_doc = xml.etree.ElementTree.parse(args.odm_file)
    root = xml_doc.getroot()

    if args.subparser_name == 'ret':
        logger.info('Returning {} ...'.format(args.odm_file))
        early_return_url = root.find('EarlyReturnURL').text
        try:
            early_return_res = requests.get(
                early_return_url, headers={'User-Agent': UA_LONG}, timeout=10)
            early_return_res.raise_for_status()
            logger.info('Loan returned successfully: {}'.format(args.odm_file))
        except HTTPError as he:
            if he.response.status_code == 403:
                logger.warn('Loan is probably already returned.')
                sys.exit()
            logger.error(
                'Unexpected HTTPError while trying to return loan {}'.format(
                    args.odm_file))
            logger.error('HTTPError: {}'.format(str(he)))
            logger.debug(he.response.content)
            sys.exit(1)
        except ConnectionError as ce:
            logger.error('ConnectionError: {}'.format(str(ce)))
            sys.exit(1)

        sys.exit()

    metadata = None
    for t in root.itertext():
        if not t.startswith('<Metadata>'):
            continue
        metadata = xml.etree.ElementTree.fromstring(
            # remove invalid & char
            re.sub(r'\s&\s', ' &amp; ', t))
        break

    title = metadata.find('Title').text
    cover_url = metadata.find('CoverUrl').text
    authors = [
        c.text for c in metadata.find('Creators')
        if 'Author' in c.attrib.get('role', '')]
    if not authors:
        authors = [c.text for c in metadata.find('Creators')]

    if args.subparser_name == 'info':
        logger.info(u'{:10} {}'.format('Title:', colored.blue(title)))
        logger.info(u'{:10} {}'.format('Creators:', colored.blue(u', '.join([
            u'{} ({})'.format(c.text, c.attrib['role'])
            for c in metadata.find('Creators')]))))
        logger.info(u'{:10} {}'.format(
            'Publisher:', metadata.find('Publisher').text))
        logger.info(u'{:10} {}'.format('Subjects:', u', '.join([
            c.text for c in metadata.find('Subjects')])))
        logger.info(u'{:10} {}'.format('Languages:', u', '.join([
            c.text for c in metadata.find('Languages')])))
        logger.info(u'{:10} \n{}'.format(
            'Description:', metadata.find('Description').text))

        for formats in root.findall('Formats'):
            for f in formats:
                logger.info(u'{:10} {}'.format('Format:', f.attrib['name']))
                parts = f.find('Parts')
                for p in parts:
                    logger.info('  * {} - {} ({:,.0f}kB)'.format(
                        p.attrib['name'], p.attrib['duration'],
                        math.ceil(1.0 * int(p.attrib['filesize']) / 1024)))
        sys.exit()

    download_baseurl = ''
    download_parts = []
    for formats in root.findall('Formats'):
        for f in formats:
            protocols = f.find('Protocols')
            for p in protocols:
                if p.attrib.get('method', '') != 'download':
                    continue
                download_baseurl = p.attrib['baseurl']
                break
            parts = f.find('Parts')
            for p in parts:
                download_parts.append(p.attrib)

    logger.info('Downloading "{}" by "{}" in {} parts...'.format(
        colored.blue(title, bold=True),
        colored.blue(', '.join(authors)), len(download_parts)
    ))

    book_folder = os.path.join(
        args.download_dir,
        u'{} - {}'.format(title, u', '.join(authors)))
    if not os.path.exists(book_folder):
        os.makedirs(book_folder)

    cover_filename = os.path.join(book_folder, 'cover.jpg')
    if not os.path.isfile(cover_filename):
        cover_res = requests.get(cover_url, headers={'User-Agent': UA})
        cover_res.raise_for_status()
        with open(cover_filename, 'wb') as outfile:
            outfile.write(cover_res.content)

    acquisition_url = root.find('License').find('AcquisitionUrl').text
    media_id = root.attrib['id']

    client_id = str(uuid.uuid1()).upper()
    raw_hash = '{client_id}|{omc}|{os}|ELOSNOC*AIDEM*EVIRDREVO'.format(
        client_id=client_id,
        omc=OMC,
        os=OS
    )
    m = hashlib.sha1(raw_hash.encode('utf-16-le'))
    license_hash = base64.b64encode(m.digest())

    # Extract license
    # License file is downloadable only once per odm
    # so we keep it in case downloads fail
    _, odm_filename = os.path.split(args.odm_file)
    license_file = os.path.join(
        args.download_dir, odm_filename.replace('.odm', '.license'))

    if os.path.isfile(license_file):
        logger.warn('Already downloaded license file: {}'.format(license_file))
    else:
        # download license file
        params = OrderedDict([
            ('MediaID', media_id), ('ClientID', client_id),
            ('OMC', OMC), ('OS', OS), ('Hash', license_hash)])

        license_res = requests.get(
            acquisition_url,
            params=params,
            headers={'User-Agent': UA},
            timeout=10,
            stream=True
        )
        try:
            license_res.raise_for_status()
            with open(license_file, 'wb') as outfile:
                for chunk in license_res.iter_content(1024):
                    outfile.write(chunk)
            logger.debug('Saved license file {}'.format(license_file))

        except HTTPError as he:
            if he.response.status_code == 404:
                # odm file has expired
                logger.error(
                    'The loan file "{}" has expired.'
                    'Please download again.'.format(
                        args.odm_file))
            else:
                logger.error(he.response.content)
            sys.exit(1)
        except ConnectionError as ce:
            logger.error('ConnectionError: {}'.format(str(ce)))
            sys.exit(1)

    license_xml_doc = xml.etree.ElementTree.parse(license_file)
    license_root = license_xml_doc.getroot()

    ns = '{http://license.overdrive.com/2008/03/License.xsd}'

    license_client = license_root.find(
        '{}SignedInfo'.format(ns)).find('{}ClientID'.format(ns))
    license_client_id = license_client.text

    lic_file_contents = ''
    with open(license_file, 'r') as lic_file:
        lic_file_contents = lic_file.read()

    for p in download_parts:
        part_number = int(p['number'])
        part_filename = os.path.join(
            book_folder,
            u'{}.mp3'.format(
                slugify(u'{} - Part {:02d}'.format(
                    title, part_number),
                    allow_unicode=True
                )
            )
        )
        part_tmp_filename = u'{}.part'.format(part_filename)

        if os.path.isfile(part_filename):
            logger.warn('Already saved {}'.format(
                colored.magenta(part_filename)))
            continue

        part_file_size = int(p['filesize'])
        part_url_filename = p['filename']
        part_download_url = '{}/{}'.format(download_baseurl, part_url_filename)

        try:
            part_download_res = requests.get(
                part_download_url,
                headers={
                    'User-Agent': UA,
                    'ClientID': license_client_id,
                    'License': lic_file_contents
                },
                timeout=10, stream=True)

            part_download_res.raise_for_status()

            chunk_size = 1024
            expected_chunk_count = math.ceil(1.0 * part_file_size / chunk_size)
            with open(part_tmp_filename, 'wb') as outfile:
                for chunk in progress.bar(
                        part_download_res.iter_content(chunk_size=chunk_size),
                        label='Part {}'.format(part_number),
                        expected_size=expected_chunk_count):
                    if chunk:
                        outfile.write(chunk)
            os.rename(part_tmp_filename, part_filename)

            try:
                audiofile = EasyID3(part_filename)
                if not audiofile.get('title'):
                    audiofile['title'] = u'{}'.format(title)
                if not audiofile.get('album'):
                    audiofile['album'] = u'{}'.format(title)
                if not audiofile.get('artist'):
                    audiofile['artist'] = u'{}'.format(authors[0])
                if not audiofile.get('albumartist'):
                    audiofile['albumartist'] = u'{}'.format(authors[0])
                if not audiofile.get('tracknumber'):
                    audiofile['tracknumber'] = u'{:02d}'.format(part_number)
                audiofile.save()
            except Exception as e:
                logger.warn('Error saving ID3: {}'.format(str(e)))

            logger.info('Saved {}'.format(colored.magenta(part_filename)))

        except HTTPError as he:
            logger.error('HTTPError: {}'.format(str(he)))
            logger.debug(he.response.content)
            sys.exit(1)

        except ConnectionError as ce:
            logger.error('ConnectionError: {}'.format(str(ce)))
            sys.exit(1)

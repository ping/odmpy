# -*- coding: utf-8 -*-

# Copyright (C) 2021 github.com/ping
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

OMC = '1.2.0'
OS = '10.11.6'
UA = 'OverDrive Media Console'
UA_LONG = 'OverDrive Media Console/3.7.0.28 iOS/10.3.3'

# Ref: https://github.com/ping/odmpy/issues/19
UNSUPPORTED_PARSER_ENTITIES = {
    # https://www.freeformatter.com/html-entities.html#iso88591-characters
    'Agrave': 'À',
    'Aacute': 'Á',
    'Acirc': 'Â',
    'Atilde': 'Ã',
    'Auml': 'Ä',
    'Aring': 'Å',
    'AElig': 'Æ',
    'Ccedil': 'Ç',
    'Egrave': 'È',
    'Eacute': 'É',
    'Ecirc': 'Ê',
    'Euml': 'Ë',
    'Igrave': 'Ì',
    'Iacute': 'Í',
    'Icirc': 'Î',
    'Iuml': 'Ï',
    'ETH': 'Ð',
    'Ntilde': 'Ñ',
    'Ograve': 'Ò',
    'Oacute': 'Ó',
    'Ocirc': 'Ô',
    'Otilde': 'Õ',
    'Ouml': 'Ö',
    'Oslash': 'Ø',
    'Ugrave': 'Ù',
    'Uacute': 'Ú',
    'Ucirc': 'Û',
    'Uuml': 'Ü',
    'Yacute': 'Ý',
    'THORN': 'Þ',
    'szlig': 'ß',
    'agrave': 'à',
    'aacute': 'á',
    'acirc': 'â',
    'atilde': 'ã',
    'auml': 'ä',
    'aring': 'å',
    'aelig': 'æ',
    'ccedil': 'ç',
    'egrave': 'è',
    'eacute': 'é',
    'ecirc': 'ê',
    'euml': 'ë',
    'igrave': 'ì',
    'iacute': 'í',
    'icirc': 'î',
    'iuml': 'ï',
    'eth': 'ð',
    'ntilde': 'ñ',
    'ograve': 'ò',
    'oacute': 'ó',
    'ocirc': 'ô',
    'otilde': 'õ',
    'ouml': 'ö',
    'oslash': 'ø',
    'ugrave': 'ù',
    'uacute': 'ú',
    'ucirc': 'û',
    'uuml': 'ü',
    'yacute': 'ý',
    'thorn': 'þ',
    'yuml': 'ÿ',
    # https://www.freeformatter.com/html-entities.html#iso88591-symbols
    'iexcl': '¡',
    'cent': '¢',
    'pound': '£',
    'curren': '¤',
    'yen': '¥',
    'brvbar': '¦',
    'sect': '§',
    'uml': '¨',
    'copy': '©',
    'ordf': 'ª',
    'laquo': '«',
    'not': '¬',
    'shy': '­',
    'reg': '®',
    'macr': '¯',
    'deg': '°',
    'plusmn': '±',
    'sup2': '²',
    'sup3': '³',
    'acute': '´',
    'micro': 'µ',
    'para': '¶',
    'cedil': '¸',
    'sup1': '¹',
    'ordm': 'º',
    'raquo': '»',
    'frac14': '¼',
    'frac12': '½',
    'frac34': '¾',
    'iquest': '¿',
    'times': '×',
    'divide': '÷',
}

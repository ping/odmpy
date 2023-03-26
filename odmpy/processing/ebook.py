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
import base64
import datetime
import json
import logging
import mimetypes
import os
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from functools import cmp_to_key
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse, urljoin

import bs4.element
import requests
from bs4 import BeautifulSoup, Doctype
from termcolor import colored
from tqdm import tqdm

from .shared import (
    generate_names,
    build_opf_package,
    extract_isbn,
    extract_authors_from_openbook,
)
from ..errors import OdmpyRuntimeError
from ..libby import USER_AGENT, LibbyClient, LibbyFormats, LibbyMediaTypes
from ..overdrive import OverDriveClient
from ..utils import slugify, is_windows

#
# Main processing logic for libby direct ebook and magazine loans
#

NAV_XHTMLTEMPLATE = """
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title></title></head>
<body>
<nav epub:type="toc">
<h1>Contents</h1>
<ol id="toc"></ol>
</nav>
</body>
</html>
"""


def _build_ncx(media_info: Dict, openbook: Dict) -> ET.Element:
    """
    Build the ncx from openbook

    :param media_info:
    :param openbook:
    :return:
    """

    # References:
    # Version 2: https://idpf.org/epub/20/spec/OPF_2.0_final_spec.html#Section2.0
    # Version 3: https://www.w3.org/TR/epub-33/#sec-package-doc

    publication_identifier = (
        extract_isbn(
            media_info["formats"],
            [LibbyFormats.EBookOverdrive, LibbyFormats.MagazineOverDrive],
        )
        or media_info["id"]
    )

    ET.register_namespace("opf", "http://www.idpf.org/2007/opf")
    ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")
    ncx = ET.Element(
        "ncx",
        attrib={
            "version": "2005-1",
            "xmlns": "http://www.daisy.org/z3986/2005/ncx/",
            "xml:lang": "en",
        },
    )

    head = ET.SubElement(ncx, "head")
    ET.SubElement(
        head, "meta", attrib={"content": publication_identifier, "name": "dtb:uid"}
    )
    doc_title = ET.SubElement(ncx, "docTitle")
    doc_title_text = ET.SubElement(doc_title, "text")
    doc_title_text.text = openbook["title"]["main"]

    doc_author = ET.SubElement(ncx, "docAuthor")
    doc_author_text = ET.SubElement(doc_author, "text")
    doc_author_text.text = openbook["creator"][0]["name"]

    nav_map = ET.SubElement(ncx, "navMap")
    for i, item in enumerate(openbook["nav"]["toc"], start=1):
        nav_point = ET.SubElement(nav_map, "navPoint", attrib={"id": f"navPoint{i}"})
        nav_label = ET.SubElement(nav_point, "navLabel")
        nav_label_text = ET.SubElement(nav_label, "text")
        nav_label_text.text = item["title"]
        ET.SubElement(nav_point, "content", attrib={"src": item["path"]})
    return ncx


def _sanitise_opf_id(string_id: str) -> str:
    """
    OPF IDs cannot start with a number
    :param string_id:
    :return:
    """
    string_id = slugify(string_id)
    if string_id[0].isdigit():
        return f"id_{string_id}"
    return string_id


def _cleanup_soup(soup: BeautifulSoup, version: str = "2.0") -> None:
    """
    Tries to fix up book content pages to be epub-version compliant.

    :param soup:
    :param version:
    :return:
    """
    if version == "2.0":
        # v2 is a lot pickier about the acceptable elements and attributes
        modified_doctype = 'html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd"'
        for item in soup.contents:
            if isinstance(item, Doctype):
                item.replace_with(Doctype(modified_doctype))
                break
        remove_attributes = [
            # this list will not be complete, but we try
            "aria-label",
            "data-loc",
            "data-epub-type",
            "data-document-status",
            "data-xml-lang",
            "lang",
            "role",
            "epub:type",
            "epub:prefix",
        ]
        for attribute in remove_attributes:
            for tag in soup.find_all(attrs={attribute: True}):
                del tag[attribute]
        convert_tags = ["nav", "section"]  # this list will not be complete, but we try
        for tag in convert_tags:
            for invalid_tag in soup.find_all(tag):
                invalid_tag.name = "div"

    # known issues, this will not be complete
    for svg in soup.find_all("svg"):
        if not svg.get("xmlns"):
            svg["xmlns"] = "http://www.w3.org/2000/svg"
        if not svg.get("xmlns:xlink"):
            svg["xmlns:xlink"] = "http://www.w3.org/1999/xlink"
    convert_tags = ["figcaption"]
    for tag in convert_tags:
        for invalid_tag in soup.find_all(tag):
            invalid_tag.name = "div"
    remove_tags = ["base"]
    for tag in remove_tags:
        for remove_tag in soup.find_all(tag):
            remove_tag.decompose()

    html_tag = soup.find("html")
    if html_tag and isinstance(html_tag, bs4.element.Tag) and not html_tag.get("xmlns"):
        html_tag["xmlns"] = "http://www.w3.org/1999/xhtml"


def _sort_spine_entries(a: Dict, b: Dict, toc_pages: List[str]):
    """
    Sort spine according to TOC. For magazines, this is sometimes a
    problem where the sequence laid out in the spine does not align
    with the TOC, e.g. Mother Jones. If unsorted, the page through
    sequence does not match the actual TOC.

    :param a:
    :param b:
    :param toc_pages:
    :return:
    """
    try:
        a_index = toc_pages.index(a["-odread-original-path"])
    except ValueError:
        a_index = 999
    try:
        b_index = toc_pages.index(b["-odread-original-path"])
    except ValueError:
        b_index = 999

    if a_index != b_index:
        # sort order found via toc
        return -1 if a_index < b_index else 1

    return -1 if a["-odread-spine-position"] < b["-odread-spine-position"] else 1


def _sort_title_contents(a: Dict, b: Dict):
    """
    Sort the title contents roster so that pages get processed first.
    This is a precautionary measure for getting high-res cover images
    since we must parse the html for the image src.

    :param a:
    :param b:
    :return:
    """
    extensions_rank = [".xhtml", ".html", ".htm", ".jpg", ".jpeg", ".png", ".gif"]
    a_ext = Path(a["url"]).suffix
    b_ext = Path(b["url"]).suffix
    try:
        a_index = extensions_rank.index(a_ext)
    except ValueError:
        a_index = 999
    try:
        b_index = extensions_rank.index(b_ext)
    except ValueError:
        b_index = 999

    if a_index != b_index:
        # sort order found via toc
        return -1 if a_index < b_index else 1

    if a_ext != b_ext:
        return -1 if a_ext < b_ext else 1

    return -1 if urlparse(a["url"]).path < urlparse(b["url"]).path else 1


def _filter_content(entry: Dict, media_info: Dict, toc_pages: List[str]):
    """
    Filter title contents that are not needed.

    :param entry:
    :param media_info:
    :param toc_pages:
    :return:
    """
    parsed_entry_url = urlparse(entry["url"])
    media_type, _ = mimetypes.guess_type(parsed_entry_url.path[1:])

    if media_info["type"]["id"] == LibbyMediaTypes.Magazine and media_type:
        if media_type.startswith("image/") and (
            parsed_entry_url.path.startswith("/pages/")
            or parsed_entry_url.path.startswith("/thumbnails/")
        ):
            return False
        if (
            media_type in ("application/xhtml+xml", "text/html")
            and parsed_entry_url.path[1:] not in toc_pages
        ):
            return False

    if parsed_entry_url.path.startswith("/_d/"):  # ebooks
        return False

    return True


def process_ebook_loan(
    loan: Dict,
    cover_path: Optional[Path],
    openbook: Dict,
    rosters: List[Dict],
    libby_client: LibbyClient,
    args: argparse.Namespace,
    logger: logging.Logger,
) -> None:
    """
    Generates and return an ebook loan directly from Libby.

    :param loan:
    :param cover_path:
    :param openbook:
    :param rosters:
    :param libby_client:
    :param args:
    :param logger:
    :return:
    """
    book_folder, book_file_name = generate_names(
        title=loan["title"],
        series=loan.get("series") or "",
        authors=extract_authors_from_openbook(openbook),
        edition=loan.get("edition") or "",
        title_id=loan["id"],
        args=args,
        logger=logger,
    )
    epub_file_path = book_file_name.with_suffix(".epub")
    epub_version = "3.0"

    book_meta_name = "META-INF"
    book_content_name = "OEBPS"
    book_meta_folder = book_folder.joinpath(book_meta_name)
    book_content_folder = book_folder.joinpath(book_content_name)
    for d in (book_meta_folder, book_content_folder):
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)

    od_client = OverDriveClient(
        user_agent=USER_AGENT, timeout=args.timeout, retry=args.retries
    )
    media_info = od_client.media(loan["id"])

    if args.is_debug_mode:
        with book_folder.joinpath("media.json").open("w", encoding="utf-8") as f:
            json.dump(media_info, f, indent=2)

        with book_folder.joinpath("loan.json").open("w", encoding="utf-8") as f:
            json.dump(loan, f, indent=2)

        with book_folder.joinpath("rosters.json").open("w", encoding="utf-8") as f:
            json.dump(rosters, f, indent=2)

        with book_folder.joinpath("openbook.json").open("w", encoding="utf-8") as f:
            json.dump(openbook, f, indent=2)

    title_contents: Dict = next(
        iter([r for r in rosters if r["group"] == "title-content"]), {}
    )
    headers = libby_client.default_headers()
    headers["Accept"] = "*/*"
    contents_re = re.compile(r"parent\.__bif_cfc0\(self,'(?P<base64_text>.+)'\)")

    openbook_toc = openbook["nav"]["toc"]
    if len(openbook_toc) <= 1 and loan["type"]["id"] == LibbyMediaTypes.Magazine:
        raise OdmpyRuntimeError("Unsupported fixed-layout (pre-paginated) format.")

    # for finding cover image for magazines
    cover_toc_item = next(
        iter(
            [
                item
                for item in openbook_toc
                if item.get("pageRange", "") == "Cover" and item.get("featureImage")
            ]
        ),
        None,
    )
    # for finding cover image for ebooks
    cover_page_landmark = next(
        iter(
            [
                item
                for item in openbook.get("nav", {}).get("landmarks", [])
                if item["type"] == "cover"
            ]
        ),
        None,
    )
    toc_pages = [item["path"].split("#")[0] for item in openbook_toc]
    manifest_entries: List[Dict] = []

    title_content_entries = list(
        filter(
            lambda e: _filter_content(e, media_info, toc_pages),
            title_contents["entries"],
        )
    )
    # Ignoring mypy error below because of https://github.com/python/mypy/issues/9372
    title_content_entries = sorted(
        title_content_entries, key=cmp_to_key(_sort_title_contents)  # type: ignore[misc]
    )
    progress_bar = tqdm(title_content_entries, disable=args.hide_progress)
    has_ncx = False
    has_nav = False

    # Used to patch magazine css that causes paged mode in calibre viewer to not work.
    # This expression is used to strip `overflow-x: hidden` from the css definition
    # for `#article-body`.
    patch_magazine_css_re = re.compile(
        r"(#article-body\s*\{[^{}]+?)overflow-x:\s*hidden;([^{}]+?})"
    )

    # holds the manifest item ID for the image identified as the cover
    cover_img_manifest_id = None

    for entry in progress_bar:
        entry_url = entry["url"]
        parsed_entry_url = urlparse(entry_url)
        media_type, _ = mimetypes.guess_type(parsed_entry_url.path[1:])
        asset_folder = book_content_folder.joinpath(
            Path(parsed_entry_url.path[1:]).parent
        )
        if media_type == "application/x-dtbncx+xml":
            has_ncx = True
        manifest_entry = {
            "href": parsed_entry_url.path[1:],
            "id": "ncx"
            if media_type == "application/x-dtbncx+xml"
            else _sanitise_opf_id(parsed_entry_url.path[1:]),
            "media-type": media_type,
        }

        # try to find cover image for magazines
        if cover_toc_item and manifest_entry["id"] == _sanitise_opf_id(
            cover_toc_item["featureImage"]
        ):
            # we assign it here to ensure that the image referenced in the
            # toc actually exists
            cover_img_manifest_id = manifest_entry["id"]

        if not asset_folder.exists():
            asset_folder.mkdir(parents=True, exist_ok=True)
        asset_file_path = asset_folder.joinpath(Path(parsed_entry_url.path).name)

        soup = None
        if asset_file_path.exists():
            progress_bar.set_description(f"Already saved {asset_file_path.name}")
            if media_type in ("application/xhtml+xml", "text/html"):
                with asset_file_path.open("r", encoding="utf-8") as f_asset:
                    soup = BeautifulSoup(f_asset, features="html.parser")
        else:
            progress_bar.set_description(f"Downloading {asset_file_path.name}")
            # use the libby client session because the required
            # auth cookies are set there
            res: requests.Response = libby_client.make_request(
                entry_url, headers=headers, return_res=True
            )

            # patch magazine css to fix rendering in calibre viewer
            if (
                media_info["type"]["id"] == LibbyMediaTypes.Magazine
                and media_type == "text/css"
            ):
                css_content = patch_magazine_css_re.sub(r"\1\2", res.text)
                with open(asset_file_path, "w", encoding="utf-8") as f_out:
                    f_out.write(css_content)
            elif media_type in ("application/xhtml+xml", "text/html"):
                soup = BeautifulSoup(res.text, features="html.parser")
                script_ele = soup.find("script", attrs={"type": "text/javascript"})
                if script_ele and hasattr(script_ele, "string"):
                    mobj = contents_re.search(script_ele.string or "")
                    if not mobj:
                        logger.warning(
                            "Unable to extract content string for %s",
                            parsed_entry_url.path,
                        )
                    else:
                        new_soup = BeautifulSoup(
                            base64.b64decode(mobj.group("base64_text")),
                            features="html.parser",
                        )
                        soup.body.replace_with(new_soup.body)  # type: ignore[arg-type,union-attr]
                _cleanup_soup(soup, version=epub_version)
                if (
                    cover_toc_item
                    and cover_toc_item.get("featureImage")
                    and manifest_entry["id"] == _sanitise_opf_id(cover_toc_item["path"])
                ):
                    img_src = os.path.relpath(
                        book_content_folder.joinpath(cover_toc_item["featureImage"]),
                        start=asset_folder,
                    )
                    if is_windows():
                        img_src = Path(img_src).as_posix()
                    # patch the svg based cover for magazines
                    cover_svg = soup.find("svg")
                    if cover_svg:
                        # replace the svg ele with a simple image tag
                        cover_svg.decompose()  # type: ignore[union-attr]
                        for c in soup.body.find_all(recursive=False):  # type: ignore[union-attr]
                            c.decompose()
                        soup.body.append(  # type: ignore[union-attr]
                            soup.new_tag("img", attrs={"src": img_src, "alt": "Cover"})
                        )
                        style_ele = soup.new_tag("style")
                        style_ele.append(
                            "img { max-width: 100%; margin-left: auto; margin-right: auto; }"
                        )
                        soup.head.append(style_ele)  # type: ignore[union-attr]

                with open(asset_file_path, "w", encoding="utf-8") as f_out:
                    f_out.write(str(soup))
            else:
                with open(asset_file_path, "wb") as f_out:
                    f_out.write(res.content)

        if soup:
            # try to min. soup searches where possible
            if (
                (not cover_img_manifest_id)
                and cover_page_landmark
                and cover_page_landmark["path"] == parsed_entry_url.path[1:]
            ):
                # try to find cover image for the book from the cover html content
                cover_image = soup.find("img", attrs={"src": True})
                if cover_image:
                    cover_img_manifest_id = _sanitise_opf_id(
                        urljoin(cover_page_landmark["path"], cover_image["src"])  # type: ignore[index]
                    )
            elif (not has_nav) and soup.find(attrs={"epub:type": "toc"}):
                # identify nav page
                manifest_entry["properties"] = "nav"
                has_nav = True
            elif soup.find("svg"):
                # page has svg
                manifest_entry["properties"] = "svg"

        if cover_img_manifest_id == manifest_entry["id"]:
            manifest_entry["properties"] = "cover-image"
        manifest_entries.append(manifest_entry)
        if manifest_entry.get("properties") == "cover-image" and cover_path:
            # replace the cover image already downloaded via the OD api, in case it is to be kept
            shutil.copyfile(asset_file_path, cover_path)

    if not has_nav:
        # Generate nav - needed for magazines
        nav_soup = BeautifulSoup(NAV_XHTMLTEMPLATE, features="html.parser")
        nav_soup.find("title").append(loan["title"])  # type: ignore[union-attr]
        toc_ele = nav_soup.find(id="toc")
        for item in openbook_toc:
            li_ele = nav_soup.new_tag("li")
            a_ele = nav_soup.new_tag("a", attrs={"href": item["path"]})
            a_ele.append(item["title"])
            li_ele.append(a_ele)
            toc_ele.append(li_ele)  # type: ignore[union-attr]
        # we give the nav an id-stamped file name to avoid accidentally overwriting
        # an existing file name
        nav_file_name = f'nav_{loan["id"]}.xhtml'
        with book_content_folder.joinpath(nav_file_name).open(
            "w", encoding="utf-8"
        ) as f_nav:
            f_nav.write(str(nav_soup).strip())
        manifest_entries.append(
            {
                "href": nav_file_name,
                "id": "nav",
                "media-type": "application/xhtml+xml",
                "properties": "nav",
            }
        )

    if not has_ncx:
        # generate ncx for backward compat
        ncx = _build_ncx(media_info, openbook)
        # we give the ncx an id-stamped file name to avoid accidentally overwriting
        # an existing file name
        toc_ncx_name = f'toc_{loan["id"]}.ncx'
        tree = ET.ElementTree(ncx)
        tree.write(
            book_content_folder.joinpath(toc_ncx_name),
            xml_declaration=True,
            encoding="utf-8",
        )
        manifest_entries.append(
            {
                "href": toc_ncx_name,
                "id": "ncx",
                "media-type": "application/x-dtbncx+xml",
            }
        )
        has_ncx = True

    # create epub OPF
    opf_file_name = "package.opf"
    opf_file_path = book_content_folder.joinpath(opf_file_name)
    package = build_opf_package(
        media_info,
        version=epub_version,
        loan_format=LibbyFormats.MagazineOverDrive
        if loan["type"]["id"] == LibbyMediaTypes.Magazine
        else LibbyFormats.EBookOverdrive,
    )
    if args.generate_opf:
        # save opf before the manifest and spine elements get added
        # because those elements are meaningless outside an epub
        export_opf_file = epub_file_path.with_suffix(".opf")
        ET.ElementTree(package).write(
            export_opf_file, xml_declaration=True, encoding="utf-8"
        )
        logger.info('Saved "%s"', colored(str(export_opf_file), "magenta"))

    # add manifest
    manifest = ET.SubElement(package, "manifest")
    for entry in manifest_entries:
        ET.SubElement(manifest, "item", attrib=entry)

    cover_manifest_entry = next(
        iter(
            [
                entry
                for entry in manifest_entries
                if entry.get("properties", "") == "cover-image"
            ]
        ),
        None,
    )
    if not cover_manifest_entry:
        cover_img_manifest_id = None
    if cover_path and not cover_manifest_entry:
        # add cover image separately since we can't identify which item is the cover
        # we give the cover a timestamped file name to avoid accidentally overwriting
        # an existing file name
        cover_image_name = f"cover_{int(datetime.datetime.now().timestamp())}.jpg"
        shutil.copyfile(cover_path, book_content_folder.joinpath(cover_image_name))
        cover_img_manifest_id = "coverimage"
        ET.SubElement(
            manifest,
            "item",
            attrib={
                "id": cover_img_manifest_id,
                "href": cover_image_name,
                "media-type": "image/jpeg",
                "properties": "cover-image",
            },
        )

    if cover_img_manifest_id:
        metadata = package.find("metadata")
        if metadata:
            _ = ET.SubElement(
                metadata,
                "meta",
                attrib={"name": "cover", "content": cover_img_manifest_id},
            )

    # add spine
    spine = ET.SubElement(package, "spine")
    if has_ncx:
        spine.set("toc", "ncx")
    spine_entries = list(
        filter(
            lambda s: not (
                media_info["type"]["id"] == LibbyMediaTypes.Magazine
                and s["-odread-original-path"] not in toc_pages
            ),
            openbook["spine"],
        )
    )

    # Ignoring mypy error below because of https://github.com/python/mypy/issues/9372
    spine_entries = sorted(
        spine_entries, key=cmp_to_key(lambda a, b: _sort_spine_entries(a, b, toc_pages))  # type: ignore[misc]
    )
    for entry in spine_entries:
        if (
            media_info["type"]["id"] == LibbyMediaTypes.Magazine
            and entry["-odread-original-path"] not in toc_pages
        ):
            continue
        item_ref = ET.SubElement(spine, "itemref")
        item_ref.set("idref", _sanitise_opf_id(entry["-odread-original-path"]))

    # add guide
    if openbook.get("nav", {}).get("landmarks"):
        guide = ET.SubElement(package, "guide")
        for landmark in openbook["nav"]["landmarks"]:
            _ = ET.SubElement(
                guide,
                "reference",
                attrib={
                    "href": landmark["path"],
                    "title": landmark["title"],
                    "type": landmark["type"],
                },
            )

    if args.is_debug_mode:
        from xml.dom import minidom

        with opf_file_path.open("w", encoding="utf-8") as f:
            f.write(
                minidom.parseString(ET.tostring(package, "utf-8")).toprettyxml(
                    indent="\t"
                )
            )
    else:
        tree = ET.ElementTree(package)
        tree.write(opf_file_path, xml_declaration=True, encoding="utf-8")
    logger.debug('Saved "%s"', opf_file_path)

    # create container.xml
    container_file_path = book_meta_folder.joinpath("container.xml")
    container = ET.Element(
        "container",
        attrib={
            "version": "1.0",
            "xmlns": "urn:oasis:names:tc:opendocument:xmlns:container",
        },
    )
    root_files = ET.SubElement(container, "rootfiles")
    _ = ET.SubElement(
        root_files,
        "rootfile",
        attrib={
            # use posix path because zipFile requires "/"
            "full-path": Path(book_content_name, opf_file_name).as_posix(),
            "media-type": "application/oebps-package+xml",
        },
    )
    tree = ET.ElementTree(container)
    tree.write(container_file_path, xml_declaration=True, encoding="utf-8")
    logger.debug('Saved "%s"', container_file_path)

    # create epub zip
    with zipfile.ZipFile(
        epub_file_path, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as epub_zip:
        epub_zip.writestr(
            "mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED
        )
        for root_start in (book_meta_folder, book_content_folder):
            for p in root_start.glob("**/*"):
                if p.is_dir():
                    continue
                zip_archive_file = p.relative_to(book_folder)
                # using posix path because zipfile requires "/" separators
                # and may break on Windows otherwise
                zip_archive_name = zip_archive_file.as_posix()
                zip_target_file = book_folder.joinpath(zip_archive_file)
                epub_zip.write(zip_target_file, zip_archive_name)
                logger.debug(
                    'epub: Added "%s" as "%s"', zip_target_file, zip_archive_name
                )
    logger.info('Saved "%s"', colored(str(epub_file_path), "magenta", attrs=["bold"]))

    # clean up
    if not args.is_debug_mode:
        for file_name in (
            "mimetype",
            "media.json",
            "openbook.json",
            "loan.json",
            "rosters.json",
        ):
            target = book_folder.joinpath(file_name)
            if target.exists():
                target.unlink()
        for folder in (book_content_folder, book_meta_folder):
            shutil.rmtree(folder, ignore_errors=True)

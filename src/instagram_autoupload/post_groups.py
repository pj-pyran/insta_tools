"""Queue layout: one Drive subfolder per planned post date.

The queue folder contains subfolders named ``YYYY-MM-DD`` (the planned post
date). Everything inside one is posted together as a single carousel, in
alphabetical file-name order (max 10). The exporters put photos taken on the
same day into the same folder by default; move files or rename folders in
Drive to regroup or reschedule.

Photos in a folder are named ``<seq>-<original name>.jpg`` with an optional
same-named ``.txt`` caption. Photos with no capture date go in ``undated``,
which is never posted until renamed to a date.
"""

from __future__ import annotations

import os
import re

MAX_CAROUSEL_ITEMS = 10  # Instagram limit
UNDATED_FOLDER_NAME = "undated"

DriveFile = dict

_DATE_FOLDER = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_post_folder(name: str) -> bool:
    return bool(_DATE_FOLDER.match(name))


def build_name(seq: int, original: str) -> str:
    """File name (no extension) within a post folder."""
    return f"{seq:03d}-{original}"


def folder_name_for(post_date: str | None) -> str:
    return post_date or UNDATED_FOLDER_NAME


def carousel_order(images: list[DriveFile]) -> list[DriveFile]:
    """Photos of one post in carousel order (max 10)."""
    return sorted(images, key=lambda f: f["name"])[:MAX_CAROUSEL_ITEMS]


def find_caption(images: list[DriveFile], text_files: list[DriveFile]) -> DriveFile | None:
    """Caption of the first photo in the post that has one."""
    by_base = {os.path.splitext(f["name"])[0]: f for f in text_files}
    for image in images:
        caption = by_base.get(os.path.splitext(image["name"])[0])
        if caption:
            return caption
    return None

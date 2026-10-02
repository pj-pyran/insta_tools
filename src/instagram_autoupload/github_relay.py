"""Temporary public hosting for a photo via a GitHub Release asset.

Instagram's publishing API fetches the image over HTTP, so it must be
reachable at a public URL at request time. We upload it as a release asset
on this (public) repo, use the asset's download URL, then delete the
release afterwards so nothing lingers.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import time

import requests

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _repo() -> str:
    return os.environ["GITHUB_REPOSITORY"]  # "<owner>/<repo>", set automatically in Actions


def _headers() -> dict:
    token = os.environ["GITHUB_TOKEN"]
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


class ReleaseAsset:
    def __init__(self, release_id: int, tag_name: str, download_url: str):
        self.release_id = release_id
        self.tag_name = tag_name
        self.download_url = download_url


def upload_photo(local_path: str) -> ReleaseAsset:
    tag = f"post-{int(time.time())}"
    filename = os.path.basename(local_path)

    create_resp = requests.post(
        f"{GITHUB_API}/repos/{_repo()}/releases",
        headers=_headers(),
        json={
            "tag_name": tag,
            "name": tag,
            "body": "Temporary release for automated Instagram post image hosting.",
            "draft": False,
            "prerelease": False,
        },
        timeout=30,
    )
    create_resp.raise_for_status()
    release = create_resp.json()
    release_id = release["id"]
    upload_url = release["upload_url"].split("{", 1)[0]

    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    with open(local_path, "rb") as fh:
        asset_resp = requests.post(
            upload_url,
            headers={**_headers(), "Content-Type": content_type},
            params={"name": filename},
            data=fh,
            timeout=60,
        )
    asset_resp.raise_for_status()
    download_url = asset_resp.json()["browser_download_url"]

    logger.info("Uploaded %s as release asset for tag %s", filename, tag)
    return ReleaseAsset(release_id=release_id, tag_name=tag, download_url=download_url)


def delete_release(asset: ReleaseAsset) -> None:
    resp = requests.delete(
        f"{GITHUB_API}/repos/{_repo()}/releases/{asset.release_id}",
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()

    tag_resp = requests.delete(
        f"{GITHUB_API}/repos/{_repo()}/git/refs/tags/{asset.tag_name}",
        headers=_headers(),
        timeout=30,
    )
    if tag_resp.status_code not in (204, 404):
        tag_resp.raise_for_status()

    logger.info("Deleted temporary release %s", asset.tag_name)

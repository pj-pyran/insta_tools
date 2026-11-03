"""Export tagged photos from Lightroom's cloud catalog into the Drive queue.

Mirrors the Lightroom Classic plugin's workflow but against Adobe's cloud API:
a dedicated album marks photos "to export", and a second album marks them
"already exported" (the API has no per-asset keyword/tag field and no way to
remove a single asset from an album's membership check other than tracking
it in a second album).
"""

from __future__ import annotations

import base64
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

IMS_TOKEN_URL = "https://ims-na1.adobelogin.com/ims/token/v3"
LR_API = "https://lr.adobe.io"
GITHUB_API = "https://api.github.com"

SOURCE_ALBUM_NAME = "for Instagram auto-export"
EXPORTED_ALBUM_NAME = "Instagram auto-exported"

EXPORT_POLL_INTERVAL_SECONDS = 5
EXPORT_POLL_TIMEOUT_SECONDS = 120

REFRESH_TOKEN_SECRET_NAME = "ADOBE_REFRESH_TOKEN"


class LightroomCloudClient:
    def __init__(self) -> None:
        self.client_id = os.environ["ADOBE_CLIENT_ID"]
        self.client_secret = os.environ["ADOBE_CLIENT_SECRET"]
        self.refresh_token = os.environ["ADOBE_REFRESH_TOKEN"]
        self.access_token: str | None = None
        self.catalog_id: str | None = None

    def _auth_headers(self) -> dict:
        return {
            "X-API-Key": self.client_id,
            "Authorization": f"Bearer {self.access_token}",
        }

    def authenticate(self) -> None:
        """Exchange the refresh token for an access token.

        Adobe rotates the refresh token on every use, so the new one must be
        persisted (see rotate_github_secret) or the next run will fail.
        """
        resp = requests.post(
            IMS_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        logger.info("Authenticated with Adobe IMS")

    def _get(self, path: str, **kwargs) -> requests.Response:
        resp = requests.get(f"{LR_API}{path}", headers=self._auth_headers(), timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    def _post(self, path: str, **kwargs) -> requests.Response:
        resp = requests.post(f"{LR_API}{path}", headers=self._auth_headers(), timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    def _put(self, path: str, **kwargs) -> requests.Response:
        resp = requests.put(f"{LR_API}{path}", headers=self._auth_headers(), timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    def fetch_catalog_id(self) -> str:
        resp = self._get("/v2/catalog")
        self.catalog_id = _strip_json_prefix(resp.text)["id"]
        return self.catalog_id

    def _find_album_by_name(self, name: str) -> dict | None:
        resp = self._get(f"/v2/catalogs/{self.catalog_id}/albums", params={"subtype": "collection_set,collection"})
        for album in _strip_json_prefix(resp.text).get("resources", []):
            if album.get("payload", {}).get("name") == name:
                return album
        return None

    def get_or_create_album(self, name: str) -> str:
        existing = self._find_album_by_name(name)
        if existing:
            return existing["id"]

        import uuid

        album_id = uuid.uuid4().hex
        self._put(
            f"/v2/catalogs/{self.catalog_id}/albums/{album_id}",
            json={"subtype": "collection", "payload": {"name": name}},
        )
        logger.info("Created album %r", name)
        return album_id

    def list_album_asset_ids(self, album_id: str) -> set[str]:
        return set(self.list_album_assets(album_id))

    def list_album_assets(self, album_id: str) -> dict[str, tuple[str, str]]:
        """Map asset id -> (capture date YYYY-MM-DD or "", original file stem or "")."""
        ids: dict[str, tuple[str, str]] = {}
        params = {"limit": 500}
        path = f"/v2/catalogs/{self.catalog_id}/albums/{album_id}/assets"
        while True:
            resp = self._get(path, params=params)
            data = _strip_json_prefix(resp.text)
            for res in data.get("resources", []):
                payload = res["asset"].get("payload", {})
                source = payload.get("importSource", {})
                capture = payload.get("captureDate") or ""
                stem = os.path.splitext(source.get("fileName", ""))[0]
                ids[res["asset"]["id"]] = (capture[:10], stem)
            next_link = data.get("links", {}).get("next", {}).get("href")
            if not next_link:
                break
            path = next_link
            params = {}
        return ids

    def add_assets_to_album(self, album_id: str, asset_ids: list[str]) -> None:
        # API limit is 50 assets per call. A 403 where every error is
        # ResourceExistsError means all assets were already in the album;
        # treat that as success rather than a real failure.
        for i in range(0, len(asset_ids), 50):
            batch = asset_ids[i : i + 50]
            try:
                self._put(
                    f"/v2/catalogs/{self.catalog_id}/albums/{album_id}/assets",
                    json={"resources": [{"id": asset_id} for asset_id in batch]},
                )
            except requests.HTTPError as exc:
                if exc.response is None or exc.response.status_code != 403:
                    raise
                data = _strip_json_prefix(exc.response.text)
                errors = data.get("errors", [])
                if len(errors) != len(batch) or not all(
                    e.get("subtype") == "ResourceExistsError" for e in errors
                ):
                    raise
                logger.info("All assets in batch already in album %s", album_id)

    def generate_export(self, asset_id: str, long_side: int) -> str:
        resp = self._post(
            f"/v2/catalogs/{self.catalog_id}/assets/{asset_id}/exports",
            json={"output_settings": {"long_side": str(long_side), "mime_type": "image/jpeg"}},
        )
        data = _strip_json_prefix(resp.text)
        export_href = data["links"]["/rels/export"]["href"]
        return export_href.rsplit("/", 1)[-1]

    def download_export(self, asset_id: str, export_id: str, dest_path: str) -> None:
        deadline = time.monotonic() + EXPORT_POLL_TIMEOUT_SECONDS
        url = f"{LR_API}/v2/catalogs/{self.catalog_id}/assets/{asset_id}/exports/{export_id}"
        while True:
            resp = requests.get(url, headers=self._auth_headers(), timeout=30)
            if resp.status_code == 200:
                with open(dest_path, "wb") as fh:
                    fh.write(resp.content)
                return
            if resp.status_code != 404:
                resp.raise_for_status()
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Export {export_id} for asset {asset_id} did not finish in time")
            time.sleep(EXPORT_POLL_INTERVAL_SECONDS)


def _strip_json_prefix(text: str) -> dict:
    """Adobe prefixes some Lightroom API JSON responses with while (1) {}."""
    import json

    marker = "while (1) {}\n"
    if text.startswith(marker):
        text = text[len(marker) :]
    return json.loads(text)


def _encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    from nacl import encoding, public

    key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def rotate_github_secret(new_refresh_token: str) -> None:
    """Persist the rotated Adobe refresh token, same pattern as token_refresh.py."""
    repo = os.environ["GITHUB_REPOSITORY"]
    pat = os.environ["GH_PAT_SECRETS"]
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    key_resp = requests.get(f"{GITHUB_API}/repos/{repo}/actions/secrets/public-key", headers=headers, timeout=30)
    key_resp.raise_for_status()
    key_data = key_resp.json()

    encrypted_value = _encrypt_secret(key_data["key"], new_refresh_token)

    put_resp = requests.put(
        f"{GITHUB_API}/repos/{repo}/actions/secrets/{REFRESH_TOKEN_SECRET_NAME}",
        headers=headers,
        json={"encrypted_value": encrypted_value, "key_id": key_data["key_id"]},
        timeout=30,
    )
    put_resp.raise_for_status()
    logger.info("Rotated GitHub secret %s", REFRESH_TOKEN_SECRET_NAME)

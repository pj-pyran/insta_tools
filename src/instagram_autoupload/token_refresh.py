"""Refresh the 60-day Instagram access token and rotate it in GitHub secrets."""

from __future__ import annotations

import base64
import logging
import os

import requests
from nacl import encoding, public

logger = logging.getLogger(__name__)

GRAPH_HOST = "https://graph.instagram.com"
SECRET_NAME = "IG_ACCESS_TOKEN"
GITHUB_API = "https://api.github.com"


def refresh_access_token(current_token: str) -> str:
    resp = requests.get(
        f"{GRAPH_HOST}/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": current_token},
        timeout=30,
    )
    resp.raise_for_status()
    new_token = resp.json()["access_token"]
    logger.info("Refreshed Instagram access token")
    return new_token


def _encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def rotate_github_secret(new_token: str) -> None:
    """Write the refreshed token back to the repo's Actions secret.

    Requires a PAT (GH_PAT_SECRETS) with permission to manage this repo's
    Actions secrets - the default GITHUB_TOKEN cannot do this.
    """
    repo = os.environ["GITHUB_REPOSITORY"]
    pat = os.environ["GH_PAT_SECRETS"]
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    key_resp = requests.get(
        f"{GITHUB_API}/repos/{repo}/actions/secrets/public-key",
        headers=headers,
        timeout=30,
    )
    key_resp.raise_for_status()
    key_data = key_resp.json()

    encrypted_value = _encrypt_secret(key_data["key"], new_token)

    put_resp = requests.put(
        f"{GITHUB_API}/repos/{repo}/actions/secrets/{SECRET_NAME}",
        headers=headers,
        json={
            "encrypted_value": encrypted_value,
            "key_id": key_data["key_id"],
        },
        timeout=30,
    )
    put_resp.raise_for_status()
    logger.info("Rotated GitHub secret %s", SECRET_NAME)

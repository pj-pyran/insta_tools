"""Publish single-image or carousel posts via the Instagram API with Instagram Login."""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)

GRAPH_HOST = "https://graph.instagram.com"
API_VERSION = "v21.0"

POLL_INTERVAL_SECONDS = 10
POLL_TIMEOUT_SECONDS = 300

TERMINAL_STATUSES = {"FINISHED", "ERROR", "EXPIRED"}


class InstagramPublishError(RuntimeError):
    pass


def create_container(
    ig_user_id: str,
    access_token: str,
    image_url: str | None = None,
    caption: str = "",
    is_carousel_item: bool = False,
    children: list[str] | None = None,
) -> str:
    data = {"access_token": access_token}
    if children:
        data["media_type"] = "CAROUSEL"
        data["children"] = ",".join(children)
    else:
        data["image_url"] = image_url
    if is_carousel_item:
        data["is_carousel_item"] = "true"
    else:
        data["caption"] = caption  # captions are only valid on the top-level container
    resp = requests.post(
        f"{GRAPH_HOST}/{API_VERSION}/{ig_user_id}/media", data=data, timeout=60
    )
    resp.raise_for_status()
    container_id = resp.json()["id"]
    logger.info("Created media container %s", container_id)
    return container_id


def wait_until_ready(container_id: str, access_token: str) -> None:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while True:
        resp = requests.get(
            f"{GRAPH_HOST}/{API_VERSION}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=30,
        )
        resp.raise_for_status()
        status = resp.json()["status_code"]
        logger.info("Container %s status: %s", container_id, status)

        if status == "FINISHED":
            return
        if status in TERMINAL_STATUSES:
            raise InstagramPublishError(
                f"Container {container_id} ended in status {status!r}"
            )
        if time.monotonic() >= deadline:
            raise InstagramPublishError(
                f"Container {container_id} did not finish within {POLL_TIMEOUT_SECONDS}s "
                f"(last status: {status!r})"
            )
        time.sleep(POLL_INTERVAL_SECONDS)


def publish_container(ig_user_id: str, container_id: str, access_token: str) -> str:
    resp = requests.post(
        f"{GRAPH_HOST}/{API_VERSION}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=60,
    )
    resp.raise_for_status()
    media_id = resp.json()["id"]
    logger.info("Published media %s", media_id)
    return media_id


def post_photos(ig_user_id: str, image_urls: list[str], caption: str, access_token: str) -> str:
    """Publish one photo, or a carousel when given several."""
    if len(image_urls) == 1:
        container_id = create_container(
            ig_user_id, access_token, image_url=image_urls[0], caption=caption
        )
    else:
        child_ids = [
            create_container(ig_user_id, access_token, image_url=url, is_carousel_item=True)
            for url in image_urls
        ]
        for child_id in child_ids:
            wait_until_ready(child_id, access_token)
        container_id = create_container(
            ig_user_id, access_token, caption=caption, children=child_ids
        )
    wait_until_ready(container_id, access_token)
    return publish_container(ig_user_id, container_id, access_token)

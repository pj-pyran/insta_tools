"""Entry point: post the next queued photo to Instagram, end to end."""

from __future__ import annotations

import logging
import os
import sys
import tempfile

from . import github_relay, instagram_client, token_refresh
from .drive_client import DriveQueue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run() -> None:
    ig_user_id = os.environ["IG_USER_ID"]
    access_token = os.environ["IG_ACCESS_TOKEN"]

    queue = DriveQueue()
    image_file, caption_file = queue.get_next_post()
    caption = queue.download_text(caption_file["id"]) if caption_file else ""
    if not caption_file:
        logger.warning("No caption file found for %s; posting without a caption", image_file["name"])

    with tempfile.TemporaryDirectory() as tmp_dir:
        local_path = os.path.join(tmp_dir, image_file["name"])
        queue.download_file(image_file["id"], local_path)

        asset = github_relay.upload_photo(local_path)
        try:
            instagram_client.post_photo(ig_user_id, asset.download_url, caption, access_token)
        finally:
            github_relay.delete_release(asset)

    posted_ids = [image_file["id"]] + ([caption_file["id"]] if caption_file else [])
    queue.move_to_posted(posted_ids)

    new_token = token_refresh.refresh_access_token(access_token)
    token_refresh.rotate_github_secret(new_token)

    logger.info("Weekly Instagram post completed successfully")


def main() -> int:
    try:
        run()
    except Exception:
        logger.exception("Weekly Instagram post failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

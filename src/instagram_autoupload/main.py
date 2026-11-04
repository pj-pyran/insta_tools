"""Entry point: post the next queued photo to Instagram, end to end."""

from __future__ import annotations

import datetime
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


def run() -> bool:
    """Return True if a post was published."""
    ig_user_id = os.environ["IG_USER_ID"]
    access_token = os.environ["IG_ACCESS_TOKEN"]

    queue = DriveQueue()
    post_date = os.environ.get("POST_DATE") or datetime.date.today().isoformat()
    post = queue.get_post(post_date)
    if post is None:
        logger.info("No post folder named %s in the queue; nothing to post", post_date)
        return False
    image_files, caption_file, folder_id = post
    caption = queue.download_text(caption_file["id"]) if caption_file else ""
    if not caption_file:
        logger.warning("No caption file found for %s; posting without a caption", image_files[0]["name"])
    logger.info("Posting %d photo(s): %s", len(image_files), [f["name"] for f in image_files])

    assets: list[github_relay.ReleaseAsset] = []
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            for image_file in image_files:
                local_path = os.path.join(tmp_dir, image_file["name"])
                queue.download_file(image_file["id"], local_path)
                assets.append(github_relay.upload_photo(local_path))

            instagram_client.post_photos(
                ig_user_id, [a.download_url for a in assets], caption, access_token
            )
    finally:
        for asset in assets:
            github_relay.delete_release(asset)

    posted_ids = [f["id"] for f in image_files] + ([caption_file["id"]] if caption_file else [])
    queue.move_to_posted(posted_ids, post_date, folder_id)

    new_token = token_refresh.refresh_access_token(access_token)
    token_refresh.rotate_github_secret(new_token)

    logger.info("Weekly Instagram post completed successfully")
    return True


def main() -> int:
    try:
        posted = run()
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a") as f:
                f.write(f"posted={'true' if posted else 'false'}\n")
    except Exception:
        logger.exception("Weekly Instagram post failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

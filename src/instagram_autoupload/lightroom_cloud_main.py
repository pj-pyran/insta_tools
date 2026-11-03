"""Entry point: pull newly-tagged Lightroom cloud photos into the Drive queue.

Mirrors the Lightroom Classic plugin's keyword-based workflow using the two
Lightroom cloud album equivalents (see lightroom_cloud.py for why albums,
not keywords, are used here).
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile

from . import image_processing, lightroom_cloud, post_groups
from .drive_client import DriveQueue
from .lightroom_cloud import LightroomCloudClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

CAPTION_TEXT = "\n\nthis was auto-uploaded by a script!"
EXPORT_LONG_SIDE = 2048  # downscaled further to Instagram specs after download


def run() -> None:
    client = LightroomCloudClient()
    client.authenticate()
    client.fetch_catalog_id()

    source_album_id = client.get_or_create_album(lightroom_cloud.SOURCE_ALBUM_NAME)
    exported_album_id = client.get_or_create_album(lightroom_cloud.EXPORTED_ALBUM_NAME)

    source_assets = client.list_album_assets(source_album_id)
    source_asset_ids = set(source_assets)
    already_exported_ids = client.list_album_asset_ids(exported_album_id)
    # Sorted by capture date so sequence numbers follow shooting order.
    pending_asset_ids = sorted(
        source_asset_ids - already_exported_ids, key=lambda a: (source_assets[a][0], a)
    )

    if not pending_asset_ids:
        raise RuntimeError(
            f"No new assets in cloud album {lightroom_cloud.SOURCE_ALBUM_NAME!r}; queue is empty"
        )

    logger.info("Exporting %d cloud asset(s)", len(pending_asset_ids))

    drive = DriveQueue()
    exported_ids: list[str] = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        seq_by_date: dict[str, int] = {}
        for asset_id in pending_asset_ids:
            post_date, original = source_assets[asset_id]
            seq_by_date[post_date] = seq_by_date.get(post_date, 0) + 1
            folder = post_groups.folder_name_for(post_date or None)
            base = post_groups.build_name(seq_by_date[post_date], original or asset_id)
            local_path = os.path.join(tmp_dir, f"{asset_id}.jpg")
            export_id = client.generate_export(asset_id, EXPORT_LONG_SIDE)
            client.download_export(asset_id, export_id, local_path)
            image_processing.crop_and_resize_for_instagram(local_path)

            drive.upload_file(local_path, f"{base}.jpg", "image/jpeg", folder)
            drive.upload_text(CAPTION_TEXT, f"{base}.txt", folder)
            exported_ids.append(asset_id)
            logger.info("Exported cloud asset %s to Drive queue", asset_id)

    client.add_assets_to_album(exported_album_id, exported_ids)

    lightroom_cloud.rotate_github_secret(client.refresh_token)

    logger.info("Lightroom cloud export completed successfully")


def main() -> int:
    try:
        run()
    except Exception:
        logger.exception("Lightroom cloud export failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

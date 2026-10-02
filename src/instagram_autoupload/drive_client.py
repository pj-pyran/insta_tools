"""Google Drive queue: list, download, and archive posted photos."""

from __future__ import annotations

import io
import logging
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from . import selection

logger = logging.getLogger(__name__)

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
IMAGE_MIME_TYPES = ("image/jpeg",)
POSTED_FOLDER_NAME = "posted"


def _build_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=DRIVE_SCOPES,
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


class DriveQueue:
    def __init__(self):
        self.service = _build_service()
        self.folder_id = os.environ["GDRIVE_FOLDER_ID"]
        self._posted_folder_id: str | None = None

    def _list_top_level_files(self) -> list[dict]:
        query = f"'{self.folder_id}' in parents and trashed = false"
        files: list[dict] = []
        page_token = None
        while True:
            response = (
                self.service.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id, name, mimeType, createdTime)",
                    pageToken=page_token,
                )
                .execute()
            )
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return files

    def get_next_post(self) -> tuple[dict, dict | None]:
        """Return (image_file, caption_file_or_None) for the next photo to post."""
        files = self._list_top_level_files()
        images = [f for f in files if f["mimeType"] in IMAGE_MIME_TYPES]
        if not images:
            raise RuntimeError(
                f"No image files found in Drive folder {self.folder_id!r}; queue is empty"
            )

        image_file = selection.choose_next(images)
        base_name = os.path.splitext(image_file["name"])[0]
        caption_file = next(
            (
                f
                for f in files
                if f["mimeType"] == "text/plain"
                and os.path.splitext(f["name"])[0] == base_name
            ),
            None,
        )
        return image_file, caption_file

    def download_file(self, file_id: str, dest_path: str) -> None:
        request = self.service.files().get_media(fileId=file_id)
        with open(dest_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

    def download_text(self, file_id: str) -> str:
        request = self.service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue().decode("utf-8").strip()

    def _get_or_create_posted_folder(self) -> str:
        if self._posted_folder_id:
            return self._posted_folder_id

        query = (
            f"'{self.folder_id}' in parents and trashed = false "
            f"and mimeType = 'application/vnd.google-apps.folder' "
            f"and name = '{POSTED_FOLDER_NAME}'"
        )
        response = self.service.files().list(q=query, fields="files(id)").execute()
        existing = response.get("files", [])
        if existing:
            self._posted_folder_id = existing[0]["id"]
            return self._posted_folder_id

        metadata = {
            "name": POSTED_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [self.folder_id],
        }
        folder = self.service.files().create(body=metadata, fields="id").execute()
        self._posted_folder_id = folder["id"]
        return self._posted_folder_id

    def move_to_posted(self, file_ids: list[str]) -> None:
        posted_folder_id = self._get_or_create_posted_folder()
        for file_id in file_ids:
            self.service.files().update(
                fileId=file_id,
                addParents=posted_folder_id,
                removeParents=self.folder_id,
                fields="id, parents",
            ).execute()
            logger.info("Moved Drive file %s to posted/", file_id)

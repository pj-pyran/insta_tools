"""Google Drive queue: list, download, upload, and archive posted photos."""

from __future__ import annotations

import io
import logging
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaInMemoryUpload, MediaIoBaseDownload

from . import post_groups

logger = logging.getLogger(__name__)

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
IMAGE_MIME_TYPES = ("image/jpeg",)
POSTED_FOLDER_NAME = "posted"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


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

    def _list_children(self, parent_id: str) -> list[dict]:
        query = f"'{parent_id}' in parents and trashed = false"
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

    def _get_or_create_folder(self, name: str, parent_id: str) -> str:
        query = (
            f"'{parent_id}' in parents and trashed = false "
            f"and mimeType = '{FOLDER_MIME_TYPE}' and name = '{name}'"
        )
        existing = self.service.files().list(q=query, fields="files(id)").execute().get("files", [])
        if existing:
            return existing[0]["id"]
        metadata = {"name": name, "mimeType": FOLDER_MIME_TYPE, "parents": [parent_id]}
        return self.service.files().create(body=metadata, fields="id").execute()["id"]

    def get_post(self, post_date: str) -> tuple[list[dict], dict | None, str] | None:
        """Return (image_files, caption_file_or_None, folder_id) for the post
        scheduled on ``post_date`` (YYYY-MM-DD), or None if no such folder.

        Several images means a carousel; see post_groups.py for the layout.
        """
        folders = [
            f
            for f in self._list_children(self.folder_id)
            if f["mimeType"] == FOLDER_MIME_TYPE and f["name"] == post_date
        ]
        if not folders:
            return None
        folder_id = folders[0]["id"]
        files = self._list_children(folder_id)
        images = [f for f in files if f["mimeType"] in IMAGE_MIME_TYPES]
        if not images:
            raise RuntimeError(f"Folder {post_date!r} contains no images")
        post_images = post_groups.carousel_order(images)
        text_files = [f for f in files if f["mimeType"] == "text/plain"]
        return post_images, post_groups.find_caption(post_images, text_files), folder_id

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

    def move_to_posted(self, file_ids: list[str], post_date: str, folder_id: str) -> None:
        """Move posted files to posted/<post_date>/, removing the post folder once empty."""
        posted_root = self._get_or_create_folder(POSTED_FOLDER_NAME, self.folder_id)
        dest = self._get_or_create_folder(post_date, posted_root)
        for file_id in file_ids:
            self.service.files().update(
                fileId=file_id,
                addParents=dest,
                removeParents=folder_id,
                fields="id, parents",
            ).execute()
            logger.info("Moved Drive file %s to posted/%s/", file_id, post_date)
        if not self._list_children(folder_id):
            self.service.files().update(fileId=folder_id, body={"trashed": True}).execute()

    def upload_file(self, local_path: str, dest_name: str, mime_type: str, folder: str) -> str:
        """Upload a local file into the named post folder, returning its file id."""
        parent = self._get_or_create_folder(folder, self.folder_id)
        metadata = {"name": dest_name, "parents": [parent]}
        media = MediaFileUpload(local_path, mimetype=mime_type)
        file = self.service.files().create(body=metadata, media_body=media, fields="id").execute()
        logger.info("Uploaded %s/%s to Drive queue", folder, dest_name)
        return file["id"]

    def upload_text(self, text: str, dest_name: str, folder: str) -> str:
        parent = self._get_or_create_folder(folder, self.folder_id)
        metadata = {"name": dest_name, "parents": [parent]}
        media = MediaInMemoryUpload(text.encode("utf-8"), mimetype="text/plain")
        file = self.service.files().create(body=metadata, media_body=media, fields="id").execute()
        logger.info("Uploaded caption %s/%s to Drive queue", folder, dest_name)
        return file["id"]

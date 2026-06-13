"""Google Drive integration for photo and file storage."""

import json
import logging
import base64
import httpx
from typing import Optional

from config import get_settings

logger = logging.getLogger(__name__)


class DriveManager:
    """Manager for Google Drive uploads."""

    def __init__(self):
        settings = get_settings()
        try:
            service_account_json = base64.b64decode(
                settings.google_service_account_json
            ).decode("utf-8")
            self.creds_dict = json.loads(service_account_json)
            self.folder_id = settings.google_drive_folder_id
            self._credentials = None  # lazy-init, refreshed on expiry
            logger.info("DriveManager initialized")
        except Exception as e:
            logger.error(f"Failed to initialize DriveManager: {e}")
            raise

    async def _get_access_token(self) -> str:
        """Return a valid OAuth token, refreshing automatically when expired."""
        from google.auth.transport.requests import Request
        from google.oauth2.service_account import Credentials

        if self._credentials is None:
            self._credentials = Credentials.from_service_account_info(
                self.creds_dict,
                scopes=["https://www.googleapis.com/auth/drive"],
            )

        if not self._credentials.valid:
            self._credentials.refresh(Request())

        return self._credentials.token

    # ------------------------------------------------------------------ #
    # Public upload methods
    # ------------------------------------------------------------------ #

    async def upload_file_async(
        self,
        file_bytes: bytes,
        filename: str,
        mime_type: str = "application/pdf",
        folder_name: Optional[str] = None,
    ) -> Optional[str]:
        """Upload raw bytes to Google Drive. Returns file_id or None on error."""
        try:
            token = await self._get_access_token()
            parent_id = (
                await self._get_or_create_folder(folder_name, token)
                if folder_name
                else self.folder_id
            )

            metadata = {"name": filename, "parents": [parent_id]}
            headers = {"Authorization": f"Bearer {token}"}

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                    headers=headers,
                    files={
                        "data": ("metadata", json.dumps(metadata), "application/json"),
                        "file": (filename, file_bytes, mime_type),
                    },
                )
                response.raise_for_status()
                file_id = response.json().get("id")

            if file_id:
                await self._make_file_public(file_id, token)
                logger.info(f"Uploaded '{filename}' to Drive folder '{folder_name}': {file_id}")

            return file_id
        except Exception as e:
            logger.error(f"Failed to upload '{filename}' to Drive: {e}")
            return None

    async def upload_photo_from_url(self, photo_url: str, filename: str) -> Optional[str]:
        """Upload photo from URL to Google Drive. Returns public Drive URL or None."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(photo_url)
                response.raise_for_status()
                photo_data = response.content

            token = await self._get_access_token()
            metadata = {"name": filename, "parents": [self.folder_id]}
            headers = {"Authorization": f"Bearer {token}"}

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                    headers=headers,
                    files={
                        "data": ("metadata", json.dumps(metadata), "application/json"),
                        "file": (filename, photo_data),
                    },
                )
                response.raise_for_status()
                file_id = response.json().get("id")

            if file_id:
                await self._make_file_public(file_id, token)
                drive_url = f"https://drive.google.com/file/d/{file_id}/view"
                logger.info(f"Uploaded photo '{filename}' to Drive: {drive_url}")
                return drive_url
            return None
        except httpx.HTTPError as e:
            logger.error(f"HTTP error uploading photo from {photo_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to upload photo from {photo_url}: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    async def _get_or_create_folder(self, folder_name: str, token: str) -> str:
        """Return the Drive ID of a named subfolder, creating it if needed."""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            query = (
                f"name = '{folder_name}' and "
                f"'{self.folder_id}' in parents and "
                "mimeType = 'application/vnd.google-apps.folder' and "
                "trashed = false"
            )
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    "https://www.googleapis.com/drive/v3/files",
                    headers=headers,
                    params={"q": query, "fields": "files(id)"},
                )
                resp.raise_for_status()
                files = resp.json().get("files", [])
                if files:
                    return files[0]["id"]

                # Create it
                resp = await client.post(
                    "https://www.googleapis.com/drive/v3/files",
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "name": folder_name,
                        "mimeType": "application/vnd.google-apps.folder",
                        "parents": [self.folder_id],
                    },
                )
                resp.raise_for_status()
                return resp.json().get("id", self.folder_id)
        except Exception as e:
            logger.warning(f"Could not get/create Drive folder '{folder_name}': {e}")
            return self.folder_id

    async def _make_file_public(self, file_id: str, token: str) -> None:
        """Grant public read access to a Drive file."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"role": "reader", "type": "anyone"},
                )
                resp.raise_for_status()
                logger.info(f"Drive file {file_id} made public")
        except Exception as e:
            logger.warning(f"Failed to make Drive file {file_id} public: {e}")


async def get_drive_manager() -> DriveManager:
    return DriveManager()

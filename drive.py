"""Google Drive integration for photo storage."""

import json
import logging
import base64
import httpx
from typing import Optional

from config import get_settings

logger = logging.getLogger(__name__)


class DriveManager:
    """Manager for Google Drive photo uploads."""

    def __init__(self):
        """Initialize Google Drive client."""
        settings = get_settings()
        try:
            service_account_json = base64.b64decode(
                settings.google_service_account_json
            ).decode("utf-8")
            self.creds_dict = json.loads(service_account_json)
            self.folder_id = settings.google_drive_folder_id
            self.access_token = None
            logger.info("DriveManager initialized")
        except Exception as e:
            logger.error(f"Failed to initialize DriveManager: {e}")
            raise

    async def _get_access_token(self) -> str:
        """Get OAuth access token from service account."""
        if self.access_token:
            return self.access_token

        try:
            from google.auth.transport.requests import Request
            from google.oauth2.service_account import Credentials

            credentials = Credentials.from_service_account_info(
                self.creds_dict,
                scopes=["https://www.googleapis.com/auth/drive"],
            )
            request = Request()
            credentials.refresh(request)
            self.access_token = credentials.token
            return self.access_token
        except Exception as e:
            logger.error(f"Failed to get access token: {e}")
            raise

    async def upload_photo_from_url(
        self,
        photo_url: str,
        filename: str,
    ) -> Optional[str]:
        """Upload photo from URL to Google Drive."""
        try:
            # Download photo
            async with httpx.AsyncClient() as client:
                response = await client.get(photo_url)
                response.raise_for_status()
                photo_data = response.content

            # Get access token
            token = await self._get_access_token()

            # Upload to Google Drive
            headers = {
                "Authorization": f"Bearer {token}",
            }
            metadata = {
                "name": filename,
                "parents": [self.folder_id],
            }

            async with httpx.AsyncClient() as client:
                files = {
                    "data": ("metadata", json.dumps(metadata), "application/json"),
                    "file": (filename, photo_data),
                }
                response = await client.post(
                    "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                    headers=headers,
                    files=files,
                )
                response.raise_for_status()
                result = response.json()
                file_id = result.get("id")

                # Make file public/shareable
                await self._make_file_public(file_id, token)

                # Generate shareable link
                drive_url = f"https://drive.google.com/file/d/{file_id}/view"
                logger.info(f"Uploaded photo {filename} to Drive: {drive_url}")
                return drive_url
        except httpx.HTTPError as e:
            logger.error(f"HTTP error uploading photo: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to upload photo from {photo_url}: {e}")
            return None

    async def _make_file_public(self, file_id: str, token: str) -> None:
        """Make Drive file publicly accessible."""
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            permission = {
                "role": "reader",
                "type": "anyone",
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
                    headers=headers,
                    json=permission,
                )
                response.raise_for_status()
                logger.info(f"File {file_id} made public")
        except Exception as e:
            logger.warning(f"Failed to make file public: {e}")


async def get_drive_manager() -> DriveManager:
    """Get or create Drive manager (dependency injection)."""
    return DriveManager()

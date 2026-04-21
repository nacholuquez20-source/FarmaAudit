"""Evolution API client for AuditBot (WhatsApp integration)."""

import logging
from typing import Optional

import httpx

from config import get_settings
from models import WAHAMessage

logger = logging.getLogger(__name__)


class WAHAClient:
    """Client for Evolution API (WhatsApp)."""

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.waha_url.rstrip("/")
        self.api_key = settings.waha_api_key
        self.instance = settings.waha_session
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"apikey": self.api_key},
            timeout=15,
        )
        logger.info(f"Evolution API client initialized: {self.base_url}")

    async def send_text(self, phone: str, text: str) -> bool:
        """Send text message via Evolution API."""
        try:
            payload = {"number": phone, "text": text}
            response = await self.client.post(
                f"/message/sendText/{self.instance}", json=payload
            )
            response.raise_for_status()
            logger.info(f"Sent text to {phone}")
            return True
        except Exception as e:
            logger.error(f"Failed to send text to {phone}: {e}")
            return False

    async def send_file(
        self, phone: str, file_url: str, caption: Optional[str] = None
    ) -> bool:
        """Send file (photo/document) via Evolution API."""
        try:
            payload = {
                "number": phone,
                "mediatype": "image",
                "media": file_url,
                "caption": caption or "",
            }
            response = await self.client.post(
                f"/message/sendMedia/{self.instance}", json=payload
            )
            response.raise_for_status()
            logger.info(f"Sent file to {phone}")
            return True
        except Exception as e:
            logger.error(f"Failed to send file to {phone}: {e}")
            return False

    async def send_message(self, message: WAHAMessage) -> bool:
        """Send message (text or file)."""
        if message.file_url:
            return await self.send_file(message.phone, message.file_url, message.caption)
        return await self.send_text(message.phone, message.text)

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()


async def get_waha_client() -> WAHAClient:
    """Get Evolution API client (dependency injection)."""
    return WAHAClient()

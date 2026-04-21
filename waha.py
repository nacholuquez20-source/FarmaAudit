"""WAHA (WhatsApp HTTP API) client for AuditBot."""

import logging
from typing import Optional

import httpx

from config import get_settings
from models import WAHAMessage

logger = logging.getLogger(__name__)


class WAHAClient:
    """Client for WAHA WhatsApp API."""

    def __init__(self):
        """Initialize WAHA client."""
        settings = get_settings()
        self.base_url = settings.waha_url
        self.api_key = settings.waha_api_key
        self.session = settings.waha_session
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        logger.info(f"WAHA client initialized: {self.base_url}")

    async def send_text(self, phone: str, text: str) -> bool:
        """Send text message via WAHA."""
        try:
            payload = {
                "session": self.session,
                "chatId": f"{phone}@c.us",
                "text": text,
            }
            response = await self.client.post("/api/sendText", json=payload)
            response.raise_for_status()
            logger.info(f"Sent text to {phone}")
            return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to send text to {phone}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending text to {phone}: {e}")
            return False

    async def send_file(
        self,
        phone: str,
        file_url: str,
        caption: Optional[str] = None,
    ) -> bool:
        """Send file (photo/document) via WAHA."""
        try:
            payload = {
                "session": self.session,
                "chatId": f"{phone}@c.us",
                "url": file_url,
            }
            if caption:
                payload["caption"] = caption

            response = await self.client.post("/api/sendFile", json=payload)
            response.raise_for_status()
            logger.info(f"Sent file to {phone}")
            return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to send file to {phone}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending file to {phone}: {e}")
            return False

    async def send_message(self, message: WAHAMessage) -> bool:
        """Send message (text or file) via WAHA."""
        if message.file_url:
            return await self.send_file(message.phone, message.file_url, message.caption)
        return await self.send_text(message.phone, message.text)

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()


async def get_waha_client() -> WAHAClient:
    """Get or create WAHA client (dependency injection)."""
    return WAHAClient()

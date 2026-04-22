"""Twilio WhatsApp client for AuditBot."""

import logging
from typing import Optional
import asyncio

from twilio.rest import Client

from config import get_settings
from models import WAHAMessage

logger = logging.getLogger(__name__)


class TwilioClient:
    """Client for Twilio WhatsApp."""

    def __init__(self):
        settings = get_settings()
        self.account_sid = settings.twilio_account_sid
        self.auth_token = settings.twilio_auth_token
        self.phone_number = settings.twilio_phone_number
        self.client = Client(self.account_sid, self.auth_token)
        logger.info(f"Twilio WhatsApp client initialized: {self.phone_number}")

    @staticmethod
    def _normalize_whatsapp_number(phone: str) -> str:
        """Format a phone number for Twilio WhatsApp delivery."""
        phone = (phone or "").strip()
        if phone.startswith("whatsapp:"):
            return phone
        if phone.startswith("+"):
            return f"whatsapp:{phone}"
        return f"whatsapp:+{phone}"

    async def send_text(self, phone: str, text: str) -> bool:
        """Send text message via Twilio WhatsApp."""
        try:
            to_number = self._normalize_whatsapp_number(phone)
            from_number = self._normalize_whatsapp_number(self.phone_number)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    body=text,
                    from_=from_number,
                    to=to_number,
                ),
            )
            logger.info(f"Sent text to {phone}")
            return True
        except Exception as e:
            logger.error(f"Failed to send text to {phone}: {e}")
            return False

    async def send_file(
        self, phone: str, file_url: str, caption: Optional[str] = None
    ) -> bool:
        """Send file (photo/document) via Twilio WhatsApp."""
        try:
            to_number = self._normalize_whatsapp_number(phone)
            from_number = self._normalize_whatsapp_number(self.phone_number)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    body=caption or "",
                    media_url=file_url,
                    from_=from_number,
                    to=to_number,
                ),
            )
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

    async def send_punto(
        self, phone: str, numero: int, total: int, area: str, descripcion: str
    ) -> bool:
        """Send a checklist point to auditor."""
        text = f"""PUNTO {numero}/{total} — {area.upper()}
{descripcion}

Mandá audio, foto o texto con lo que observás.
(Podés responder "saltar" para omitir este punto o "pausar" para retomar más tarde)"""
        return await self.send_text(phone, text)

    async def send_resumen_auditoria(
        self,
        phone: str,
        sucursal: str,
        total: int,
        desvios: int,
        omitidos: int,
        detalle_desvios: str,
    ) -> bool:
        """Send audit completion summary to auditor."""
        text = f"""✅ AUDITORÍA COMPLETADA

Sucursal: {sucursal}
Total de puntos: {total}
Desvíos encontrados: {desvios}
Puntos omitidos: {omitidos}

{detalle_desvios}

¡Gracias por tu auditoría!"""
        return await self.send_text(phone, text)


async def get_twilio_client() -> TwilioClient:
    """Get Twilio WhatsApp client (dependency injection)."""
    return TwilioClient()

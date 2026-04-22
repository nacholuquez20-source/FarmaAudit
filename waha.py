"""Twilio WhatsApp client for AuditBot."""

import logging
from typing import Optional, List, Dict
import asyncio

from twilio.rest import Client

from config import get_settings
from models import WAHAMessage, ItemBloque, ResultadoItem

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

    async def send_bloque_prompt(
        self, phone: str, bloque_id: str, bloque_nombre: str, items: List[ItemBloque]
    ) -> bool:
        """Send block prompt with evaluation items."""
        items_text = "\n".join([f"• {item.descripcion}" for item in items])
        text = f"""BLOQUE {bloque_id} — {bloque_nombre.upper()}

Evaluá del 1 al 5 o describí lo que observás:

{items_text}

Podés mandar audio, foto con comentario, o números separados por coma (ej: "3,4,4,5,3,2")"""
        return await self.send_text(phone, text)

    async def send_bloque_confirmacion(
        self,
        phone: str,
        bloque_id: str,
        bloque_nombre: str,
        items: List[ItemBloque],
        resultados: List[ResultadoItem],
    ) -> bool:
        """Send block results confirmation with ✓/⚠️ indicators."""
        lineas = [f"BLOQUE {bloque_id} — {bloque_nombre.upper()}\n"]

        for item, resultado in zip(items, resultados):
            puntaje_str = f"{resultado.puntaje}" if resultado.puntaje else "?"
            if resultado.tiene_desvio:
                lineas.append(f"⚠️ {item.descripcion}: {puntaje_str}")
                if resultado.descripcion_desvio:
                    lineas.append(f"   → {resultado.descripcion_desvio}")
            else:
                lineas.append(f"✓ {item.descripcion}: {puntaje_str}")

        lineas.append("\n¿Está bien? SI / EDITAR / SALTAR BLOQUE")
        text = "\n".join(lineas)
        return await self.send_text(phone, text)

    async def send_resumen_final(
        self,
        phone: str,
        sucursal: str,
        fecha: str,
        puntaje_total: float,
        puntaje_maximo: float,
        resultados_por_bloque: Dict[str, List[ResultadoItem]],
        desvios: int,
        alta: int,
        media: int,
        baja: int,
        stock_verificado: int,
        compromisos: str,
    ) -> bool:
        """Send final audit summary with scores and statistics."""
        porcentaje = int((puntaje_total / puntaje_maximo * 100)) if puntaje_maximo > 0 else 0

        lineas = [
            "✅ AUDITORÍA COMPLETADA",
            f"\nSucursal: {sucursal}",
            f"Fecha: {fecha}",
            f"\nPUNTAJE TOTAL: {puntaje_total:.1f}/{puntaje_maximo:.1f} ({porcentaje}%)",
            "\nDETALLE POR BLOQUE:",
        ]

        for bloque in ["A", "B", "C", "D"]:
            if bloque in resultados_por_bloque:
                items = resultados_por_bloque[bloque]
                puntajes = [r.puntaje for r in items if r.puntaje]
                if puntajes:
                    promedio = sum(puntajes) / len(puntajes)
                    lineas.append(f"  Bloque {bloque}: {promedio:.1f}/5")

        lineas.extend([
            f"\nDESVÍOS: {desvios}",
            f"  🔴 Críticos (Alta): {alta}",
            f"  🟡 Importantes (Media): {media}",
            f"  🟢 Leves (Baja): {baja}",
            f"\nProductos verificados: {stock_verificado}",
            f"Compromisos: {compromisos if compromisos else 'Sin firmar'}",
            "\n¡Gracias por tu auditoría!",
        ])

        text = "\n".join(lineas)
        return await self.send_text(phone, text)

    async def send_alerta_coordinador(
        self, phone: str, sucursal: str, area: str, descripcion: str, severidad: str
    ) -> bool:
        """Send immediate alert to coordinator for high severity findings."""
        icon = "🔴" if severidad == "Alta" else "🟡" if severidad == "Media" else "🟢"
        text = f"""{icon} ALERTA DE AUDITORÍA

Sucursal: {sucursal}
Área: {area}
Severidad: {severidad}

{descripcion}

Acción requerida inmediatamente."""
        return await self.send_text(phone, text)


async def get_twilio_client() -> TwilioClient:
    """Get Twilio WhatsApp client (dependency injection)."""
    return TwilioClient()

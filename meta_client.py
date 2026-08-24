"""Meta WhatsApp Cloud API client for AuditBot."""

import asyncio
import logging
from typing import Optional, List, Dict, Tuple
import httpx

from config import get_settings
from models import WhatsAppMessage, ItemBloque, ResultadoItem

logger = logging.getLogger(__name__)


class MetaClient:
    """Client for Meta WhatsApp Cloud API."""

    BASE_URL = "https://graph.facebook.com/v19.0"

    # Real Meta Cloud API limits (developers.facebook.com/docs/whatsapp/cloud-api).
    MAX_TEXT_BODY_CHARS = 4096
    MAX_INTERACTIVE_BODY_CHARS = 1024
    # NOTE: this is a total across ALL sections combined, not per section.
    # Meta allows up to 10 sections, but no matter how many sections you use
    # the grand total of rows in the message cannot exceed 10.
    MAX_LIST_ROWS_TOTAL = 10
    MAX_LIST_SECTIONS = 10

    def __init__(self):
        settings = get_settings()
        self.phone_number_id = settings.meta_phone_number_id
        self.access_token = settings.meta_access_token
        logger.info(f"Meta WhatsApp client initialized: {self.phone_number_id}")

    @staticmethod
    def _normalize_whatsapp_number(phone: str) -> str:
        """Format a phone number for Meta WhatsApp delivery."""
        phone = (phone or "").strip()
        if phone.startswith("+"):
            return phone
        return f"+{phone}"

    async def _post_with_retry(
        self,
        url: str,
        payload: dict,
        headers: dict,
        timeout: float = 30,
        max_retries: int = 1,
    ) -> httpx.Response:
        """POST to the Graph API with a short retry for transient failures.

        Only retries when we can be reasonably sure Meta never processed the
        request: connection-level failures (the request never reached Meta)
        and 5xx responses (Meta explicitly reports a server-side failure).
        Read timeouts and 4xx responses are NOT retried, since in those
        cases the message may already have been queued/sent by Meta and a
        retry could deliver a duplicate to the user.
        """
        delay = 0.5
        async with httpx.AsyncClient() as client:
            for attempt in range(max_retries + 1):
                try:
                    response = await client.post(url, json=payload, headers=headers, timeout=timeout)
                except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                    if attempt >= max_retries:
                        raise
                    logger.warning(
                        f"Meta API connection error (attempt {attempt + 1}/{max_retries + 1}), retrying: {e}"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue

                if response.status_code >= 500 and attempt < max_retries:
                    logger.warning(
                        f"Meta API returned {response.status_code} "
                        f"(attempt {attempt + 1}/{max_retries + 1}), retrying"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue

                return response
        raise RuntimeError("Meta API retry loop exited without a response")  # pragma: no cover

    async def _get_with_retry(
        self,
        url: str,
        headers: dict,
        timeout: float = 30,
        max_retries: int = 1,
    ) -> httpx.Response:
        """GET from the Graph API with a short retry for transient failures.

        GET requests don't mutate state on Meta's side, so unlike sends it's
        always safe to retry them on any transient error (connection issues,
        timeouts, or 5xx).
        """
        delay = 0.5
        async with httpx.AsyncClient() as client:
            for attempt in range(max_retries + 1):
                try:
                    response = await client.get(url, headers=headers, timeout=timeout)
                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                    if attempt >= max_retries:
                        raise
                    logger.warning(
                        f"Meta API GET error (attempt {attempt + 1}/{max_retries + 1}), retrying: {e}"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue

                if response.status_code >= 500 and attempt < max_retries:
                    logger.warning(
                        f"Meta API GET returned {response.status_code} "
                        f"(attempt {attempt + 1}/{max_retries + 1}), retrying"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue

                return response
        raise RuntimeError("Meta API retry loop exited without a response")  # pragma: no cover

    async def send_text_with_id(self, phone: str, text: str) -> Optional[str]:
        """Send text message and return the WhatsApp message id when Meta provides it."""
        try:
            to_number = self._normalize_whatsapp_number(phone)
            url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
            if text and len(text) > self.MAX_TEXT_BODY_CHARS:
                logger.warning(
                    f"Text body exceeds Meta's {self.MAX_TEXT_BODY_CHARS}-char limit "
                    f"({len(text)} chars), truncating"
                )
                text = text[: self.MAX_TEXT_BODY_CHARS]
            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "text",
                "text": {"body": text},
            }
            headers = {"Authorization": f"Bearer {self.access_token}"}

            response = await self._post_with_retry(url, payload, headers, timeout=30)
            if response.status_code == 200:
                message_id = ""
                try:
                    response_json = response.json()
                    messages = response_json.get("messages") or []
                    if messages and isinstance(messages[0], dict):
                        message_id = str(messages[0].get("id") or "")
                except Exception:
                    logger.warning("Could not parse Meta send_text response body")
                logger.info(f"Sent text to {phone}")
                return message_id or None
            else:
                logger.error(f"Failed to send text to {phone}: Status {response.status_code}")
                logger.error(f"Response body: {response.text}")
                logger.error(f"Payload sent: {payload}")
                logger.error(f"URL: {url}")
                return None
        except Exception as e:
            logger.error(f"Failed to send text to {phone}: {e}")
            return None

    async def send_text(self, phone: str, text: str) -> bool:
        """Send text message via Meta WhatsApp Cloud API."""
        return bool(await self.send_text_with_id(phone, text))

    async def send_file(
        self, phone: str, file_url: str, caption: Optional[str] = None
    ) -> bool:
        """Send image via Meta WhatsApp Cloud API."""
        try:
            to_number = self._normalize_whatsapp_number(phone)
            url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "image",
                "image": {"link": file_url},
            }
            if caption:
                payload["image"]["caption"] = caption
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = await self._post_with_retry(url, payload, headers, timeout=30)
            if response.status_code == 200:
                logger.info(f"Sent image to {phone}")
                return True
            logger.error(f"Failed to send image to {phone}: {response.status_code} {response.text}")
            return False
        except Exception as e:
            logger.error(f"Failed to send image to {phone}: {e}")
            return False

    async def send_image_by_id(
        self,
        phone: str,
        media_id: str,
        caption: Optional[str] = None,
    ) -> bool:
        """Send an image using an existing Meta media_id (no re-upload needed)."""
        try:
            to_number = self._normalize_whatsapp_number(phone)
            url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
            payload: dict = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "image",
                "image": {"id": media_id},
            }
            if caption:
                payload["image"]["caption"] = caption
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = await self._post_with_retry(url, payload, headers, timeout=30)
            if response.status_code == 200:
                logger.info(f"Sent image (id={media_id}) to {phone}")
                return True
            logger.error(f"Failed to send image to {phone}: {response.status_code} {response.text}")
            return False
        except Exception as e:
            logger.error(f"Failed to send image to {phone}: {e}")
            return False

    async def send_image_by_url(
        self,
        phone: str,
        image_url: str,
        caption: Optional[str] = None,
    ) -> bool:
        """Send an image via a public/signed URL (no Meta media_id available —
        ej. una foto que vive en Supabase Storage, no en un mensaje de
        WhatsApp entrante). Mismo patrón que send_document, con type=image."""
        try:
            to_number = self._normalize_whatsapp_number(phone)
            url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
            payload: dict = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "image",
                "image": {"link": image_url},
            }
            if caption:
                payload["image"]["caption"] = caption
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = await self._post_with_retry(url, payload, headers, timeout=30)
            if response.status_code == 200:
                logger.info(f"Sent image by URL to {phone}")
                return True
            logger.error(f"Failed to send image by URL to {phone}: {response.status_code} {response.text}")
            return False
        except Exception as e:
            logger.error(f"Failed to send image by URL to {phone}: {e}")
            return False

    async def send_document(
        self,
        phone: str,
        doc_url: str,
        filename: str,
        caption: Optional[str] = None,
    ) -> bool:
        """Send a PDF/document via Meta WhatsApp Cloud API using a public URL."""
        try:
            to_number = self._normalize_whatsapp_number(phone)
            url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "document",
                "document": {"link": doc_url, "filename": filename},
            }
            if caption:
                payload["document"]["caption"] = caption
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = await self._post_with_retry(url, payload, headers, timeout=30)
            if response.status_code == 200:
                logger.info(f"Sent document '{filename}' to {phone}")
                return True
            logger.error(f"Failed to send document to {phone}: {response.status_code} {response.text}")
            return False
        except Exception as e:
            logger.error(f"Failed to send document to {phone}: {e}")
            return False

    async def send_template(
        self,
        phone: str,
        template_name: str,
        language_code: str = "es_AR",
        body_params: Optional[List[str]] = None,
        button_params: Optional[List[Dict[str, str]]] = None,
    ) -> bool:
        """Send a pre-approved WhatsApp message template (business-initiated messages,
        outside the 24h session window). The template must already be approved in Meta
        Business Manager before this call will succeed — see
        ARQUITECTURA_DESVIOS_CAMPANIAS.md, seccion 2.4, for the templates a produccion
        necesita (campana_nueva_sucursal, desvio_correccion_revisada,
        campana_recordatorio_tareas, insumo_solicitud_confirmada, sla_auditor_revision_vencido).

        Args:
            phone: Phone number.
            template_name: Exact template name registered in Meta.
            language_code: Template locale (e.g. "es_AR", "es").
            body_params: Positional {{1}}, {{2}}... values for the BODY component, in order.
            button_params: Optional list of dicts {"sub_type": "quick_reply", "index": "0",
                "payload": "..."} for interactive button components on the template.
        """
        try:
            to_number = self._normalize_whatsapp_number(phone)
            url = f"{self.BASE_URL}/{self.phone_number_id}/messages"

            components = []
            if body_params:
                components.append({
                    "type": "body",
                    "parameters": [{"type": "text", "text": param} for param in body_params],
                })
            if button_params:
                for button in button_params:
                    components.append({
                        "type": "button",
                        "sub_type": button.get("sub_type", "quick_reply"),
                        "index": button.get("index", "0"),
                        "parameters": [{"type": "payload", "payload": button.get("payload", "")}],
                    })

            payload: dict = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language_code},
                },
            }
            if components:
                payload["template"]["components"] = components

            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = await self._post_with_retry(url, payload, headers, timeout=30)
            if response.status_code == 200:
                logger.info(f"Sent template '{template_name}' to {phone}")
                return True
            logger.error(f"Failed to send template '{template_name}' to {phone}: {response.status_code} {response.text}")
            return False
        except Exception as e:
            logger.error(f"Failed to send template '{template_name}' to {phone}: {e}")
            return False

    async def send_message(self, message: WhatsAppMessage) -> bool:
        """Send message (text or file)."""
        if message.file_url:
            return await self.send_file(message.phone, message.file_url, message.caption)
        return await self.send_text(message.phone, message.text)

    async def download_media_with_metadata(self, media_id: str) -> Tuple[bytes, str]:
        """Download media bytes and MIME type from Meta CDN."""
        metadata_url = f"{self.BASE_URL}/{media_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        metadata_response = await self._get_with_retry(metadata_url, headers, timeout=30)
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
        media_url = metadata.get("url")
        mime_type = metadata.get("mime_type") or "application/octet-stream"
        if not media_url:
            raise ValueError(f"Meta media URL missing for media_id={media_id}")

        media_response = await self._get_with_retry(media_url, headers, timeout=60)
        media_response.raise_for_status()
        return media_response.content, mime_type

    async def download_media(self, media_id: str) -> bytes:
        """Download media bytes from Meta CDN."""
        content, _ = await self.download_media_with_metadata(media_id)
        return content

    async def download_media_by_url(self, media_url: str) -> Tuple[bytes, str]:
        """Re-download bytes + mime type from a previously-resolved Meta CDN
        media URL.

        Meta's resolved media URLs require the same Authorization header as
        the rest of the Graph API (they are not public links) and are only
        valid for a short window after being issued — best-effort, callers
        must handle failure (raises on any error, same as download_media).
        """
        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = await self._get_with_retry(media_url, headers, timeout=60)
        response.raise_for_status()
        mime_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        return response.content, mime_type

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

    async def send_quick_reply(
        self,
        phone: str,
        body: str,
        buttons: List[Dict[str, str]]
    ) -> bool:
        """Send quick reply message with button options.

        Args:
            phone: Phone number
            body: Message body text
            buttons: List of dicts with 'id' and 'title' keys
                    Example: [{'id': 'si', 'title': 'Sí'}, {'id': 'no', 'title': 'No'}]
        """
        try:
            to_number = self._normalize_whatsapp_number(phone)
            url = f"{self.BASE_URL}/{self.phone_number_id}/messages"

            if len(buttons) > 3:
                logger.warning(
                    f"send_quick_reply got {len(buttons)} buttons, Meta allows max 3; extra ones dropped"
                )

            # Build quick reply buttons
            quick_reply_buttons = []
            for btn in buttons[:3]:  # Max 3 buttons for quick reply
                quick_reply_buttons.append({
                    "type": "reply",
                    "reply": {
                        "id": btn.get("id", ""),
                        "title": btn.get("title", "")[:20],
                    }
                })

            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": body[:self.MAX_INTERACTIVE_BODY_CHARS]
                    },
                    "action": {
                        "buttons": quick_reply_buttons
                    }
                }
            }

            headers = {"Authorization": f"Bearer {self.access_token}"}

            response = await self._post_with_retry(url, payload, headers, timeout=30)
            if response.status_code == 200:
                logger.info(f"Sent quick reply message to {phone} with {len(buttons)} buttons")
                return True
            else:
                logger.error(f"Failed to send quick reply to {phone}: Status {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send quick reply to {phone}: {e}")
            return False

    async def send_list_message(
        self,
        phone: str,
        header: str,
        body: str,
        footer: str,
        button_text: str,
        options: List[Dict[str, str]]
    ) -> bool:
        """Send interactive list message with selectable options.

        Args:
            phone: Phone number
            header: Message header (max 60 chars)
            body: Message body text
            footer: Footer text (optional, max 60 chars)
            button_text: Button label (max 20 chars)
            options: List of dicts with 'id' and 'title' keys
                    Example: [{'id': '1', 'title': 'Muy malo'}, ...]

        IMPORTANT (real Meta limit, easy to get wrong): WhatsApp list messages
        allow up to 10 sections, but the row budget is NOT 10-per-section —
        it's a maximum of MAX_LIST_ROWS_TOTAL (10) rows across ALL sections
        combined. A single-section list (as built here) can therefore never
        carry more than 10 options; callers with more items must paginate
        or use a different UI (e.g. plain numbered text), not a bigger list.
        """
        try:
            to_number = self._normalize_whatsapp_number(phone)
            url = f"{self.BASE_URL}/{self.phone_number_id}/messages"

            if len(options) > self.MAX_LIST_ROWS_TOTAL:
                logger.error(
                    f"send_list_message got {len(options)} options for {phone}, but Meta allows "
                    f"a maximum of {self.MAX_LIST_ROWS_TOTAL} rows total across all sections. "
                    "Refusing to send a malformed request; caller must paginate or use plain text."
                )
                return False

            # Build rows from options
            rows = []
            for opt in options:
                rows.append({
                    "id": opt.get("id", ""),
                    "title": opt.get("title", "")[:24],  # Max 24 chars
                    "description": opt.get("description", "")[:72]  # Max 72 chars
                })

            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "header": {
                        "type": "text",
                        "text": header[:60]
                    },
                    "body": {
                        "text": body[:self.MAX_INTERACTIVE_BODY_CHARS]
                    },
                    "footer": {
                        "text": footer[:60]
                    } if footer else None,
                    "action": {
                        "button": button_text[:20],
                        "sections": [
                            {
                                "title": "Opciones",
                                "rows": rows
                            }
                        ]
                    }
                }
            }

            # Remove footer if empty
            if not footer:
                del payload["interactive"]["footer"]

            headers = {"Authorization": f"Bearer {self.access_token}"}

            response = await self._post_with_retry(url, payload, headers, timeout=30)
            if response.status_code == 200:
                logger.info(f"Sent list message to {phone} with {len(options)} options")
                return True
            else:
                logger.error(f"Failed to send list message to {phone}: Status {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send list message to {phone}: {e}")
            return False


    async def check_webhook_subscription(self) -> Optional[dict]:
        """Chequea contra la Graph API si el webhook de WhatsApp sigue activo y
        suscripto al campo 'messages'. Usa un app access token (app_id|app_secret),
        no el token de envío de mensajes — por eso requiere META_APP_ID además del
        META_APP_SECRET ya usado para verificar firmas.

        Devuelve None si falta configuración o si la llamada a Meta falla (fallo
        de red no implica que el webhook esté roto, así que el caller no debe
        alertar en ese caso). Si puede chequear, devuelve un dict con 'healthy',
        'callback_url', 'active' y 'fields' para loguear el detalle.
        """
        settings = get_settings()
        if not settings.meta_app_id or not settings.meta_app_secret:
            return None

        app_token = f"{settings.meta_app_id}|{settings.meta_app_secret}"
        url = f"{self.BASE_URL}/{settings.meta_app_id}/subscriptions"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params={"access_token": app_token}, timeout=30)
        except Exception as e:
            logger.warning(f"No se pudo chequear la suscripción del webhook (red): {e}")
            return None

        if response.status_code != 200:
            logger.warning(f"Chequeo de webhook: Meta devolvió {response.status_code} {response.text}")
            return None

        subs = response.json().get("data", [])
        wa_sub = next((s for s in subs if s.get("object") == "whatsapp_business_account"), None)
        if not wa_sub:
            return {"healthy": False, "callback_url": None, "active": False, "fields": []}

        fields = [f.get("name") for f in wa_sub.get("fields", [])]
        active = bool(wa_sub.get("active"))
        return {
            "healthy": active and "messages" in fields,
            "callback_url": wa_sub.get("callback_url"),
            "active": active,
            "fields": fields,
        }


async def get_meta_client() -> MetaClient:
    """Get Meta WhatsApp client (dependency injection)."""
    return MetaClient()

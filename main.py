"""FastAPI application for AuditBot webhook and background jobs."""

import logging
from datetime import datetime, timedelta, timezone
import json
import asyncio
import uuid
from collections import OrderedDict

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
from pydantic import BaseModel
from supabase import create_client, Client

from config import get_settings
from models import WhatsAppPayload, ConversationState, RESPUESTA_CONFIG
from router import ConversationRouter
from meta_client import MetaClient
from supabase_manager import SupabaseManager
from init_supabase import init_supabase_schema

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AuditBot", version="1.0.0")
settings = get_settings()
scheduler = AsyncIOScheduler()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class EncargadoNotificationRequest(BaseModel):
    id_gestion: str
    telefono_encargado: str
    descripcion_desvio: str
    sucursal: str | None = None

# Lazy initialization - these will be created on demand
router = None
sheets = None

# Message deduplication cache: {message_id: (timestamp, phone)}
# TTL: 5 minutes (prevents reprocessing of Meta retries)
_processed_messages: OrderedDict = OrderedDict()
_processing_messages: set[str] = set()
_message_lock = asyncio.Lock()
_MESSAGE_TTL_SECONDS = 300
_supabase_client: Client | None = None
_dedup_store_available: bool | None = None
_last_reminder_sent: dict[str, tuple[datetime, int]] = {}  # {id_sesion: (last_reminder_timestamp, reminders_sent)}


def _get_supabase_client() -> Client | None:
    """Create Supabase client lazily for distributed deduplication."""
    global _supabase_client, _dedup_store_available
    if _supabase_client is not None:
        return _supabase_client
    if _dedup_store_available is False:
        return None

    supabase_url = settings.supabase_url
    supabase_key = settings.supabase_service_key
    if not supabase_url or not supabase_key:
        _dedup_store_available = False
        return None

    try:
        _supabase_client = create_client(supabase_url, supabase_key)
        _dedup_store_available = True
    except Exception as exc:
        logger.warning(f"Supabase dedup disabled: client init failed: {exc}")
        _dedup_store_available = False
        return None

    return _supabase_client


def _claim_message_distributed(message_id: str, phone: str) -> bool:
    """Claim a message ID in shared storage to prevent cross-instance duplicates."""
    global _dedup_store_available
    client = _get_supabase_client()
    if client is None:
        return True

    try:
        client.table("webhook_dedup").insert({
            "message_id": message_id,
            "phone": phone,
            "claimed_at": datetime.utcnow().isoformat(),
        }).execute()
        return True
    except Exception as exc:
        error_text = str(exc).lower()
        if "duplicate key" in error_text or "already exists" in error_text or "23505" in error_text:
            return False
        if "webhook_dedup" in error_text and "does not exist" in error_text:
            logger.warning("Supabase dedup disabled: webhook_dedup table not found")
            _dedup_store_available = False
            return True
        logger.warning(f"Supabase dedup claim failed, falling back to in-memory only: {exc}")
        return True


def _release_message_distributed(message_id: str) -> None:
    """Release distributed claim on processing failure (allow safe retry)."""
    client = _get_supabase_client()
    if client is None:
        return
    try:
        client.table("webhook_dedup").delete().eq("message_id", message_id).execute()
    except Exception as exc:
        logger.warning(f"Failed to release distributed dedup claim for {message_id}: {exc}")


def _is_message_processed(message_id: str) -> bool:
    """Check if message was already processed (within TTL)."""
    if message_id not in _processed_messages:
        return False
    timestamp, _ = _processed_messages[message_id]
    if datetime.utcnow() - timestamp > timedelta(seconds=_MESSAGE_TTL_SECONDS):
        del _processed_messages[message_id]
        return False
    return True


async def _mark_message_processed(message_id: str, phone: str) -> None:
    """Mark message as processed."""
    async with _message_lock:
        _processed_messages[message_id] = (datetime.utcnow(), phone)
        _processing_messages.discard(message_id)
        if len(_processed_messages) > 1000:
            _processed_messages.popitem(last=False)


async def _claim_message_for_processing(message_id: str, phone: str) -> bool:
    """Atomically claim a message ID to avoid duplicate concurrent processing."""
    async with _message_lock:
        if _is_message_processed(message_id):
            return False
        if message_id in _processing_messages:
            return False
        if not _claim_message_distributed(message_id, phone):
            return False
        _processing_messages.add(message_id)
        return True


async def _release_message_claim(message_id: str) -> None:
    """Release in-flight claim if processing failed."""
    async with _message_lock:
        _processing_messages.discard(message_id)
    _release_message_distributed(message_id)

def get_router():
    """Get or create conversation router."""
    global router
    if router is None:
        router = ConversationRouter()
    return router

def get_sheets():
    """Get or create sheets manager."""
    global sheets
    if sheets is None:
        sheets = SupabaseManager()
    return sheets


@app.on_event("startup")
async def startup_event():
    """Initialize background jobs on startup."""
    logger.info("Starting AuditBot...")
    init_supabase_schema()

    # Start scheduler
    scheduler.add_job(
        check_expired_confirmations,
        "interval",
        minutes=settings.timeout_check_interval,
        id="timeout_check",
        max_instances=1,  # Prevent concurrent executions
    )
    scheduler.add_job(
        check_expired_audit_sessions,
        "interval",
        minutes=settings.timeout_check_interval,
        id="audit_timeout_check",
        max_instances=1,  # Prevent concurrent executions
    )
    scheduler.add_job(
        check_incomplete_respuestas_timeout,
        "interval",
        seconds=30,
        id="respuesta_timeout_check",
        max_instances=1,
    )
    scheduler.add_job(
        daily_summary_job,
        "cron",
        hour=23,  # UTC (20:00 ART = 23:00 UTC)
        minute=0,
        id="daily_summary",
        timezone=pytz.UTC,
        max_instances=1,  # Prevent concurrent executions
    )
    # Disabled: Using Supabase directly, no longer syncing from Google Sheets
    # scheduler.add_job(
    #     sync_sheets_to_supabase,
    #     "interval",
    #     minutes=5,
    #     id="sheets_supabase_sync",
    #     max_instances=1,
    # )
    scheduler.start()

    logger.info("Background jobs started")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    scheduler.shutdown()
    logger.info("AuditBot shutdown")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/send-encargado-notification")
async def send_encargado_notification(payload: EncargadoNotificationRequest):
    """Send a WhatsApp notification to the branch manager for one deviation."""
    telefono = "".join(ch for ch in payload.telefono_encargado if ch.isdigit())
    if not telefono:
        raise HTTPException(status_code=400, detail="telefono_encargado is required")

    gestion = get_sheets().get_gestion_by_id(payload.id_gestion)
    sucursal = payload.sucursal or (gestion or {}).get("sucursal") or "tu sucursal"
    descripcion = payload.descripcion_desvio or (gestion or {}).get("desvio") or "desvio pendiente"
    if len(descripcion) > 420:
        descripcion = f"{descripcion[:417]}..."

    message = (
        f"FarmaAudit: tenes un desvio pendiente para corregir en {sucursal}.\n\n"
        f"ID: {payload.id_gestion}\n"
        f"Detalle: {descripcion}\n\n"
        "Responde este WhatsApp para ver tus desvios pendientes, seleccionar uno y enviar la correccion."
    )

    meta_client = MetaClient()
    sent = await meta_client.send_text(telefono, message)
    if not sent:
        raise HTTPException(status_code=502, detail="No se pudo enviar el WhatsApp")

    return {"status": "ok"}


# @app.get("/sync-now")
# async def sync_now():
#     """Manual sync endpoint for testing."""
#     # Disabled: using Supabase directly, no longer syncing from Google Sheets
#     pass


@app.get("/webhook")
async def webhook_verify(request: Request):
    """Meta WhatsApp webhook verification (GET)."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == settings.meta_verify_token:
        logger.info("Webhook verified with Meta")
        return PlainTextResponse(challenge)
    else:
        logger.warning(f"Webhook verification failed: mode={mode}, token_match={token == settings.meta_verify_token}")
        raise HTTPException(status_code=403, detail="Forbidden")


@app.post("/webhook")
async def webhook(request: Request):
    """Meta WhatsApp Cloud API webhook entry point."""
    correlation_id = str(uuid.uuid4())[:8]  # Short correlation ID for logs
    message_id = ""
    message_claimed = False
    processed_successfully = False
    try:
        data = await request.json()

        # Extract messages from Meta's nested structure
        entry = data.get("entry", [])
        if not entry:
            logger.debug(f"[{correlation_id}] Webhook received but no entry data")
            return {"status": "ok"}

        changes = entry[0].get("changes", [])
        if not changes:
            logger.debug(f"[{correlation_id}] Webhook received but no changes")
            return {"status": "ok"}

        value = changes[0].get("value", {})
        messages = value.get("messages", [])

        if not messages:
            logger.debug(f"[{correlation_id}] Webhook received but no messages (might be status update)")
            return {"status": "ok"}

        msg = messages[0]
        telefono = msg.get("from", "")
        if not telefono:
            logger.warning(f"[{correlation_id}] Received payload without from number")
            return {"status": "invalid_payload"}

        # Normalize phone to digits only
        telefono = "".join(ch for ch in telefono if ch.isdigit())

        # Check for duplicate message (Meta redelivery protection)
        message_id = msg.get("id", "")
        context_message_id = str((msg.get("context") or {}).get("id") or "")
        if message_id:
            message_claimed = await _claim_message_for_processing(message_id, telefono)
            if not message_claimed:
                logger.info(f"[{correlation_id}] Duplicate/in-flight message detected (msg_id: {message_id}, phone: {telefono}). Skipping.")
                return {"status": "ok", "result": "duplicate_skipped"}

        # Extract message content based on type
        tipo = msg.get("type", "text")
        contenido = None
        media_url = None
        media_id = None
        mime_type = None

        if tipo == "text":
            contenido = msg.get("text", {}).get("body", "")
        elif tipo == "audio":
            audio = msg.get("audio", {})
            media_id = audio.get("id")
            mime_type = audio.get("mime_type")
            if media_id:
                # TODO: Download audio from Meta API using media_id
                # media_url = await _get_meta_media_url(media_id)
                contenido = f"[Audio message {media_id}]"
        elif tipo == "image":
            image = msg.get("image", {})
            media_id = image.get("id")
            mime_type = image.get("mime_type")
            contenido = image.get("caption", "")
            if media_id:
                # TODO: Download image from Meta API using media_id
                # media_url = await _get_meta_media_url(media_id)
                pass

        payload = WhatsAppPayload(
            telefono=telefono,
            tipo=tipo,
            contenido=contenido,
            media_url=media_url,
            media_id=media_id,
            mime_type=mime_type,
            message_id=message_id,
            context_message_id=context_message_id,
        )

        logger.info(
            f"[{correlation_id}] Received message from {payload.telefono} "
            f"(type: {payload.tipo}, msg_id: {message_id}, context_id: {context_message_id or 'none'})"
        )

        meta_client = MetaClient()
        route = get_router()
        result = await route.handle_message(payload, meta_client)

        # Mark message as processed (after successful processing)
        if message_id:
            await _mark_message_processed(message_id, telefono)
            processed_successfully = True

        logger.info(f"[{correlation_id}] Processed message result: {result}")
        return {"status": "ok", "result": result}
    except Exception as e:
        import traceback
        logger.error(f"[{correlation_id}] Webhook error: {e}")
        logger.error(f"[{correlation_id}] Traceback: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)}
    finally:
        if message_id and message_claimed and not processed_successfully:
            await _release_message_claim(message_id)


async def check_expired_confirmations():
    """Background job: Check and remove expired pending confirmations."""
    try:
        sheets = get_sheets()
        expired = sheets.get_expired_pendientes()
        meta_client = MetaClient()

        for pendiente in expired:
            logger.info(f"Timeout expired for {pendiente.telefono_auditor}")

            # Notify auditor
            await meta_client.send_text(
                pendiente.telefono_auditor,
                "â° Tu confirmaciÃ³n expirÃ³. EnvÃ­ame un nuevo hallazgo cuando estÃ©s listo.",
            )

            # Reset conversation state
            sheets.update_conversacion(
                telefono=pendiente.telefono_auditor,
                estado=ConversationState.IDLE,
            )

            # Delete pendiente
            sheets.delete_pendiente(pendiente.id_temp)

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired confirmations")
    except Exception as e:
        logger.error(f"Error in timeout check job: {e}")


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


async def check_incomplete_respuestas_timeout():
    """Background job: prompt, auto-complete or discard incomplete collected responses."""
    try:
        sheets = get_sheets()
        meta_client = MetaClient()
        route = get_router()
        respuestas = sheets.get_respuestas_incompletas_timeout(
            RESPUESTA_CONFIG["timeout_sin_actividad_segundos"]
        )
        now = datetime.now(timezone.utc)

        for respuesta in respuestas:
            last_message = _parse_utc_timestamp(respuesta.timestamp_ultimo_mensaje)
            if not last_message:
                continue

            inactive_seconds = (now - last_message).total_seconds()
            if inactive_seconds >= RESPUESTA_CONFIG["timeout_max_segundos"]:
                sheets.update_respuesta_pregunta(
                    respuesta.id,
                    estado="descartada",
                    razon_descarte="timeout_max",
                )
                sheets.create_respuesta_audit_log(
                    respuesta.id,
                    "descartada_timeout",
                    {"segundos": inactive_seconds},
                )
                sheets.update_conversacion(
                    telefono=respuesta.telefono_auditor,
                    estado=ConversationState.IDLE,
                    id_respuesta_actual="",
                )
                await meta_client.send_text(
                    respuesta.telefono_auditor,
                    "Timeout: tu respuesta fue descartada por inactividad. Escribi INICIO para retomar.",
                )
                continue

            if (
                RESPUESTA_CONFIG.get("auto_complete_enabled", False)
                and inactive_seconds >= RESPUESTA_CONFIG["timeout_auto_complete_segundos"]
            ):
                conv = sheets.get_conversacion(respuesta.telefono_auditor)
                payload = WhatsAppPayload(
                    telefono=respuesta.telefono_auditor,
                    tipo="text",
                    contenido="LISTO",
                )
                if conv:
                    await meta_client.send_text(
                        respuesta.telefono_auditor,
                        "Auto-completando tu respuesta por inactividad...",
                    )
                    await route._complete_respuesta_collection(  # noqa: SLF001 - internal orchestration for scheduler
                        respuesta,
                        conv,
                        payload,
                        meta_client,
                        auto_complete=True,
                        force=True,
                    )
                continue

            if not respuesta.timeout_prompt_enviado:
                await meta_client.send_text(
                    respuesta.telefono_auditor,
                    "Ya terminaste de enviar tu respuesta? Escribi LISTO para continuar, o segui enviando mensajes.",
                )
                sheets.update_respuesta_pregunta(
                    respuesta.id,
                    timeout_prompt_enviado=True,
                )
                sheets.create_respuesta_audit_log(
                    respuesta.id,
                    "timeout_prompt_enviado",
                    {"segundos": inactive_seconds},
                )
    except Exception as e:
        logger.error(f"Error in check_incomplete_respuestas_timeout: {e}", exc_info=True)


async def check_expired_audit_sessions():
    """Background job: Check for expired audit sessions (15 min timeout)."""
    try:
        sheets = get_sheets()
        expired_sesiones = sheets.get_sesiones_activas_expiradas(timeout_min=15)
        meta_client = MetaClient()

        for sesion in expired_sesiones:
            timestamp_raw = (sesion.timestamp_ultimo_punto or "").strip()
            if not timestamp_raw:
                continue

            try:
                last_update = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
            except ValueError:
                logger.warning(f"Invalid timestamp_ultimo_punto for session {sesion.id_sesion}: {timestamp_raw}")
                continue

            now_utc = datetime.now(timezone.utc)
            now_local = datetime.now()
            if last_update.tzinfo is not None:
                elapsed_minutes = (now_utc - last_update.astimezone(timezone.utc)).total_seconds() / 60
            else:
                # Backward compatibility for existing naive timestamps stored as local time.
                elapsed_minutes = (now_local - last_update).total_seconds() / 60

            # After 60 minutes, auto-omit the point and advance
            if elapsed_minutes >= 60:
                logger.info(f"Auto-omitting point due to inactivity: {sesion.id_sesion}")
                omitidos = json.loads(sesion.omitidos_json) if sesion.omitidos_json else []
                omitidos.append(sesion.punto_actual)
                sesion.punto_actual += 1
                sesion.timestamp_ultimo_punto = now_utc.isoformat()

                # Update session
                sheets.update_sesion(
                    id_sesion=sesion.id_sesion,
                    estado=sesion.estado,
                    timestamp_ultimo_punto=sesion.timestamp_ultimo_punto,
                    punto_actual=sesion.punto_actual,
                    omitidos_json=json.dumps(omitidos),
                )

                # Notify auditor
                await meta_client.send_text(
                    sesion.telefono_auditor,
                    "Punto omitido automáticamente por inactividad (60+ min). Continuando...",
                )

                # Move to next point if not finished
                checklist = sheets.get_checklist()
                if sesion.punto_actual < len(checklist):
                    punto = checklist[sesion.punto_actual]
                    await meta_client.send_text(
                        sesion.telefono_auditor,
                        f"""Punto {punto.punto_orden}/{sesion.total_puntos}:
{punto.area} - {punto.descripcion}

Tu evaluación:""",
                    )
                # Clear reminder tracking for this session
                _last_reminder_sent.pop(sesion.id_sesion, None)
                continue

            # Send reminder only once every 15 minutes (up to 3 reminders)
            reminder_state = _last_reminder_sent.get(sesion.id_sesion)
            last_reminder = reminder_state[0] if reminder_state else None
            reminders_sent = reminder_state[1] if reminder_state else 0

            # Check if reminder is due and we haven't exceeded 3 reminders.
            reminder_due = last_reminder is None or (now_utc - last_reminder).total_seconds() >= 900  # 900 = 15 min

            if reminder_due and reminders_sent < 3:
                reminders_sent += 1
                _last_reminder_sent[sesion.id_sesion] = (now_utc, reminders_sent)
                logger.info(f"Audit session timeout for {sesion.telefono_auditor}: {sesion.id_sesion} (reminder #{reminders_sent})")
                checklist = sheets.get_checklist()
                if sesion.punto_actual < len(checklist):
                    punto = checklist[sesion.punto_actual]
                    await meta_client.send_text(
                        sesion.telefono_auditor,
                        f"""Recordatorio: estás en el punto {punto.punto_orden}/{sesion.total_puntos}.
Mandá tu observación o escribe 'saltar'.""",
                    )

        if expired_sesiones:
            logger.info(f"Checked {len(expired_sesiones)} expired audit sessions")
    except Exception as e:
        logger.error(f"Error in audit timeout check job: {e}")
async def daily_summary_job():
    """Background job: Generate and send daily summary."""
    try:
        settings = get_settings()
        if not settings.coordinador_tel:
            logger.warning("COORDINADOR_TEL not configured")
            return

        # Get today's reports
        # TODO: Implement query to get today's reports from Reportes sheet
        # This would require extending SheetsManager with a method to query by date

        summary = f"""ðŸ“Š **Resumen Diario AuditBot**

Fecha: {datetime.now().strftime('%Y-%m-%d')}

[Resumen en construcciÃ³n]

Para mÃ¡s detalles, consulta la hoja de Reportes."""

        meta_client = MetaClient()
        await meta_client.send_text(settings.coordinador_tel, summary)

        logger.info("Daily summary sent to coordinator")
    except Exception as e:
        logger.error(f"Error in daily summary job: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )

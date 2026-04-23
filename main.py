"""FastAPI application for AuditBot webhook and background jobs."""

import logging
from datetime import datetime
import json

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

from config import get_settings
from models import WAHAPayload, ConversationState
from router import ConversationRouter
from meta_client import MetaClient
from sheets import SheetsManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AuditBot", version="1.0.0")
settings = get_settings()
scheduler = AsyncIOScheduler()

# Lazy initialization - these will be created on demand
router = None
sheets = None

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
        sheets = SheetsManager()
    return sheets


@app.on_event("startup")
async def startup_event():
    """Initialize background jobs on startup."""
    logger.info("Starting AuditBot...")

    # Start scheduler
    scheduler.add_job(
        check_expired_confirmations,
        "interval",
        minutes=settings.timeout_check_interval,
        id="timeout_check",
    )
    scheduler.add_job(
        check_expired_audit_sessions,
        "interval",
        minutes=settings.timeout_check_interval,
        id="audit_timeout_check",
    )
    scheduler.add_job(
        daily_summary_job,
        "cron",
        hour=23,  # UTC (20:00 ART = 23:00 UTC)
        minute=0,
        id="daily_summary",
        timezone=pytz.UTC,
    )
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


@app.get("/qr")
async def qr_info():
    """Legacy endpoint kept for compatibility in Meta mode."""
    return HTMLResponse(
        content="""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>AuditBot Meta</title>
            <style>
                body { font-family: Arial, sans-serif; background: #f6f7fb; color: #1f2937; margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px; }
                .card { max-width: 720px; width: 100%; background: white; border-radius: 16px; padding: 32px; box-shadow: 0 14px 40px rgba(15, 23, 42, 0.12); }
                h1 { margin: 0 0 12px; font-size: 28px; }
                p { line-height: 1.6; margin: 12px 0; }
                code { background: #eef2ff; padding: 2px 6px; border-radius: 6px; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>AuditBot en modo Meta</h1>
                <p>Este proyecto usa Meta WhatsApp Cloud API para conectarse a WhatsApp.</p>
                <p>La integración activa es Meta, y el webhook debe apuntar a <code>/webhook</code>.</p>
                <p>Si querés verificar conectividad, revisá los logs de Railway y confirmá que Meta esté enviando eventos al webhook.</p>
            </div>
        </body>
        </html>
        """,
        media_type="text/html",
    )


@app.get("/qr-legacy")
async def get_qr_legacy():
    """Legacy endpoint kept only for compatibility."""
    return HTMLResponse(
        content="""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>AuditBot Legacy</title>
            <style>
                body { font-family: Arial, sans-serif; background: #f6f7fb; color: #1f2937; margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px; }
                .card { max-width: 720px; width: 100%; background: white; border-radius: 16px; padding: 32px; box-shadow: 0 14px 40px rgba(15, 23, 42, 0.12); }
                h1 { margin: 0 0 12px; font-size: 28px; }
                p { line-height: 1.6; margin: 12px 0; }
                code { background: #eef2ff; padding: 2px 6px; border-radius: 6px; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>Ruta legacy</h1>
                <p>La integración activa es Meta WhatsApp Cloud API.</p>
                <p>Usá <code>/webhook</code> para recibir mensajes.</p>
            </div>
        </body>
        </html>
        """,
        media_type="text/html",
    )

@app.get("/webhook")
async def webhook_verify(request: Request):
    """Meta WhatsApp webhook verification (GET)."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == settings.meta_verify_token:
        logger.info("Webhook verified with Meta")
        return challenge
    else:
        logger.warning(f"Webhook verification failed: mode={mode}, token_match={token == settings.meta_verify_token}")
        return {"error": "Forbidden"}, 403


@app.post("/webhook")
async def webhook(request: Request):
    """Meta WhatsApp Cloud API webhook entry point."""
    try:
        data = await request.json()

        # Extract messages from Meta's nested structure
        entry = data.get("entry", [])
        if not entry:
            logger.debug("Webhook received but no entry data")
            return {"status": "ok"}

        changes = entry[0].get("changes", [])
        if not changes:
            logger.debug("Webhook received but no changes")
            return {"status": "ok"}

        value = changes[0].get("value", {})
        messages = value.get("messages", [])

        if not messages:
            logger.debug("Webhook received but no messages (might be status update)")
            return {"status": "ok"}

        msg = messages[0]
        telefono = msg.get("from", "")
        if not telefono:
            logger.warning("Received payload without from number")
            return {"status": "invalid_payload"}

        # Normalize phone to digits only
        telefono = "".join(ch for ch in telefono if ch.isdigit())

        # Extract message content based on type
        tipo = msg.get("type", "text")
        contenido = None
        media_url = None
        message_id = msg.get("id", "")

        if tipo == "text":
            contenido = msg.get("text", {}).get("body", "")
        elif tipo == "audio":
            audio = msg.get("audio", {})
            media_id = audio.get("id")
            if media_id:
                # TODO: Download audio from Meta API using media_id
                # media_url = await _get_meta_media_url(media_id)
                contenido = f"[Audio message {media_id}]"
        elif tipo == "image":
            image = msg.get("image", {})
            media_id = image.get("id")
            contenido = image.get("caption", "")
            if media_id:
                # TODO: Download image from Meta API using media_id
                # media_url = await _get_meta_media_url(media_id)
                pass

        payload = WAHAPayload(
            telefono=telefono,
            tipo=tipo,
            contenido=contenido,
            media_url=media_url,
        )

        logger.info(f"Received message from {payload.telefono} (type: {payload.tipo}, msg_id: {message_id})")

        meta_client = MetaClient()
        route = get_router()
        result = await route.handle_message(payload, meta_client)

        logger.info(f"Processed message result: {result}")
        return {"status": "ok", "result": result}
    except Exception as e:
        import traceback
        logger.error(f"Webhook error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)}


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


async def check_expired_audit_sessions():
    """Background job: Check for expired audit sessions (15 min timeout)."""
    try:
        sheets = get_sheets()
        expired_sesiones = sheets.get_sesiones_activas_expiradas(timeout_min=15)
        meta_client = MetaClient()

        for sesion in expired_sesiones:
            logger.info(f"Audit session timeout for {sesion.telefono_auditor}: {sesion.id_sesion}")

            # Send reminder
            checklist = sheets.get_checklist()
            if sesion.punto_actual < len(checklist):
                punto = checklist[sesion.punto_actual]
                await meta_client.send_text(
                    sesion.telefono_auditor,
                    f"â° Recordatorio: estÃ¡s en el punto {punto.punto_orden}/{sesion.total_puntos} de tu auditorÃ­a.\n"
                    f"MandÃ¡ tu observaciÃ³n o escribe 'saltar' para omitir este punto.",
                )
            # Don't reset the session â€” just send reminder

        if expired_sesiones:
            logger.info(f"Sent reminders for {len(expired_sesiones)} expired audit sessions")
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

"""FastAPI application for AuditBot webhook and background jobs."""

import logging
from datetime import datetime
import json

from fastapi import FastAPI, Request, Depends
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import httpx
import qrcode
from io import BytesIO
import base64
import re

from config import get_settings
from models import WAHAPayload, ConversationState
from router import ConversationRouter
from waha import TwilioClient
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
async def get_qr():
    """Get WhatsApp QR code from Evolution API."""
    evo_url = settings.waha_url.rstrip("/")
    instance = settings.waha_session
    headers = {"apikey": settings.waha_api_key}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{evo_url}/instance/fetchInstances",
                headers=headers,
                timeout=10,
            )
            instances = response.json() if response.status_code == 200 else []

            qr_response = await client.get(
                f"{evo_url}/instance/qrcode/{instance}?image=true",
                headers=headers,
                timeout=15,
            )

            if qr_response.status_code == 200:
                qr_data = qr_response.json()
                base64_img = qr_data.get("base64", "")
                if base64_img and "base64," in base64_img:
                    img_bytes = base64.b64decode(base64_img.split("base64,")[1])
                    return StreamingResponse(iter([img_bytes]), media_type="image/png")
    except Exception as e:
        logger.error(f"Error getting QR from Evolution API: {e}")

    # Fallback HTML
    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>WhatsApp QR - AuditBot</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }}
            .container {{ background: white; border-radius: 15px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); max-width: 600px; width: 100%; padding: 40px; }}
            h1 {{ color: #25D366; margin-bottom: 10px; text-align: center; font-size: 28px; }}
            .subtitle {{ text-align: center; color: #666; margin-bottom: 30px; font-size: 14px; }}
            .status-box {{ background: #e8f5e9; border-left: 4px solid #25D366; padding: 15px; margin: 20px 0; border-radius: 5px; }}
            .status-box p {{ color: #2e7d32; margin: 5px 0; }}
            .methods {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 30px 0; }}
            .method {{ border: 2px solid #ddd; padding: 20px; border-radius: 10px; text-align: center; cursor: pointer; transition: all 0.3s; }}
            .method:hover {{ border-color: #25D366; background: #f0f8f5; }}
            .method-icon {{ font-size: 32px; margin-bottom: 10px; }}
            .method h3 {{ color: #333; margin-bottom: 10px; font-size: 16px; }}
            .method p {{ color: #666; font-size: 13px; margin-bottom: 10px; }}
            .method a {{ display: inline-block; padding: 8px 16px; background: #25D366; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 13px; transition: background 0.3s; }}
            .method a:hover {{ background: #20ba5a; }}
            .divider {{ text-align: center; color: #999; margin: 30px 0; font-size: 14px; }}
            .logs-info {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            .logs-info p {{ color: #666; font-size: 13px; line-height: 1.6; margin: 10px 0; }}
            .logs-info code {{ background: white; padding: 2px 6px; border-radius: 3px; font-family: monospace; }}
            .steps {{ background: #f9f9f9; padding: 20px; border-radius: 10px; margin: 20px 0; }}
            .steps h3 {{ color: #333; margin-bottom: 15px; }}
            .steps ol {{ padding-left: 20px; }}
            .steps li {{ margin: 10px 0; color: #666; line-height: 1.6; }}
            @media (max-width: 600px) {{
                .methods {{ grid-template-columns: 1fr; }}
                .container {{ padding: 20px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📱 Conecta WhatsApp</h1>
            <p class="subtitle">Tu sesión está lista para autenticar</p>

            <div class="status-box">
                <p>✅ <strong>Sesión activa:</strong> default</p>
                <p>📍 <strong>Estado:</strong> Esperando código QR</p>
            </div>

            <div class="methods">
                <div class="method">
                    <div class="method-icon">🌐</div>
                    <h3>Evolution Manager</h3>
                    <p>Dashboard para administrar WhatsApp</p>
                    <a href="{evo_url}/manager" target="_blank">Abrir</a>
                </div>
            </div>

            <div class="logs-info">
                <strong>💡 Accede a Evolution Manager para ver el QR</strong>
                <p>Ingresa al dashboard de Evolution API con tu API key y haz clic en "Get QR Code" para visualizar el código que debes escanear con WhatsApp.</p>
            </div>

            <div class="steps">
                <h3>Pasos para conectar:</h3>
                <ol>
                    <li><strong>Abre Evolution Manager</strong> desde el botón de arriba</li>
                    <li><strong>Haz clic en "Get QR Code"</strong> para generar el código</li>
                    <li><strong>En tu teléfono:</strong> Abre WhatsApp</li>
                    <li><strong>Ve a:</strong> Menú (⋮) → Dispositivos vinculados</li>
                    <li><strong>Toca:</strong> "Vincular un dispositivo"</li>
                    <li><strong>Escanea el código QR</strong> con tu cámara</li>
                    <li><strong>¡Listo!</strong> Tu sesión se conectará automáticamente</li>
                </ol>
            </div>

            <div class="divider">
                ¿Problemas? Recarga esta página o intenta en 5 minutos
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.post("/webhook")
async def webhook(request: Request):
    """Twilio WhatsApp webhook entry point."""
    try:
        # Twilio sends form-data, not JSON
        form_data = await request.form()

        # Extract sender phone (remove whatsapp: prefix and +)
        from_number = form_data.get("From", "").replace("whatsapp:", "").replace("+", "")
        if not from_number:
            logger.warning("Received payload without From number")
            return {"status": "invalid_payload"}

        # Extract message content
        body = form_data.get("Body", "").strip()
        message_sid = form_data.get("MessageSid", "")

        # Initialize payload
        contenido = None
        tipo = "text"
        media_url = None

        # Check for media
        media_url_0 = form_data.get("MediaUrl0")
        if media_url_0:
            # Determine media type from URL
            if "image" in media_url_0.lower() or media_url_0.endswith((".jpg", ".jpeg", ".png")):
                tipo = "image"
            elif "audio" in media_url_0.lower() or media_url_0.endswith((".mp3", ".wav", ".ogg")):
                tipo = "audio"
            media_url = media_url_0
            contenido = body  # Caption or message body

        # If no media, treat as text
        if tipo == "text" and body:
            contenido = body

        payload = WAHAPayload(
            telefono=from_number,
            tipo=tipo,
            contenido=contenido,
            media_url=media_url,
        )

        if not payload.telefono:
            logger.warning("Received payload without phone")
            return {"status": "invalid_payload"}

        logger.info(f"Received message from {payload.telefono} (type: {payload.tipo}, sid: {message_sid})")

        twilio_client = TwilioClient()
        route = get_router()
        result = await route.handle_message(payload, twilio_client)

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
        twilio_client = TwilioClient()

        for pendiente in expired:
            logger.info(f"Timeout expired for {pendiente.telefono_auditor}")

            # Notify auditor
            await twilio_client.send_text(
                pendiente.telefono_auditor,
                "⏰ Tu confirmación expiró. Envíame un nuevo hallazgo cuando estés listo.",
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
        twilio_client = TwilioClient()

        for sesion in expired_sesiones:
            logger.info(f"Audit session timeout for {sesion.telefono_auditor}: {sesion.id_sesion}")

            # Send reminder
            checklist = sheets.get_checklist()
            if sesion.punto_actual < len(checklist):
                punto = checklist[sesion.punto_actual]
                await twilio_client.send_text(
                    sesion.telefono_auditor,
                    f"⏰ Recordatorio: estás en el punto {punto.punto_orden}/{sesion.total_puntos} de tu auditoría.\n"
                    f"Mandá tu observación o escribe 'saltar' para omitir este punto.",
                )
            # Don't reset the session — just send reminder

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

        summary = f"""📊 **Resumen Diario AuditBot**

Fecha: {datetime.now().strftime('%Y-%m-%d')}

[Resumen en construcción]

Para más detalles, consulta la hoja de Reportes."""

        twilio_client = TwilioClient()
        await twilio_client.send_text(settings.coordinador_tel, summary)

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

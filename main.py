"""FastAPI application for AuditBot webhook and background jobs."""

import logging
from datetime import datetime
import json

from fastapi import FastAPI, Request, Depends
from fastapi.responses import FileResponse, HTMLResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import httpx

from config import get_settings
from models import WAHAPayload, ConversationState
from router import ConversationRouter
from waha import WAHAClient
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
    """Get WhatsApp QR code from WAHA."""
    try:
        session_name = settings.waha_session
        waha_url = settings.waha_url.rstrip('/')
        headers = {"X-API-KEY": settings.waha_api_key}

        async with httpx.AsyncClient() as client:
            # Intentar obtener el QR como PNG
            try:
                response = await client.get(
                    f"{waha_url}/api/sessions/{session_name}/qr.png",
                    headers=headers,
                    timeout=10
                )
                if response.status_code == 200:
                    return FileResponse(
                        content=response.content,
                        media_type="image/png",
                        filename="qr.png"
                    )
            except Exception as e:
                logger.warning(f"Failed to get QR as PNG: {e}")

            # Fallback: proporcionar HTML con enlace directo a WAHA
            html = f"""
            <html>
            <head>
                <title>WhatsApp QR Code</title>
                <style>
                    body {{ font-family: Arial; text-align: center; padding: 40px; }}
                    .container {{ max-width: 600px; margin: 0 auto; }}
                    h1 {{ color: #25D366; }}
                    a {{ display: inline-block; margin-top: 20px; padding: 10px 20px;
                       background: #25D366; color: white; text-decoration: none; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>📱 WhatsApp QR Code</h1>
                    <p>Abre WAHA para ver el código QR:</p>
                    <a href="{waha_url}/" target="_blank">Abrir WAHA Dashboard</a>
                    <p style="margin-top: 30px; color: #666;">
                        <strong>Pasos:</strong><br>
                        1. Abre WAHA Dashboard<br>
                        2. Navega a Sessions<br>
                        3. Escanea el código QR con WhatsApp<br>
                        4. Listo! 🎉
                    </p>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=html)
    except Exception as e:
        logger.error(f"Error getting QR: {e}")
        return {"error": str(e)}


@app.post("/webhook")
async def webhook(request: Request):
    """WAHA webhook entry point."""
    try:
        payload_data = await request.json()

        # Sanitize payload
        payload = WAHAPayload(
            telefono=payload_data.get("phone", "").replace("+", "").replace("@c.us", ""),
            tipo=payload_data.get("type", "text"),  # text, audio, image
            contenido=payload_data.get("text") or payload_data.get("caption"),
            media_url=(payload_data.get("media") or {}).get("url"),
        )

        if not payload.telefono:
            logger.warning("Received payload without phone")
            return {"status": "invalid_payload"}

        logger.info(f"Received message from {payload.telefono} (type: {payload.tipo})")

        # Get WAHA client
        waha_client = WAHAClient()

        # Route message
        route = get_router()
        result = await route.handle_message(payload, waha_client)

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
        waha_client = WAHAClient()

        for pendiente in expired:
            logger.info(f"Timeout expired for {pendiente.telefono_auditor}")

            # Notify auditor
            await waha_client.send_text(
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

        waha_client = WAHAClient()
        await waha_client.send_text(settings.coordinador_tel, summary)

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

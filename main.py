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
    """Get WhatsApp QR code from WAHA dashboard."""
    try:
        waha_url = settings.waha_url.rstrip('/')

        # Try to capture QR from WAHA dashboard using Playwright
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                # Navigate to WAHA and wait for QR
                await page.goto(f"{waha_url}/", timeout=10000, wait_until="networkidle")
                await page.wait_for_timeout(2000)

                # Take screenshot
                screenshot = await page.screenshot(full_page=True)
                await browser.close()

                return StreamingResponse(
                    iter([screenshot]),
                    media_type="image/png",
                    headers={"Content-Disposition": "inline; filename=qr.png"}
                )
        except ImportError:
            logger.warning("Playwright not available, trying alternative method")
        except Exception as e:
            logger.warning(f"Playwright failed: {e}")

        # Fallback: Try to get QR from API
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{waha_url}/api/sessions",
                    timeout=5
                )
                if response.status_code == 200:
                    sessions = response.json()
                    return {
                        "status": "pending",
                        "message": "QR generado por WAHA. Abre el dashboard:",
                        "dashboard_url": f"{waha_url}/",
                        "sessions": sessions
                    }
            except Exception as e:
                logger.debug(f"API fallback failed: {e}")

        # Last resort: HTML page directing to WAHA
        html = f"""
        <html>
        <head>
            <title>WhatsApp QR - AuditBot</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 40px; background: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #25D366; margin-top: 0; }}
                p {{ color: #666; line-height: 1.6; }}
                .steps {{ text-align: left; background: #f9f9f9; padding: 20px; border-radius: 5px; margin: 20px 0; }}
                .steps ol {{ margin: 10px 0; padding-left: 20px; }}
                .steps li {{ margin: 10px 0; }}
                a {{ display: inline-block; margin-top: 20px; padding: 12px 30px; background: #25D366; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; }}
                a:hover {{ background: #20ba5a; }}
                .warning {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; text-align: left; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📱 Conecta WhatsApp</h1>
                <p>Tu sesión WhatsApp está lista para conectar.</p>

                <a href="{waha_url}/" target="_blank">📲 Abrir Dashboard WAHA</a>

                <div class="steps">
                    <strong>Pasos para conectar:</strong>
                    <ol>
                        <li>Haz clic en "Abrir Dashboard WAHA"</li>
                        <li>Busca el código QR en la pantalla</li>
                        <li>Abre WhatsApp en tu teléfono</li>
                        <li>Ve a Menú → Dispositivos vinculados</li>
                        <li>Toca "Vincular un dispositivo"</li>
                        <li>Escanea el código QR</li>
                        <li>¡Listo! Tu sesión estará conectada</li>
                    </ol>
                </div>

                <div class="warning">
                    <strong>⚠️ Importante:</strong> Si el QR no aparece en el dashboard después de 30 segundos, recarga la página.
                </div>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"Error in /qr endpoint: {e}")
        return HTMLResponse(content=f"<h1>Error</h1><p>{str(e)}</p>")


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

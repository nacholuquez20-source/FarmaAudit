"""Generate and send the branch-summary report to the owner (coordinador_tel)."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from audit_pdf_generator import generate_resumen_sucursales_pdf
from config import get_settings
from meta_client import MetaClient
from supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

_RESUMEN_URL_EXPIRY_SECONDS = 24 * 60 * 60  # 24 hours


class ResumenSucursalesManager:
    """Single implementation shared by the on-demand admin endpoint and the
    weekly cron job — neither has its own copy of this logic."""

    @staticmethod
    async def generar_y_enviar(meta_client: Optional[MetaClient] = None) -> Dict[str, Any]:
        db = SupabaseManager()
        resumen = db.get_resumen_sucursales()
        if not resumen:
            logger.warning("Resumen de sucursales: sin datos, no se genero nada")
            return {"status": "sin_datos"}

        pdf_bytes = generate_resumen_sucursales_pdf(resumen)

        try:
            upload = db.upload_resumen_sucursales_pdf(pdf_bytes)
        except Exception as e:
            logger.error(f"Failed to upload resumen sucursales PDF: {e}")
            return {"status": "fallo_upload"}

        signed_url = db.create_signed_ficha_url(upload["path"], _RESUMEN_URL_EXPIRY_SECONDS)

        settings = get_settings()
        if not settings.coordinador_tel:
            logger.warning("Resumen de sucursales: COORDINADOR_TEL no configurado, no se envia")
            return {"status": "sin_coordinador_tel", "url": signed_url}

        mc = meta_client or MetaClient()
        fecha = datetime.now(timezone.utc).strftime("%Y%m%d")
        filename = f"FarmaAudit_Resumen_Sucursales_{fecha}.pdf"
        caption = f"Resumen de sucursales — {len(resumen)} sucursales — FarmaAudit"

        ok = await mc.send_document(settings.coordinador_tel, signed_url, filename, caption=caption)
        if ok:
            logger.info(f"Resumen de sucursales enviado como documento a {settings.coordinador_tel}")
            return {"status": "enviado", "url": signed_url}

        ok_text = await mc.send_text(settings.coordinador_tel, f"{caption}\n{signed_url}")
        if ok_text:
            logger.warning(f"Resumen de sucursales enviado como link (fallo el documento) a {settings.coordinador_tel}")
            return {"status": "enviado_como_link", "url": signed_url}

        logger.error(f"Resumen de sucursales: fallo el envio a {settings.coordinador_tel}")
        return {"status": "fallo_envio", "url": signed_url}

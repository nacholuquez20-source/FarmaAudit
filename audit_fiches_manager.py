"""Manage audit fiches: Generate PDF, save to Google Drive, store metadata."""

import logging
from typing import Dict, Optional
from datetime import datetime, timezone

import httpx

from audit_session import AuditSession, BLOQUE_ORDER
from audit_pdf_generator import generate_audit_pdf
from supabase_manager import SupabaseManager
from drive import DriveManager

logger = logging.getLogger(__name__)


async def _download_photo_bytes(foto_url: str) -> Optional[bytes]:
    """Download photo from URL. Returns bytes or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(foto_url, follow_redirects=True)
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        logger.warning(f"Could not download photo from {foto_url}: {e}")
        return None


class AuditFichesManager:
    """Manage PDF generation and storage for audit fiches."""

    @staticmethod
    async def generate_and_save_ficha(
        session: AuditSession,
        reporte_id: str,
        sucursal_nombre: str = "",
        responsable_desvios: Optional[str] = None,
        meta_client=None,  # MetaClient — optional, used to re-download fresh photos
    ) -> Optional[str]:
        """Generate PDF ficha with photos, save to Google Drive, store metadata.

        Returns:
            Public Google Drive view URL or None if error.
        """
        try:
            db = SupabaseManager()

            sucursal = db.get_sucursal(session.sucursal_id)
            resolved_nombre = sucursal.nombre if sucursal else (sucursal_nombre or session.sucursal_id)

            # Download photo bytes for embedding in PDF
            photo_bytes: Dict[str, bytes] = {}
            if session.fotos:
                for foto in session.fotos:
                    raw: Optional[bytes] = None

                    # Try re-downloading via Meta (always fresh)
                    if meta_client and foto.media_id:
                        try:
                            raw = await meta_client.download_media(foto.media_id)
                        except Exception as e:
                            logger.warning(f"Meta re-download failed for {foto.id}: {e}")

                    # Fallback: cached media_url (may be expired)
                    if raw is None and foto.media_url:
                        raw = await _download_photo_bytes(foto.media_url)

                    if raw:
                        photo_bytes[foto.id] = raw
                        logger.info(f"Downloaded photo {foto.id} ({len(raw)} bytes) for PDF")
                    else:
                        logger.warning(f"Could not obtain bytes for photo {foto.id} — skipping in PDF")

            # Generate PDF
            pdf_bytes = generate_audit_pdf(
                session=session,
                sucursal_nombre=resolved_nombre,
                auditor_nombre=session.auditor_nombre,
                responsable_desvios=responsable_desvios,
                photo_bytes=photo_bytes or None,
            )

            # Upload to Google Drive
            drive = DriveManager()
            filename = f"Auditoria_{session.id_sesion}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"

            file_id = await drive.upload_file_async(
                file_bytes=pdf_bytes,
                filename=filename,
                mime_type="application/pdf",
                folder_name="Auditorias_Perfumeria",
            )

            if not file_id:
                logger.warning(f"Failed to upload PDF to Drive for session {session.id_sesion}")
                return None

            drive_url = f"https://drive.google.com/file/d/{file_id}/view"
            avg_score = sum(session.bloques.values()) / len(session.bloques) if session.bloques else 0

            ficha_data = {
                "reporte_id": reporte_id,
                "sucursal_id": session.sucursal_id,
                "auditor_nombre": session.auditor_nombre,
                "responsable_desvios": responsable_desvios,
                "fecha_auditoria": session.started_at or datetime.now(timezone.utc).isoformat(),
                "url_pdf": drive_url,
                "google_drive_id": file_id,
                "total_desvios": len(session.desvios),
                "total_fotos": len(session.fotos),
                "puntuacion_promedio": round(avg_score, 2),
                "score_limpieza": session.bloques.get("LIMPIEZA"),
                "score_stock": session.bloques.get("STOCK"),
                "score_ofertas": session.bloques.get("OFERTAS"),
                "score_burbujas": session.bloques.get("BURBUJAS"),
            }

            response = db.client.table("audit_fiches").insert(ficha_data).execute()

            if response.data:
                logger.info(f"Saved ficha for session {session.id_sesion}, Drive: {file_id}")
                return drive_url
            else:
                logger.error(f"Failed to save ficha metadata: {response.error}")
                # Still return the URL since the file was uploaded
                return drive_url

        except Exception as e:
            logger.error(f"Error generating/saving ficha: {e}", exc_info=True)
            return None

    @staticmethod
    async def get_fiches(
        sucursal_id: Optional[str] = None,
        fecha_desde: Optional[str] = None,
        fecha_hasta: Optional[str] = None,
        auditor_nombre: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list:
        """Get audit fiches with optional filters."""
        try:
            db = SupabaseManager()
            query = db.client.table("audit_fiches").select("*")

            if sucursal_id:
                query = query.eq("sucursal_id", sucursal_id)
            if fecha_desde:
                query = query.gte("fecha_auditoria", fecha_desde)
            if fecha_hasta:
                query = query.lte("fecha_auditoria", fecha_hasta)
            if auditor_nombre:
                query = query.ilike("auditor_nombre", f"%{auditor_nombre}%")

            query = query.order("fecha_auditoria", desc=True).limit(limit).offset(offset)
            response = query.execute()
            return response.data if response.data else []

        except Exception as e:
            logger.error(f"Error fetching fiches: {e}")
            return []

    @staticmethod
    async def get_sucursales_with_fiches() -> list:
        """Get list of all sucursales that have audit fiches."""
        try:
            db = SupabaseManager()
            response = db.client.table("audit_fiches").select("sucursal_id").execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error fetching sucursales: {e}")
            return []

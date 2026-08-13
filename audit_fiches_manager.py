"""Manage audit fiches: Generate PDF, save to Google Drive, store metadata."""

import logging
from typing import Dict, Optional
from datetime import datetime, timezone

import httpx

from audit_session import AuditSession, BLOQUE_ORDER
from audit_pdf_generator import generate_audit_pdf
from supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

# Signed URL validity for freshly generated PDF reports (Storage is private).
_FICHA_URL_EXPIRY_SECONDS = 24 * 60 * 60  # 24 hours


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
        """Generate PDF ficha with photos, save to Supabase Storage, store metadata.

        Returns:
            The Storage object path (not a URL — the bucket is private, so
            callers must mint a fresh signed URL via
            SupabaseManager.create_signed_ficha_url() whenever they need to
            actually serve/send the file) or None on error.
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

            # Upload to Supabase Storage (private bucket)
            try:
                upload_result = db.upload_audit_ficha_pdf(session.id_sesion, pdf_bytes)
            except Exception as e:
                logger.warning(f"Failed to upload PDF to Storage for session {session.id_sesion}: {e}")
                return None

            storage_path = upload_result["path"]
            signed_url = db.create_signed_ficha_url(storage_path, _FICHA_URL_EXPIRY_SECONDS)
            avg_score = sum(session.bloques.values()) / len(session.bloques) if session.bloques else 0

            ficha_data = {
                # NOTE: the audit_fiches column is named id_reporte (FK to reportes.id),
                # not reporte_id — using the wrong name here silently broke every
                # insert until this fix (the table was empty despite audits running).
                "id_reporte": reporte_id,
                "sucursal_id": session.sucursal_id,
                "auditor_nombre": session.auditor_nombre,
                # Telefono del auditor que corrio la sesion — es lo unico que
                # permite, mas adelante, avisarle por WhatsApp cuando el
                # encargado responde (el nombre solo no alcanza para resolver
                # un destinatario). session.telefono siempre esta poblado.
                "auditor_telefono": session.telefono,
                "responsable_desvios": responsable_desvios,
                "fecha_auditoria": session.started_at or datetime.now(timezone.utc).isoformat(),
                "url_pdf": signed_url,
                # NOTE: this column predates the Supabase Storage migration and is
                # named for its old Google Drive purpose — it now holds the
                # Storage object path used to mint fresh signed URLs on demand.
                "google_drive_id": storage_path,
                "desvios_count": len(session.desvios),
                "fotos_count": len(session.fotos),
                "puntuacion_promedio": round(avg_score, 2),
                # Puntaje por bloque (LIMPIEZA, STOCK, ...) de ESTA auditoria —
                # es lo unico que permite calcular la comparacion "subio/bajo
                # vs. la vez pasada" en la proxima auditoria (get_previous_audit
                # en audit_database.py). Antes no se guardaba en ningun lado:
                # la comparacion siempre devolvia None, en silencio.
                "bloques_json": session.bloques,
            }

            response = db.client.table("audit_fiches").insert(ficha_data).execute()

            if response.data:
                ficha_id = response.data[0].get("id")
                logger.info(f"Saved ficha for session {session.id_sesion}, Storage: {storage_path}")

                # Link the gestiones created for this session to the ficha
                # that contains them (ARQUITECTURA_PANEL_DESVIOS.md §6).
                gestion_ids = session.pending_ficha_gestion_ids
                if ficha_id and gestion_ids:
                    try:
                        db.client.table("gestion").update({"ficha_id": ficha_id}).in_(
                            "id_gestion", gestion_ids
                        ).execute()
                    except Exception as link_exc:
                        logger.warning(f"Failed to link gestiones to ficha {ficha_id}: {link_exc}")
            else:
                logger.error(f"Failed to save ficha metadata: {response.error}")
            # Return the storage path (not the signed URL) so callers always
            # mint a fresh one instead of relying on this one until it expires.
            return storage_path

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

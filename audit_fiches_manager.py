"""Manage audit fiches: Generate PDF, save to Google Drive, store metadata."""

import logging
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4

from audit_session import AuditSession, BLOQUE_ORDER
from audit_pdf_generator import generate_audit_pdf
from supabase_manager import SupabaseManager
from drive import DriveManager

logger = logging.getLogger(__name__)


class AuditFichesManager:
    """Manage PDF generation and storage for audit fiches."""

    @staticmethod
    async def generate_and_save_ficha(
        session: AuditSession,
        reporte_id: str,
        sucursal_nombre: str,
        responsable_desvios: Optional[str] = None,
    ) -> Optional[str]:
        """Generate PDF ficha, save to Google Drive, store metadata in DB.

        Args:
            session: AuditSession with audit data
            reporte_id: UUID of reporte record in DB
            sucursal_nombre: Name of sucursal
            responsable_desvios: Name of person responsible for deviations

        Returns:
            Google Drive file ID or None if error
        """

        try:
            # Generate PDF
            pdf_bytes = generate_audit_pdf(
                session=session,
                sucursal_nombre=sucursal_nombre,
                auditor_nombre=session.auditor_nombre,
                responsable_desvios=responsable_desvios,
            )

            # Upload to Google Drive
            drive = DriveManager()
            filename = f"Auditoria_Perfumeria_{session.id_sesion}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"

            file_id = await drive.upload_file_async(
                file_bytes=pdf_bytes,
                filename=filename,
                mime_type="application/pdf",
                folder_name="Auditorías_Perfumería",
            )

            if not file_id:
                logger.warning(f"Failed to upload PDF to Google Drive for session {session.id_sesion}")
                return None

            # Generate Drive share link
            drive_url = f"https://drive.google.com/file/d/{file_id}/view"

            # Calculate metrics for metadata
            avg_score = sum(session.bloques.values()) / len(session.bloques) if session.bloques else 0

            # Save metadata to Supabase
            db = SupabaseManager()
            ficha_data = {
                "id_reporte": reporte_id,
                "sucursal_id": session.sucursal_id,
                "auditor_nombre": session.auditor_nombre,
                "responsable_desvios": responsable_desvios,
                "fecha_auditoria": session.started_at or datetime.now(timezone.utc).isoformat(),
                "url_pdf": drive_url,
                "google_drive_id": file_id,
                "desvios_count": len(session.desvios),
                "fotos_count": len(session.fotos),
                "puntuacion_promedio": round(avg_score, 2),
            }

            response = db.client.table("audit_fiches").insert(ficha_data).execute()

            if response.data:
                logger.info(f"Saved ficha metadata for session {session.id_sesion}, Drive ID: {file_id}")
                return file_id
            else:
                logger.error(f"Failed to save ficha metadata: {response.error}")
                return None

        except Exception as e:
            logger.error(f"Error generating/saving ficha: {e}")
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
        """Get audit fiches with optional filters.

        Args:
            sucursal_id: Filter by sucursal
            fecha_desde: Filter from date (ISO format)
            fecha_hasta: Filter to date (ISO format)
            auditor_nombre: Filter by auditor name
            limit: Pagination limit
            offset: Pagination offset

        Returns:
            List of ficha records
        """

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

            # Order by date descending
            query = query.order("fecha_auditoria", desc=True)

            # Pagination
            query = query.limit(limit).offset(offset)

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

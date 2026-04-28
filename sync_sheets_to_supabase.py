"""
Hydrate Supabase from Google Sheets.

Supabase is the operational source of truth for the frontend. Google Sheets is
kept as an ingestion/legacy source for data produced by the WhatsApp bot.
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
import os

from supabase import create_client, Client
from sheets_legacy import SheetsManager as LegacySheetsManager
from models import Auditor, Sucursal, Reporte, Gestion
from config import get_settings

logger = logging.getLogger(__name__)

# Once supervisors act in the frontend, Supabase owns the operational lifecycle.
# The Sheets sync can create/update base records, but must not roll back progress.
FRONTEND_MANAGED_STATES = {"En_proceso", "Resuelta", "Cerrada"}
SHEET_PASSIVE_STATES = {"", "Abierta", "Vencida"}


class SheetsToSupabaseSync:
    """Hydrates Supabase from Google Sheets without overriding frontend workflow state."""

    def __init__(self):
        """Initialize Supabase client."""
        settings = get_settings()
        supabase_url = os.getenv("SUPABASE_URL") or settings.supabase_url
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or settings.supabase_service_key

        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables are required")

        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.sheets = LegacySheetsManager()
        logger.info("SheetsToSupabaseSync initialized")

    def sync_sucursales(self) -> None:
        """Sync Maestro_Sucursales from Sheets to Supabase."""
        try:
            logger.info("Starting sucursales sync...")
            sucursales = self.sheets.get_all_sucursales()

            for sucursal in sucursales:
                data = {
                    "id": sucursal.id,
                    "nombre": sucursal.nombre,
                    "direccion": sucursal.direccion,
                    "responsable": sucursal.responsable,
                    "tel_responsable": sucursal.tel_responsable,
                    "zona": sucursal.zona,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                # UPSERT: insert or update
                self.supabase.table("sucursales").upsert(data).execute()

            logger.info(f"Synced {len(sucursales)} sucursales")
        except Exception as e:
            logger.error(f"Failed to sync sucursales: {e}")
            raise

    def sync_auditores(self) -> None:
        """Sync Maestro_Auditores from Sheets to Supabase."""
        try:
            logger.info("Starting auditores sync...")
            auditores = self.sheets.get_all_auditores()

            for auditor in auditores:
                data = {
                    "telefono": auditor.telefono,
                    "nombre": auditor.nombre,
                    "cuadrilla": auditor.cuadrilla,
                    "activo": auditor.activo,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                self.supabase.table("auditores").upsert(data).execute()

            logger.info(f"Synced {len(auditores)} auditores")
        except Exception as e:
            logger.error(f"Failed to sync auditores: {e}")
            raise

    def sync_reportes(self) -> None:
        """Sync Reportes from Sheets to Supabase."""
        try:
            logger.info("Starting reportes sync...")
            sheet = self.sheets._get_sheet("Reportes")
            rows = sheet.get_all_records()

            for row in rows:
                data = {
                    "id": row.get("ID", ""),
                    "fecha": row.get("Fecha", ""),
                    "hora": row.get("Hora", ""),
                    "cuadrilla": row.get("Cuadrilla", ""),
                    "auditor": row.get("Auditor", ""),
                    "id_sucursal": row.get("ID_Sucursal", ""),
                    "sucursal": row.get("Sucursal", ""),
                    "area": row.get("Area", ""),
                    "subitem": row.get("Subitem", ""),
                    "descripcion": row.get("Descripcion", ""),
                    "severidad": row.get("Severidad", "Baja"),
                    "foto_url": row.get("Foto_URL") or None,
                    "creado_por_audio": str(row.get("Creado_Por_Audio", "false")).lower() == "true",
                    "timestamp": row.get("Timestamp", ""),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                if data["id"]:  # Only sync if has ID
                    self.supabase.table("reportes").upsert(data).execute()

            logger.info(f"Synced {len(rows)} reportes")
        except Exception as e:
            logger.error(f"Failed to sync reportes: {e}")
            raise

    def _preserve_operational_gestion_state(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Preserve Supabase-owned workflow fields when Sheets has stale/passive state."""
        existing = (
            self.supabase.table("gestion")
            .select("estado,fecha_cierre,cerrado_por")
            .eq("id_gestion", data["id_gestion"])
            .execute()
        )
        existing_rows = existing.data or []
        if not existing_rows:
            return data

        existing_row = existing_rows[0]
        existing_estado = existing_row.get("estado")
        incoming_estado = data.get("estado") or ""

        if existing_estado in FRONTEND_MANAGED_STATES and incoming_estado in SHEET_PASSIVE_STATES:
            logger.info(
                "Preserving frontend-managed gestion state for %s: %s",
                data["id_gestion"],
                existing_estado,
            )
            data["estado"] = existing_estado
            data["fecha_cierre"] = existing_row.get("fecha_cierre")
            data["cerrado_por"] = existing_row.get("cerrado_por")

        return data

    def sync_gestion(self) -> None:
        """Hydrate Gestion from Sheets while preserving Supabase-owned workflow fields."""
        try:
            logger.info("Starting gestion sync...")
            sheet = self.sheets._get_sheet("Gestion")
            rows = sheet.get_all_records()

            for row in rows:
                data = {
                    "id_gestion": row.get("ID_Gestion", ""),
                    "id_reporte": row.get("ID_Reporte", ""),
                    "id_sucursal": row.get("ID_Sucursal", ""),
                    "sucursal": row.get("Sucursal", ""),
                    "desvio": row.get("Desvio", ""),
                    "severidad": row.get("Severidad", "Baja"),
                    "responsable": row.get("Responsable", ""),
                    "tel_responsable": row.get("Tel_Responsable", ""),
                    "plazo_fecha": row.get("Plazo_Fecha", ""),
                    "plan_accion": row.get("Plan_Accion", ""),
                    "estado": row.get("Estado", "Abierta"),
                    "fecha_cierre": row.get("Fecha_Cierre") or None,
                    "cerrado_por": row.get("Cerrado_Por") or None,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                if data["id_gestion"]:  # Only sync if has ID
                    data = self._preserve_operational_gestion_state(data)
                    self.supabase.table("gestion").upsert(data).execute()

            logger.info(f"Synced {len(rows)} gestion records")
        except Exception as e:
            logger.error(f"Failed to sync gestion: {e}")
            raise

    def sync_control_stock(self) -> None:
        """Sync Control_Stock from Sheets to Supabase."""
        try:
            logger.info("Starting control_stock sync...")
            sheet = self.sheets._get_sheet("Control_Stock")
            rows = sheet.get_all_records()

            for row in rows:
                # Generate a simple ID if not present
                item_id = row.get("ID", f"{row.get('Sucursal_ID', '')}-{row.get('Nombre_Item', '')}-{row.get('Fecha', '')}")

                data = {
                    "id": item_id,
                    "auditoria_id": row.get("Auditoria_ID", ""),
                    "sucursal_id": row.get("Sucursal_ID", ""),
                    "fecha": row.get("Fecha", ""),
                    "auditor": row.get("Auditor", ""),
                    "nombre_item": row.get("Nombre_Item", ""),
                    "stock_fisico": int(row.get("Stock_Fisico", 0)) if row.get("Stock_Fisico") else 0,
                    "stock_sistema": int(row.get("Stock_Sistema", 0)) if row.get("Stock_Sistema") else 0,
                    "diferencia": int(row.get("Diferencia", 0)) if row.get("Diferencia") else 0,
                    "alerta": row.get("Alerta", "NO"),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                self.supabase.table("control_stock").upsert(data).execute()

            logger.info(f"Synced {len(rows)} control_stock items")
        except Exception as e:
            logger.error(f"Failed to sync control_stock: {e}")
            # Don't raise - this sheet might not exist in all setups

    def sync_all(self) -> None:
        """Run full sync for all tables."""
        try:
            logger.info("===== Starting full Sheets â†’ Supabase sync =====")
            self.sync_sucursales()
            self.sync_auditores()
            self.sync_reportes()
            self.sync_gestion()
            self.sync_control_stock()
            logger.info("===== Full sync completed successfully =====")
        except Exception as e:
            logger.error(f"Full sync failed: {e}")
            raise


async def sync_sheets_to_supabase() -> None:
    """Background task entry point for FastAPI."""
    try:
        sync = SheetsToSupabaseSync()
        sync.sync_all()
    except Exception as e:
        logger.error(f"Sync task failed: {e}")


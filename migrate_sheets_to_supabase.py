"""Migrate data from legacy Google Sheets into Supabase.

Usage:
    python migrate_sheets_to_supabase.py --table maestro_auditores --confirm
    python migrate_sheets_to_supabase.py --table all --confirm
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
import uuid
from typing import Any, Dict, Iterable, List, Optional

from config import get_settings
from models import (
    Auditor,
    ChecklistPerfumeriaPunto,
    ChecklistPunto,
    Conversacion,
    DesvioLibre,
    Gestion,
    GestionState,
    Pendiente,
    Reporte,
    ResultadoItem,
    ResultadoPerfumeria,
    SesionAuditoria,
    Severidad,
    StockItem,
    Sucursal,
    ConversationState,
)
from sheets_legacy import SheetsManager as LegacySheetsManager
from supabase_client import SupabaseManager

logger = logging.getLogger(__name__)


TABLE_ALIASES = {
    "maestro_auditores": "auditores",
    "maestro_sucursales": "sucursales",
    "catalogo_areas": "catalogo_areas",
    "checklist_plantillas": "checklist_plantillas",
    "checklist_perfumeria": "checklist_perfumeria",
    "conversaciones": "conversaciones",
    "pendientes": "pendientes",
    "sesiones_auditoria": "sesiones_auditoria",
    "reportes": "reportes",
    "gestion": "gestion",
    "resultados_perfumeria": "resultados_perfumeria",
    "control_stock": "control_stock",
    "all": "all",
}

EXECUTION_ORDER = [
    "auditores",
    "sucursales",
    "catalogo_areas",
    "checklist_plantillas",
    "checklist_perfumeria",
    "conversaciones",
    "pendientes",
    "sesiones_auditoria",
    "reportes",
    "gestion",
    "resultados_perfumeria",
    "control_stock",
]


class MigrationRunner:
    def __init__(self) -> None:
        self.legacy = LegacySheetsManager()
        self.db = SupabaseManager()
        self.summary = defaultdict(int)
        self.known_auditores: set[str] = set()
        self.known_sucursales: set[str] = set()
        self.known_reportes: set[str] = set()
        self.known_sesiones: set[str] = set()

    def _records(self, sheet_name: str) -> List[Dict[str, Any]]:
        try:
            sheet = self.legacy._get_sheet(sheet_name)
            return sheet.get_all_records()
        except Exception as exc:
            logger.warning("Sheet %s unavailable: %s", sheet_name, exc)
            return []

    def _require_confirmed(self, confirmed: bool) -> None:
        if not confirmed:
            raise SystemExit("Add --confirm to run a migration.")

    def migrate(self, table: str, confirmed: bool, dry_run: bool = False) -> None:
        self._require_confirmed(confirmed)
        table = TABLE_ALIASES.get(table, table)

        if table == "all":
            for name in EXECUTION_ORDER:
                self._run(name, dry_run=dry_run)
            self._print_summary()
            return

        if table not in EXECUTION_ORDER:
            raise SystemExit(f"Unknown table '{table}'.")

        self._run(table, dry_run=dry_run)
        self._print_summary()

    def _run(self, table: str, dry_run: bool = False) -> None:
        logger.info("Migrating %s...", table)
        method = getattr(self, f"_migrate_{table}")
        method(dry_run=dry_run)

    def _print_summary(self) -> None:
        logger.info("Migration summary:")
        for key, value in sorted(self.summary.items()):
            logger.info("  %s: %s", key, value)

    def _upsert_many(self, table_name: str, rows: Iterable[Dict[str, Any]], conflict: str, dry_run: bool = False) -> int:
        count = 0
        conflict_key = conflict.split(",")[0]
        for row in rows:
            key_value = row.get(conflict_key)
            if key_value in (None, ""):
                logger.warning("Skipping %s row without %s", table_name, conflict_key)
                continue
            if dry_run:
                logger.info("[dry-run] %s -> %s", table_name, key_value)
            else:
                self.db._upsert(table_name, row, on_conflict=conflict)
            count += 1
        self.summary[table_name] += count
        return count

    def _migrate_auditores(self, dry_run: bool = False) -> None:
        rows = []
        for auditor in self.legacy.get_all_auditores():
            rows.append({
                "telefono": auditor.telefono,
                "nombre": auditor.nombre,
                "cuadrilla": auditor.cuadrilla,
                "activo": auditor.activo,
            })
            self.known_auditores.add(auditor.telefono)
        self._upsert_many("auditores", rows, "telefono", dry_run)

    def _migrate_sucursales(self, dry_run: bool = False) -> None:
        rows = []
        for sucursal in self.legacy.get_all_sucursales():
            rows.append({
                "id": sucursal.id,
                "nombre": sucursal.nombre,
                "direccion": sucursal.direccion,
                "responsable": sucursal.responsable,
                "tel_responsable": sucursal.tel_responsable,
                "zona": sucursal.zona,
            })
            self.known_sucursales.add(sucursal.id)
        self._upsert_many("sucursales", rows, "id", dry_run)

    def _migrate_catalogo_areas(self, dry_run: bool = False) -> None:
        rows = self._records("Catalogo_Areas")
        payload = []
        for row in rows:
            payload.append({
                "area": row.get("Area", row.get("area", "")),
                "subitems": self._load_json(row.get("SubItems", row.get("subitems", "[]")), []),
            })
        self._upsert_many("catalogo_areas", payload, "area", dry_run)

    def _migrate_checklist_plantillas(self, dry_run: bool = False) -> None:
        rows = self._records("Checklist_Plantillas")
        payload = []
        for row in rows:
            payload.append({
                "item_id": row.get("item_id", ""),
                "bloque": row.get("bloque", ""),
                "bloque_nombre": row.get("bloque_nombre", ""),
                "descripcion": row.get("descripcion", ""),
                "peso": int(row.get("peso") or 5),
                "punto_orden": int(row.get("punto_orden") or 0) if row.get("punto_orden") not in (None, "") else None,
                "area": row.get("area", ""),
                "responsable_default": row.get("responsable_default", ""),
                "severidad_default": row.get("severidad_default", "Media"),
            })
        self._upsert_many("checklist_plantillas", payload, "item_id", dry_run)

    def _migrate_checklist_perfumeria(self, dry_run: bool = False) -> None:
        rows = self._records("Checklist_Perfumeria")
        payload = []
        for row in rows:
            payload.append({
                "bloque_id": row.get("bloque_id", ""),
                "bloque_nombre": row.get("bloque_nombre", ""),
                "punto_orden": int(row.get("punto_orden") or 0),
                "tipo_respuesta": row.get("tipo_respuesta", "si_no"),
                "pregunta": row.get("pregunta", ""),
                "peso": int(row.get("peso") or 5),
                "critico": self._parse_bool(row.get("critico")),
            })
        self._upsert_many("checklist_perfumeria", payload, "bloque_id,punto_orden", dry_run)

    def _migrate_conversaciones(self, dry_run: bool = False) -> None:
        rows = self._records("Conversaciones")
        payload = []
        for row in rows:
            telefono = self._first(row, "telefono", "Telefono", "Telefono_Auditor")
            if not telefono:
                logger.warning("Skipping conversaciones row without telefono")
                continue
            payload.append({
                "telefono": self._normalize_phone(telefono),
                "estado_actual": self._first(row, "estado_actual", "Estado_actual", "Estado", default="idle"),
                "id_pendiente": self._first(row, "id_pendiente", "ID_pendiente", "Hallazgo_Temp"),
                "ultimo_mensaje": self._first(row, "ultimo_mensaje", "Ultimo_mensaje", default=""),
                "timestamp": self._parse_datetime(self._first(row, "timestamp", "Timestamp", "timestamp_ultimo")) or self._now_iso(),
            })
        self._upsert_many("conversaciones", payload, "telefono", dry_run)

    def _migrate_pendientes(self, dry_run: bool = False) -> None:
        rows = self._records("Pendientes")
        payload = []
        for row in rows:
            telefono = self._normalize_phone(self._first(row, "telefono_auditor", "Telefono_Auditor"))
            raw_id = self._first(row, "id_temp", "ID_temp")
            id_temp = raw_id or self._stable_id("pen", [
                telefono,
                self._first(row, "estado", "Estado"),
                self._first(row, "expira_en", "Expira_en"),
            ])
            if telefono and self.known_auditores and telefono not in self.known_auditores:
                logger.warning("Skipping pendiente %s because auditor %s does not exist yet", id_temp, telefono)
                continue
            payload.append({
                "id_temp": id_temp,
                "telefono_auditor": telefono,
                "estado": self._first(row, "estado", "Estado"),
                "datos_json": self._load_json(self._first(row, "datos_json", "Datos_JSON"), {}),
                "timestamp_creacion": self._datetime_or_none(self._first(row, "timestamp_creacion", "Timestamp_creacion")) or self._now_iso(),
                "expira_en": self._datetime_or_none(self._first(row, "expira_en", "Expira_en")) or self._now_iso(),
            })
        self._upsert_many("pendientes", payload, "id_temp", dry_run)

    def _migrate_sesiones_auditoria(self, dry_run: bool = False) -> None:
        rows = self._records("Sesiones_Auditoria")
        payload = []
        for row in rows:
            telefono = self._normalize_phone(self._first(row, "telefono_auditor", "Telefono_Auditor"))
            sucursal_id = self._first(row, "sucursal_id", "Sucursal_ID")
            if telefono and self.known_auditores and telefono not in self.known_auditores:
                logger.warning("Skipping session %s due to unknown auditor %s", self._first(row, "id_sesion"), telefono)
                continue
            if sucursal_id and self.known_sucursales and sucursal_id not in self.known_sucursales:
                logger.warning("Skipping session %s due to unknown sucursal %s", self._first(row, "id_sesion"), sucursal_id)
                continue
            payload.append({
                "id_sesion": self._first(row, "id_sesion"),
                "telefono_auditor": telefono,
                "sucursal_id": sucursal_id or None,
                "estado": self._first(row, "estado", "Estado"),
                "timestamp_inicio": self._datetime_or_none(self._first(row, "timestamp_inicio", "Timestamp_inicio")) or self._now_iso(),
                "timestamp_ultimo_punto": self._datetime_or_none(self._first(row, "timestamp_ultimo_punto", "Timestamp_ultimo_punto")) or self._now_iso(),
                "punto_actual": int(self._first(row, "punto_actual", default="0") or 0),
                "total_puntos": int(self._first(row, "total_puntos", default="0") or 0),
                "hallazgos_json": self._load_json(self._first(row, "hallazgos_json", "Hallazgos_JSON"), []),
                "omitidos_json": self._load_json(self._first(row, "omitidos_json", "Omitidos_JSON"), []),
                "bloque_actual": self._first(row, "bloque_actual", "Bloque_actual", default="A"),
                "resultados_json": self._load_json(self._first(row, "resultados_json", "Resultados_JSON"), {}),
                "stock_total": int(self._first(row, "stock_total", default="0") or 0),
                "stock_actual": int(self._first(row, "stock_actual", default="0") or 0),
                "stock_items_json": self._load_json(self._first(row, "stock_items_json", "Stock_Items_JSON"), []),
                "desvios_libres_json": self._load_json(self._first(row, "desvios_libres_json", "Desvios_Libres_JSON"), []),
                "compromisos_firmados": self._first(row, "compromisos_firmados", "Compromisos_Firmados", default=""),
            })
            self.known_sesiones.add(self._first(row, "id_sesion"))
        self._upsert_many("sesiones_auditoria", payload, "id_sesion", dry_run)

    def _migrate_reportes(self, dry_run: bool = False) -> None:
        rows = self._records("Reportes")
        payload = []
        for row in rows:
            id_sucursal = self._first(row, "id_sucursal", "ID_Sucursal")
            if id_sucursal and self.known_sucursales and id_sucursal not in self.known_sucursales:
                logger.warning("Skipping reporte %s due to unknown sucursal %s", self._first(row, "id"), id_sucursal)
                continue
            reporte_id = self._first(row, "id", "ID")
            payload.append({
                "id": reporte_id or f"rep_{uuid.uuid4().hex[:10]}",
                "fecha": self._parse_date(self._first(row, "fecha", "Fecha")) or datetime.now(timezone.utc).date().isoformat(),
                "hora": self._first(row, "hora", "Hora") or datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "cuadrilla": self._first(row, "cuadrilla", "Cuadrilla"),
                "auditor": self._first(row, "auditor", "Auditor"),
                "id_sucursal": id_sucursal or None,
                "sucursal": self._first(row, "sucursal", "Sucursal"),
                "area": self._first(row, "area", "Area"),
                "subitem": self._first(row, "subitem", "Subitem"),
                "descripcion": self._first(row, "descripcion", "Descripcion"),
                "severidad": self._normalize_severidad(self._first(row, "severidad", "Severidad", "Plan_Accion", default="Baja")),
                "foto_url": self._first(row, "foto_url", "Foto_URL", default="") or None,
                "creado_por_audio": self._parse_bool(self._first(row, "creado_por_audio", "Creado_Por_Audio")),
                "timestamp": self._datetime_or_none(self._first(row, "timestamp", "Timestamp")) or self._now_iso(),
            })
            if reporte_id:
                self.known_reportes.add(reporte_id)
        self._upsert_many("reportes", payload, "id", dry_run)

    def _migrate_gestion(self, dry_run: bool = False) -> None:
        rows = self._records("Gestion")
        payload = []
        for row in rows:
            id_reporte = self._first(row, "id_reporte", "ID_Reporte", "Reporte_ID")
            raw_id = self._first(row, "id_gestion", "ID_Gestion", "ID")
            id_gestion = raw_id or self._stable_id("ges", [
                id_reporte,
                self._first(row, "Estado", "id_sucursal"),
                self._first(row, "Responsable_Nombre", "desvio"),
                self._first(row, "Notas", "Timestamp"),
            ])
            if id_reporte and self.known_reportes and id_reporte not in self.known_reportes:
                logger.warning("Skipping gestion %s due to unknown reporte %s", id_gestion, id_reporte)
                continue
            raw_plazo = self._first(row, "plazo_fecha", "Plazo_Fecha", "Notas")
            plazo_fecha = self._parse_date(raw_plazo) or datetime.now(timezone.utc).date().isoformat()
            estado_value = self._first(row, "estado", "Estado", default="")
            payload.append({
                "id_gestion": id_gestion,
                "id_reporte": id_reporte or None,
                "id_sucursal": self._first(row, "id_sucursal", "ID_Sucursal", "Estado") or None,
                "sucursal": self._first(row, "sucursal", "Sucursal", "Responsable_ID"),
                "desvio": self._first(row, "desvio", "Desvio", "Responsable_Nombre"),
                "severidad": self._normalize_severidad(self._first(row, "severidad", "Severidad", default="Baja")),
                "responsable": self._first(row, "responsable", "Responsable", "Fecha_Compromiso"),
                "tel_responsable": self._first(row, "tel_responsable", "Tel_Responsable", "Fecha_Cierre") or None,
                "plazo_fecha": plazo_fecha,
                "plan_accion": self._first(row, "plan_accion", "Plan_Accion", "Timestamp"),
                "estado": self._first(row, "estado", "", default=estado_value or "Abierta"),
                "fecha_cierre": self._datetime_or_none(self._first(row, "fecha_cierre", "Fecha_Cierre")),
                "cerrado_por": self._first(row, "cerrado_por", "Cerrado_Por", default="") or None,
            })
        self._upsert_many("gestion", payload, "id_gestion", dry_run)

    def _migrate_resultados_perfumeria(self, dry_run: bool = False) -> None:
        rows = self._records("Resultados_Perfumeria")
        if not rows:
            rows = self._records("Resultado_Perfumeria")
        payload = []
        for row in rows:
            id_sesion = self._first(row, "id_sesion", "ID_Sesion")
            if id_sesion and self.known_sesiones and id_sesion not in self.known_sesiones:
                logger.warning("Skipping resultado_perfumeria %s due to unknown session %s", self._first(row, "id"), id_sesion)
                continue
            payload.append({
                "id": self._first(row, "id", "ID"),
                "id_sesion": id_sesion,
                "bloque_id": self._first(row, "bloque_id", "Bloque_ID"),
                "punto_orden": int(self._first(row, "punto_orden", "Punto_Orden", default="0") or 0),
                "pregunta": self._first(row, "pregunta", "Pregunta"),
                "respuesta_json": self._load_json(self._first(row, "respuesta_json", "Respuesta_JSON"), {}),
                "tipo_respuesta": self._first(row, "tipo_respuesta", "Tipo_Respuesta"),
                "foto_url": self._first(row, "foto_url", "Foto_URL", default="") or None,
                "timestamp": self._datetime_or_none(self._first(row, "timestamp", "Timestamp")) or self._now_iso(),
            })
        self._upsert_many("resultados_perfumeria", payload, "id", dry_run)

    def _migrate_control_stock(self, dry_run: bool = False) -> None:
        rows = self._records("Control_Stock")
        payload = []
        for row in rows:
            id_sesion = self._first(row, "auditoria_id", "Auditoria_ID")
            if id_sesion and self.known_sesiones and id_sesion not in self.known_sesiones:
                logger.warning("Skipping control_stock %s due to unknown session %s", self._first(row, "id"), id_sesion)
                continue
            payload.append({
                "id": self._first(row, "id", "ID") or f"stk_{uuid.uuid4().hex[:10]}",
                "auditoria_id": id_sesion or None,
                "sucursal_id": self._first(row, "sucursal_id", "Sucursal_ID") or None,
                "fecha": self._parse_date(self._first(row, "fecha", "Fecha")) or datetime.now(timezone.utc).date().isoformat(),
                "auditor": self._first(row, "auditor", "Auditor"),
                "nombre_item": self._first(row, "nombre_item", "Nombre_Item", "producto", "Producto"),
                "stock_fisico": int(self._first(row, "stock_fisico", "Stock_Fisico", default="0") or 0),
                "stock_sistema": int(self._first(row, "stock_sistema", "Stock_Sistema", default="0") or 0),
                "diferencia": int(self._first(row, "diferencia", "Diferencia", default="0") or 0),
                "alerta": self._first(row, "alerta", "Alerta", default="NO"),
            })
        self._upsert_many("control_stock", payload, "id", dry_run)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _load_json(value: Any, default: Any) -> Any:
        if value in (None, ""):
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except Exception:
            return default

    @staticmethod
    def _first(row: Dict[str, Any], *keys: str, default: str = "") -> str:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return str(value)
        return default

    @staticmethod
    def _normalize_phone(value: str) -> str:
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    @staticmethod
    def _parse_bool(value: Any) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "yes", "si", "sí"}

    @staticmethod
    def _parse_date(value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        text = str(value)
        if "T" in text:
            text = text.split("T", 1)[0]
        try:
            return datetime.fromisoformat(text).date().isoformat()
        except ValueError:
            return text

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        text = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            return str(value)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_severidad(value: Any) -> str:
        raw = str(value or "").strip()
        normalized = raw[:1].upper() + raw[1:].lower() if raw else "Baja"
        if normalized not in {"Alta", "Media", "Baja"}:
            return "Baja"
        return normalized

    @staticmethod
    def _stable_id(prefix: str, parts: List[str]) -> str:
        token = "|".join(str(part or "").strip() for part in parts)
        return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, token).hex[:12]}"

    @staticmethod
    def _datetime_or_none(value: Any) -> Optional[str]:
        parsed = MigrationRunner._parse_datetime(value)
        if not parsed:
            return None
        try:
            datetime.fromisoformat(parsed.replace("Z", "+00:00"))
            return parsed
        except Exception:
            return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Google Sheets data to Supabase.")
    parser.add_argument("--table", default="all", help="Table to migrate: maestro_auditores, all, etc.")
    parser.add_argument("--confirm", action="store_true", help="Required to actually run the migration.")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without writing to Supabase.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    get_settings()  # fail fast if env is missing

    runner = MigrationRunner()
    runner.migrate(args.table, confirmed=args.confirm, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

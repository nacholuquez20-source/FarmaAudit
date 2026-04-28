"""Verify and optionally bootstrap the Supabase schema for AuditBot Perfumeria.

Usage:
    python verify_supabase_schema.py
    python verify_supabase_schema.py --dry-run
    python verify_supabase_schema.py --auto-fix --confirm
    python verify_supabase_schema.py --auto-fix --confirm --insert-maestros

Notes:
    - This script uses Supabase service-role access for table checks and upserts.
    - It performs best-effort verification of columns, row-shape types, duplicate
      keys, and foreign-key integrity from the live data.
    - If a table is missing, the script writes a repair SQL file using the local
      `supabase_schema.sql` as the source of truth. Direct DDL execution requires
      extra database credentials, so the repair SQL is generated and printed.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from supabase import create_client
from postgrest.exceptions import APIError

from config import Settings

logger = logging.getLogger(__name__)

SCHEMA_SQL_PATH = Path("supabase_schema.sql")
REPAIR_SQL_PATH = Path("verify_supabase_schema_fix.sql")


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    kind: str
    required: bool = True


@dataclass(frozen=True)
class TableSpec:
    label: str
    table: str
    columns: Tuple[ColumnSpec, ...]
    pk: Tuple[str, ...]
    unique: Tuple[Tuple[str, ...], ...] = ()
    fks: Tuple[Tuple[Tuple[str, ...], str, Tuple[str, ...]], ...] = ()
    expected_min_rows: Optional[int] = None


DEFAULT_CHECKLIST_PERFUMERIA: List[Dict[str, Any]] = [
    {"bloque_id": "PRES", "bloque_nombre": "PRESENTACION Y VIDRIERA", "punto_orden": 1, "tipo_respuesta": "foto_si_no", "pregunta": "¿Vidriera limpia y ordenada?", "peso": 5, "critico": False},
    {"bloque_id": "PRES", "bloque_nombre": "PRESENTACION Y VIDRIERA", "punto_orden": 2, "tipo_respuesta": "foto_si_no", "pregunta": "¿Productos exhibidos correctamente?", "peso": 4, "critico": True},
    {"bloque_id": "PRES", "bloque_nombre": "PRESENTACION Y VIDRIERA", "punto_orden": 3, "tipo_respuesta": "si_no", "pregunta": "¿Iluminación adecuada en vidriera?", "peso": 3, "critico": False},
    {"bloque_id": "GOND", "bloque_nombre": "GONDOLAS Y PUNTERAS", "punto_orden": 1, "tipo_respuesta": "foto_si_no", "pregunta": "¿Góndolas limpias y ordenadas?", "peso": 5, "critico": False},
    {"bloque_id": "GOND", "bloque_nombre": "GONDOLAS Y PUNTERAS", "punto_orden": 2, "tipo_respuesta": "foto_si_no", "pregunta": "¿Punteras organizadas correctamente?", "peso": 5, "critico": True},
    {"bloque_id": "GOND", "bloque_nombre": "GONDOLAS Y PUNTERAS", "punto_orden": 3, "tipo_respuesta": "foto_si_no", "pregunta": "¿Hay productos caídos o desordenados?", "peso": 4, "critico": False},
    {"bloque_id": "STOCK", "bloque_nombre": "STOCK Y PROBADORES", "punto_orden": 1, "tipo_respuesta": "numero_audio", "pregunta": "¿Stock físico de perfumes? (cantidades por producto)", "peso": 8, "critico": True},
    {"bloque_id": "STOCK", "bloque_nombre": "STOCK Y PROBADORES", "punto_orden": 2, "tipo_respuesta": "foto_si_no", "pregunta": "¿Probadores disponibles y limpios?", "peso": 6, "critico": True},
    {"bloque_id": "STOCK", "bloque_nombre": "STOCK Y PROBADORES", "punto_orden": 3, "tipo_respuesta": "numero_audio", "pregunta": "¿Stock de probadores completo?", "peso": 5, "critico": False},
    {"bloque_id": "REVISTA", "bloque_nombre": "REVISTA DE VENTAS", "punto_orden": 1, "tipo_respuesta": "lista_texto", "pregunta": "¿Qué productos están en la revista de ventas? (envía lista o foto)", "peso": 7, "critico": True},
    {"bloque_id": "REVISTA", "bloque_nombre": "REVISTA DE VENTAS", "punto_orden": 2, "tipo_respuesta": "si_no", "pregunta": "¿Precios coinciden con revista?", "peso": 4, "critico": False},
    {"bloque_id": "REVISTA", "bloque_nombre": "REVISTA DE VENTAS", "punto_orden": 3, "tipo_respuesta": "si_no", "pregunta": "¿Promociones vigentes están activas?", "peso": 3, "critico": False},
    {"bloque_id": "PERSONAL", "bloque_nombre": "UNIFORME Y PERSONAL", "punto_orden": 1, "tipo_respuesta": "foto_si_no", "pregunta": "¿Personal con uniforme completo?", "peso": 3, "critico": False},
    {"bloque_id": "PERSONAL", "bloque_nombre": "UNIFORME Y PERSONAL", "punto_orden": 2, "tipo_respuesta": "si_no", "pregunta": "¿Limpieza personal adecuada?", "peso": 3, "critico": False},
    {"bloque_id": "PERSONAL", "bloque_nombre": "UNIFORME Y PERSONAL", "punto_orden": 3, "tipo_respuesta": "si_no", "pregunta": "¿Asesor de perfumería disponible?", "peso": 5, "critico": True},
    {"bloque_id": "COND", "bloque_nombre": "CONDICIONES GENERALES", "punto_orden": 1, "tipo_respuesta": "si_no", "pregunta": "¿Temperatura ambiente adecuada?", "peso": 3, "critico": False},
    {"bloque_id": "COND", "bloque_nombre": "CONDICIONES GENERALES", "punto_orden": 2, "tipo_respuesta": "si_no", "pregunta": "¿Iluminación general del área?", "peso": 3, "critico": False},
    {"bloque_id": "COND", "bloque_nombre": "CONDICIONES GENERALES", "punto_orden": 3, "tipo_respuesta": "foto_si_no", "pregunta": "¿Piso limpio y sin obstáculos?", "peso": 4, "critico": False},
    {"bloque_id": "ATENCION", "bloque_nombre": "ATENCIÓN AL CLIENTE", "punto_orden": 1, "tipo_respuesta": "si_no", "pregunta": "¿Personal disponible para asesorar?", "peso": 5, "critico": True},
    {"bloque_id": "ATENCION", "bloque_nombre": "ATENCIÓN AL CLIENTE", "punto_orden": 2, "tipo_respuesta": "si_no", "pregunta": "¿Ofrece probadas a clientes?", "peso": 4, "critico": False},
    {"bloque_id": "ATENCION", "bloque_nombre": "ATENCIÓN AL CLIENTE", "punto_orden": 3, "tipo_respuesta": "si_no", "pregunta": "¿Trato profesional y amable?", "peso": 5, "critico": True},
    {"bloque_id": "EXTRAS", "bloque_nombre": "OBSERVACIONES EXTRAS", "punto_orden": 1, "tipo_respuesta": "mixto", "pregunta": "¿Hallazgos, problemas o sugerencias? (texto/audio/foto)", "peso": 0, "critico": False},
    {"bloque_id": "EXTRAS", "bloque_nombre": "OBSERVACIONES EXTRAS", "punto_orden": 2, "tipo_respuesta": "si_no", "pregunta": "¿Requiere seguimiento inmediato?", "peso": 1, "critico": False},
]


TABLES: Tuple[TableSpec, ...] = (
    TableSpec(
        label="maestro_auditores",
        table="auditores",
        columns=(
            ColumnSpec("telefono", "text"),
            ColumnSpec("nombre", "text"),
            ColumnSpec("cuadrilla", "text"),
            ColumnSpec("activo", "boolean"),
            ColumnSpec("created_at", "timestamptz", required=False),
            ColumnSpec("updated_at", "timestamptz", required=False),
        ),
        pk=("telefono",),
    ),
    TableSpec(
        label="maestro_sucursales",
        table="sucursales",
        columns=(
            ColumnSpec("id", "text"),
            ColumnSpec("nombre", "text"),
            ColumnSpec("direccion", "text"),
            ColumnSpec("responsable", "text", required=False),
            ColumnSpec("tel_responsable", "text", required=False),
            ColumnSpec("zona", "text"),
            ColumnSpec("created_at", "timestamptz", required=False),
            ColumnSpec("updated_at", "timestamptz", required=False),
        ),
        pk=("id",),
    ),
    TableSpec(
        label="checklist_perfumeria",
        table="checklist_perfumeria",
        columns=(
            ColumnSpec("id", "bigint", required=False),
            ColumnSpec("bloque_id", "text"),
            ColumnSpec("bloque_nombre", "text"),
            ColumnSpec("punto_orden", "integer"),
            ColumnSpec("tipo_respuesta", "text"),
            ColumnSpec("pregunta", "text"),
            ColumnSpec("peso", "integer", required=False),
            ColumnSpec("critico", "boolean", required=False),
            ColumnSpec("created_at", "timestamptz", required=False),
            ColumnSpec("updated_at", "timestamptz", required=False),
        ),
        pk=("bloque_id", "punto_orden"),
        unique=(("bloque_id", "punto_orden"),),
        expected_min_rows=23,
    ),
    TableSpec(
        label="conversaciones",
        table="conversaciones",
        columns=(
            ColumnSpec("telefono", "text"),
            ColumnSpec("estado_actual", "text", required=False),
            ColumnSpec("id_pendiente", "text", required=False),
            ColumnSpec("ultimo_mensaje", "text", required=False),
            ColumnSpec("timestamp", "timestamptz", required=False),
            ColumnSpec("updated_at", "timestamptz", required=False),
        ),
        pk=("telefono",),
    ),
    TableSpec(
        label="pendientes",
        table="pendientes",
        columns=(
            ColumnSpec("id_temp", "text"),
            ColumnSpec("telefono_auditor", "text"),
            ColumnSpec("estado", "text"),
            ColumnSpec("datos_json", "jsonb", required=False),
            ColumnSpec("timestamp_creacion", "timestamptz", required=False),
            ColumnSpec("expira_en", "timestamptz"),
        ),
        pk=("id_temp",),
        fks=((("telefono_auditor",), "auditores", ("telefono",)),),
    ),
    TableSpec(
        label="sesiones_auditoria",
        table="sesiones_auditoria",
        columns=(
            ColumnSpec("id_sesion", "text"),
            ColumnSpec("telefono_auditor", "text"),
            ColumnSpec("sucursal_id", "text"),
            ColumnSpec("estado", "text"),
            ColumnSpec("timestamp_inicio", "timestamptz", required=False),
            ColumnSpec("timestamp_ultimo_punto", "timestamptz", required=False),
            ColumnSpec("punto_actual", "integer", required=False),
            ColumnSpec("total_puntos", "integer", required=False),
            ColumnSpec("hallazgos_json", "jsonb", required=False),
            ColumnSpec("omitidos_json", "jsonb", required=False),
            ColumnSpec("bloque_actual", "text", required=False),
            ColumnSpec("resultados_json", "jsonb", required=False),
            ColumnSpec("stock_total", "integer", required=False),
            ColumnSpec("stock_actual", "integer", required=False),
            ColumnSpec("stock_items_json", "jsonb", required=False),
            ColumnSpec("desvios_libres_json", "jsonb", required=False),
            ColumnSpec("compromisos_firmados", "text", required=False),
        ),
        pk=("id_sesion",),
        fks=((("telefono_auditor",), "auditores", ("telefono",)), (("sucursal_id",), "sucursales", ("id",))),
    ),
    TableSpec(
        label="resultados_perfumeria",
        table="resultados_perfumeria",
        columns=(
            ColumnSpec("id", "bigint", required=False),
            ColumnSpec("id_sesion", "text"),
            ColumnSpec("bloque_id", "text"),
            ColumnSpec("punto_orden", "integer"),
            ColumnSpec("pregunta", "text"),
            ColumnSpec("respuesta_json", "jsonb"),
            ColumnSpec("tipo_respuesta", "text"),
            ColumnSpec("foto_url", "text", required=False),
            ColumnSpec("timestamp", "timestamptz", required=False),
        ),
        pk=("id",),
        fks=((("id_sesion",), "sesiones_auditoria", ("id_sesion",)), (("bloque_id", "punto_orden"), "checklist_perfumeria", ("bloque_id", "punto_orden"))),
    ),
    TableSpec(
        label="reportes",
        table="reportes",
        columns=(
            ColumnSpec("id", "text"),
            ColumnSpec("fecha", "text"),
            ColumnSpec("hora", "text"),
            ColumnSpec("cuadrilla", "text", required=False),
            ColumnSpec("auditor", "text"),
            ColumnSpec("id_sucursal", "text"),
            ColumnSpec("sucursal", "text"),
            ColumnSpec("area", "text", required=False),
            ColumnSpec("subitem", "text", required=False),
            ColumnSpec("descripcion", "text"),
            ColumnSpec("severidad", "text"),
            ColumnSpec("foto_url", "text", required=False),
            ColumnSpec("creado_por_audio", "boolean", required=False),
            ColumnSpec("timestamp", "timestamptz", required=False),
        ),
        pk=("id",),
        fks=((("id_sucursal",), "sucursales", ("id",)),),
    ),
    TableSpec(
        label="gestiones",
        table="gestion",
        columns=(
            ColumnSpec("id_gestion", "text"),
            ColumnSpec("id_reporte", "text"),
            ColumnSpec("id_sucursal", "text"),
            ColumnSpec("sucursal", "text"),
            ColumnSpec("desvio", "text"),
            ColumnSpec("severidad", "text"),
            ColumnSpec("responsable", "text"),
            ColumnSpec("tel_responsable", "text", required=False),
            ColumnSpec("plazo_fecha", "date"),
            ColumnSpec("plan_accion", "text"),
            ColumnSpec("estado", "text", required=False),
            ColumnSpec("fecha_cierre", "timestamptz", required=False),
            ColumnSpec("cerrado_por", "text", required=False),
            ColumnSpec("created_at", "timestamptz", required=False),
        ),
        pk=("id_gestion",),
        fks=((("id_reporte",), "reportes", ("id",)), (("id_sucursal",), "sucursales", ("id",))),
    ),
)


class SchemaVerifier:
    def __init__(self) -> None:
        settings = Settings()
        if not settings.supabase_url or not settings.supabase_service_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required")
        self.settings = settings
        self.client = create_client(settings.supabase_url, settings.supabase_service_key)
        self.issues: List[str] = []
        self.warnings: List[str] = []
        self.ok_messages: List[str] = []

    def _table_query(self, table: str):
        return self.client.table(table)

    def check_connection(self) -> None:
        try:
            self._table_query("sucursales").select("id").limit(1).execute()
            self.ok_messages.append("Connected to Supabase")
        except Exception as exc:
            raise RuntimeError(f"Could not connect to Supabase: {exc}") from exc

    def table_exists(self, table: str) -> bool:
        try:
            self._table_query(table).select("*", count="exact", head=True).limit(0).execute()
            return True
        except APIError as exc:
            message = str(exc)
            if "Could not find the table" in message or "PGRST205" in message:
                return False
            raise
        except Exception:
            return False

    def fetch_rows(self, table: str) -> List[Dict[str, Any]]:
        response = self._table_query(table).select("*").execute()
        return response.data or []

    def count_rows(self, table: str) -> int:
        response = self._table_query(table).select("*", count="exact", head=True).execute()
        return int(response.count or 0)

    def verify(self) -> None:
        self.check_connection()

        for spec in TABLES:
            if not self.table_exists(spec.table):
                self.issues.append(f"Missing table: {spec.label} ({spec.table})")
                continue
            self.ok_messages.append(f"Table exists: {spec.label}")

            self._verify_columns(spec)
            self._verify_cardinality(spec)
            self._verify_primary_key(spec)
            self._verify_unique_constraints(spec)
            self._verify_foreign_keys(spec)
            self._verify_type_shapes(spec)

        self._verify_integrity()

    def _verify_columns(self, spec: TableSpec) -> None:
        select_clause = ",".join(col.name for col in spec.columns if col.required)
        if not select_clause:
            return
        try:
            self._table_query(spec.table).select(select_clause).limit(0).execute()
        except APIError as exc:
            message = str(exc)
            for col in spec.columns:
                if col.required and col.name in message:
                    self.issues.append(f"Missing field: {spec.table}.{col.name}")
                elif col.required and "does not exist" in message:
                    self.issues.append(f"Missing field: {spec.table}.{col.name}")
            if "does not exist" not in message and "column" not in message:
                self.warnings.append(f"Could not fully verify columns for {spec.table}: {exc}")
        except Exception as exc:
            self.warnings.append(f"Could not fully verify columns for {spec.table}: {exc}")

    def _verify_cardinality(self, spec: TableSpec) -> None:
        if spec.expected_min_rows is None:
            return
        try:
            count = self.count_rows(spec.table)
            if count < spec.expected_min_rows:
                self.issues.append(f"{spec.label}: expected at least {spec.expected_min_rows} rows, found {count}")
            else:
                self.ok_messages.append(f"{spec.label}: {count} rows")
        except Exception as exc:
            self.warnings.append(f"Could not count rows for {spec.table}: {exc}")

    def _verify_primary_key(self, spec: TableSpec) -> None:
        try:
            rows = self.fetch_rows(spec.table)
            if not rows:
                return
            seen: Dict[Tuple[Any, ...], int] = {}
            for row in rows:
                key = tuple(row.get(col) for col in spec.pk)
                seen[key] = seen.get(key, 0) + 1
            duplicates = [key for key, count in seen.items() if count > 1]
            if duplicates:
                self.issues.append(f"{spec.table}: duplicate primary key values found: {duplicates[:3]}")
        except Exception as exc:
            self.warnings.append(f"Could not verify primary key uniqueness for {spec.table}: {exc}")

    def _verify_unique_constraints(self, spec: TableSpec) -> None:
        if not spec.unique:
            return
        try:
            rows = self.fetch_rows(spec.table)
            for unique_cols in spec.unique:
                seen: Dict[Tuple[Any, ...], int] = {}
                for row in rows:
                    key = tuple(row.get(col) for col in unique_cols)
                    seen[key] = seen.get(key, 0) + 1
                duplicates = [key for key, count in seen.items() if count > 1]
                if duplicates:
                    self.issues.append(f"{spec.table}: duplicate unique values for {unique_cols}: {duplicates[:3]}")
        except Exception as exc:
            self.warnings.append(f"Could not verify unique constraints for {spec.table}: {exc}")

    def _verify_foreign_keys(self, spec: TableSpec) -> None:
        if not spec.fks:
            return
        try:
            rows = self.fetch_rows(spec.table)
            parent_cache: Dict[str, List[Dict[str, Any]]] = {}
            for local_cols, ref_table, ref_cols in spec.fks:
                if ref_table not in parent_cache:
                    parent_cache[ref_table] = self.fetch_rows(ref_table)
                parent_rows = parent_cache[ref_table]
                parent_keys = {tuple(r.get(c) for c in ref_cols) for r in parent_rows}
                orphan_count = 0
                for row in rows:
                    local_key = tuple(row.get(c) for c in local_cols)
                    if any(v in (None, "") for v in local_key):
                        continue
                    if local_key not in parent_keys:
                        orphan_count += 1
                if orphan_count:
                    self.warnings.append(f"{spec.table}: {orphan_count} orphan rows for FK {local_cols} -> {ref_table}.{ref_cols}")
        except Exception as exc:
            self.warnings.append(f"Could not verify foreign keys for {spec.table}: {exc}")

    def _verify_type_shapes(self, spec: TableSpec) -> None:
        try:
            rows = self.fetch_rows(spec.table)
            if not rows:
                return
            sample = rows[:25]
            for col in spec.columns:
                if not col.required:
                    continue
                mismatches = 0
                for row in sample:
                    value = row.get(col.name)
                    if value in (None, ""):
                        continue
                    if not self._matches_kind(value, col.kind):
                        mismatches += 1
                if mismatches:
                    self.issues.append(
                        f"Wrong type: {spec.table}.{col.name} (expected {col.kind.upper()}, mismatched in {mismatches} sampled rows)"
                    )
        except Exception as exc:
            self.warnings.append(f"Could not verify data shapes for {spec.table}: {exc}")

    def _matches_kind(self, value: Any, kind: str) -> bool:
        if kind in {"text", "timestamptz", "date"}:
            return isinstance(value, str)
        if kind in {"integer", "bigint"}:
            return isinstance(value, int) and not isinstance(value, bool)
        if kind == "boolean":
            return isinstance(value, bool)
        if kind == "jsonb":
            return isinstance(value, (dict, list))
        return True

    def _verify_integrity(self) -> None:
        try:
            reportes = self.fetch_rows("reportes")
            sucursales = {row.get("id") for row in self.fetch_rows("sucursales")}
            reportes_orphans = [row.get("id") for row in reportes if row.get("id_sucursal") not in (None, "", *sucursales)]
            if reportes_orphans:
                self.warnings.append(f"reportes: {len(reportes_orphans)} rows reference missing sucursal_id")

            sesiones = self.fetch_rows("sesiones_auditoria")
            auditores = {row.get("telefono") for row in self.fetch_rows("auditores")}
            sesiones_orphans = [row.get("id_sesion") for row in sesiones if row.get("telefono_auditor") not in (None, "", *auditores)]
            if sesiones_orphans:
                self.warnings.append(f"sesiones_auditoria: {len(sesiones_orphans)} rows reference missing auditor")
        except Exception as exc:
            self.warnings.append(f"Could not complete integrity verification: {exc}")

    def print_report(self) -> None:
        if self.issues:
            for issue in self.issues:
                print(f"ERROR: {issue}")
        else:
            print("OK: All tables exist and are correctly configured")

        for msg in self.ok_messages:
            if msg.startswith("Connected"):
                continue
            print(f"OK: {msg}")

        for warning in self.warnings:
            print(f"WARN: {warning}")

        if not self.issues:
            print("OK: Ready to run audit bot")
        else:
            print("Run: python verify_supabase_schema.py --auto-fix --confirm")

    def auto_fix(self, confirm: bool, dry_run: bool, insert_maestros: bool) -> None:
        if not confirm:
            raise SystemExit("Add --confirm to apply auto-fix actions.")

        if not SCHEMA_SQL_PATH.exists():
            raise FileNotFoundError(f"Missing {SCHEMA_SQL_PATH}")

        shutil.copyfile(SCHEMA_SQL_PATH, REPAIR_SQL_PATH)
        logger.info("Wrote repair SQL to %s", REPAIR_SQL_PATH)

        if dry_run:
            print(f"[dry-run] Would write repair SQL to {REPAIR_SQL_PATH}")
            return

        if insert_maestros:
            self._insert_maestros_from_sheets()
        self._seed_checklist_perfumeria()

    def _insert_maestros_from_sheets(self) -> None:
        try:
            from sheets_legacy import SheetsManager as LegacySheetsManager
        except Exception as exc:
            self.warnings.append(f"Google Sheets reader unavailable: {exc}")
            return

        try:
            legacy = LegacySheetsManager()
            auditores = legacy.get_all_auditores()
            sucursales = legacy.get_all_sucursales()
            if auditores:
                self.client.table("auditores").upsert(
                    [
                        {
                            "telefono": a.telefono,
                            "nombre": a.nombre,
                            "cuadrilla": a.cuadrilla,
                            "activo": a.activo,
                        }
                        for a in auditores
                    ],
                    on_conflict="telefono",
                ).execute()
            if sucursales:
                self.client.table("sucursales").upsert(
                    [
                        {
                            "id": s.id,
                            "nombre": s.nombre,
                            "direccion": s.direccion,
                            "responsable": s.responsable,
                            "tel_responsable": s.tel_responsable,
                            "zona": s.zona,
                        }
                        for s in sucursales
                    ],
                    on_conflict="id",
                ).execute()
            print(f"Inserted maestros: auditores={len(auditores)}, sucursales={len(sucursales)}")
        except Exception as exc:
            raise RuntimeError(f"Could not insert maestros from Google Sheets: {exc}") from exc

    def _seed_checklist_perfumeria(self) -> None:
        existing_count = self.count_rows("checklist_perfumeria") if self.table_exists("checklist_perfumeria") else 0
        if existing_count >= 23:
            self.ok_messages.append(f"checklist_perfumeria: {existing_count} rows")
            return

        payload = list(DEFAULT_CHECKLIST_PERFUMERIA)
        self.client.table("checklist_perfumeria").upsert(
            payload,
            on_conflict="bloque_id,punto_orden",
        ).execute()
        count = self.count_rows("checklist_perfumeria")
        self.ok_messages.append(f"checklist_perfumeria: {count} rows")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify and bootstrap the Supabase schema used by AuditBot Perfumeria.")
    parser.add_argument("--auto-fix", action="store_true", help="Write a repair SQL file and seed missing master data.")
    parser.add_argument("--confirm", action="store_true", help="Required to execute auto-fix actions.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be written without applying fixes.")
    parser.add_argument("--insert-maestros", action="store_true", help="Upsert auditores/sucursales from Google Sheets if available.")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("postgrest").setLevel(logging.WARNING)
    logging.getLogger("supabase").setLevel(logging.WARNING)

    try:
        verifier = SchemaVerifier()
        verifier.verify()
        verifier.print_report()

        if args.auto_fix:
            verifier.auto_fix(confirm=args.confirm, dry_run=args.dry_run, insert_maestros=args.insert_maestros)

        return 0 if not verifier.issues else 1
    except Exception as exc:
        logger.exception("Schema verification failed")
        print(f"ERROR: Schema verification failed: {exc}")
        print("Suggestion: check SUPABASE_URL / SUPABASE_SERVICE_KEY and run again.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Supabase-backed storage layer for AuditBot.

This module preserves the public API that router.py and main.py already use,
but the persistence layer is now Supabase/PostgreSQL instead of Google Sheets.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config import get_settings
from models import (
    AreaSubitem,
    Auditor,
    ChecklistPerfumeriaPunto,
    ChecklistPunto,
    ConversationState,
    Conversacion,
    DesvioLibre,
    Gestion,
    GestionState,
    ItemBloque,
    Pendiente,
    Reporte,
    ResultadoItem,
    SesionAuditoria,
    Severidad,
    StockItem,
    Sucursal,
)
from supabase_client import SupabaseManager

logger = logging.getLogger(__name__)


class SheetsManager:
    """Compatibility wrapper that keeps the legacy SheetsManager API."""

    _instance = None
    _cache: Dict[str, tuple] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SheetsManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        self.db = SupabaseManager()
        self.db.validate_connection()
        logger.info("Supabase-backed SheetsManager initialized")

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------
    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache:
            return False
        _, timestamp = self._cache[key]
        ttl = get_settings().cache_ttl
        return (datetime.utcnow() - timestamp).total_seconds() < ttl

    def _set_cache(self, key: str, data: Any) -> None:
        self._cache[key] = (data, datetime.utcnow())

    def _get_cache(self, key: str) -> Any:
        if self._is_cache_valid(key):
            return self._cache[key][0]
        return None

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        if not phone:
            return ""
        return "".join(ch for ch in str(phone) if ch.isdigit())

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if value in (None, ""):
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        text = str(value)
        if "T" in text:
            text = text.split("T", 1)[0]
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    @staticmethod
    def _json_string(value: Any, default: Any) -> str:
        if value in (None, ""):
            return json.dumps(default, ensure_ascii=False)
        if isinstance(value, str):
            try:
                json.loads(value)
                return value
            except Exception:
                return json.dumps(default, ensure_ascii=False)
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Maestros
    # ------------------------------------------------------------------
    def get_auditor(self, telefono: str) -> Optional[Auditor]:
        telefono_norm = self._normalize_phone(telefono)
        return self.db.get_auditor(telefono_norm) or self.db.get_auditor(telefono)

    def get_all_auditores(self) -> List[Auditor]:
        cached = self._get_cache("auditores")
        if cached is not None:
            return cached
        auditores = self.db.list_auditores()
        self._set_cache("auditores", auditores)
        return auditores

    def get_sucursal(self, id_sucursal: str) -> Optional[Sucursal]:
        return self.db.get_sucursal(id_sucursal)

    def get_all_sucursales(self) -> List[Sucursal]:
        cached = self._get_cache("sucursales")
        if cached is not None:
            return cached
        sucursales = self.db.list_sucursales()
        self._set_cache("sucursales", sucursales)
        return sucursales

    def get_all_areas(self) -> List[AreaSubitem]:
        cached = self._get_cache("catalogo_areas")
        if cached is not None:
            return cached
        rows = self.db.list_catalogo_areas()
        areas = [
            AreaSubitem(
                area=row.get("area", ""),
                subitems=row.get("subitems", []),
            )
            for row in rows
        ]
        self._set_cache("catalogo_areas", areas)
        return areas

    # ------------------------------------------------------------------
    # Conversaciones
    # ------------------------------------------------------------------
    def get_conversacion(self, telefono: str) -> Optional[Conversacion]:
        return self.db.get_conversacion(telefono)

    def update_conversacion(
        self,
        telefono: str,
        estado: ConversationState,
        id_pendiente: Optional[str] = None,
        ultimo_mensaje: str = "",
    ) -> None:
        self.db.update_conversacion(telefono, estado, id_pendiente, ultimo_mensaje)

    # ------------------------------------------------------------------
    # Pendientes
    # ------------------------------------------------------------------
    def create_pendiente(
        self,
        telefono_auditor: str,
        estado: str = "esperando_confirmacion",
        datos_json: str = "{}",
        timeout_minutes: int = 5,
    ) -> str:
        return self.db.create_pendiente(
            telefono_auditor=telefono_auditor,
            estado=estado,
            datos_json=datos_json,
            timeout_minutes=timeout_minutes,
        )

    def get_pendiente(self, id_temp: str) -> Optional[Pendiente]:
        return self.db.get_pendiente(id_temp)

    def delete_pendiente(self, id_temp: str) -> None:
        self.db.delete_pendiente(id_temp)

    def get_expired_pendientes(self) -> List[Pendiente]:
        return self.db.get_expired_pendientes()

    # ------------------------------------------------------------------
    # Reportes / gestión
    # ------------------------------------------------------------------
    def create_reporte(self, reporte: Reporte) -> str:
        return self.db.create_reporte(reporte)

    def create_gestion(self, gestion: Gestion) -> str:
        return self.db.create_gestion(gestion)

    def get_gestion(self, id_gestion: str) -> Optional[Gestion]:
        return self.db.get_gestion(id_gestion)

    def update_gestion_estado(self, id_gestion: str, nuevo_estado: str) -> None:
        self.db.update_gestion_estado(id_gestion, nuevo_estado)

    def list_gestion_vencidas(self) -> List[Gestion]:
        return self.db.list_gestion_vencidas()

    # ------------------------------------------------------------------
    # Checklist genérico
    # ------------------------------------------------------------------
    def get_checklist(self) -> List[ChecklistPunto]:
        cached = self._get_cache("checklist_plantillas")
        if cached is not None:
            return cached

        rows = self.db.list_checklist_plantillas()
        if rows:
            puntos = [
                ChecklistPunto(
                    punto_orden=int(row.get("punto_orden") or 0),
                    area=row.get("area", ""),
                    descripcion=row.get("descripcion", ""),
                    responsable_default=row.get("responsable_default", ""),
                    severidad_default=row.get("severidad_default", "Media"),
                )
                for row in rows
            ]
        else:
            perfumeria = self.get_checklist_perfumeria_flat()
            puntos = [
                ChecklistPunto(
                    punto_orden=punto.punto_orden,
                    area=punto.bloque_nombre,
                    descripcion=punto.pregunta,
                    responsable_default="",
                    severidad_default="Media",
                )
                for punto in perfumeria
            ]

        puntos.sort(key=lambda p: p.punto_orden)
        self._set_cache("checklist_plantillas", puntos)
        return puntos

    def get_checklist_bloques(self) -> Dict[str, List[ItemBloque]]:
        cached = self._get_cache("checklist_bloques")
        if cached is not None:
            return cached

        rows = self.db.list_checklist_plantillas()
        bloques: Dict[str, List[ItemBloque]] = {}

        if rows:
            for row in rows:
                bloque = row.get("bloque", "")
                item = ItemBloque(
                    item_id=row.get("item_id", ""),
                    bloque=bloque,
                    descripcion=row.get("descripcion", ""),
                    peso=int(row.get("peso") or 5),
                )
                bloques.setdefault(bloque, []).append(item)
        else:
            for punto in self.get_checklist_perfumeria_flat():
                bloque = punto.bloque_nombre or punto.bloque_id
                item = ItemBloque(
                    item_id=f"{punto.bloque_id}-{punto.punto_orden}",
                    bloque=bloque,
                    descripcion=punto.pregunta,
                    peso=punto.peso,
                )
                bloques.setdefault(bloque, []).append(item)

        self._set_cache("checklist_bloques", bloques)
        return bloques

    # ------------------------------------------------------------------
    # Checklist perfumería
    # ------------------------------------------------------------------
    def get_checklist_perfumeria(self) -> Dict[str, List[ChecklistPerfumeriaPunto]]:
        cached = self._get_cache("checklist_perfumeria")
        if cached is not None:
            return cached

        grouped = self.db.get_checklist_perfumeria()
        self._set_cache("checklist_perfumeria", grouped)
        return grouped

    def get_checklist_perfumeria_flat(self) -> List[ChecklistPerfumeriaPunto]:
        return self.db.get_checklist_perfumeria_flat()

    # ------------------------------------------------------------------
    # Sesiones
    # ------------------------------------------------------------------
    def create_sesion(self, sesion: SesionAuditoria) -> str:
        return self.db.create_sesion(sesion)

    def get_sesion(self, id_sesion: str) -> Optional[SesionAuditoria]:
        return self.db.get_sesion(id_sesion)

    def update_sesion(
        self,
        id_sesion: str,
        estado: str,
        timestamp_ultimo_punto: str,
        bloque_actual: str = "A",
        resultados_json: str = "{}",
        stock_items_json: str = "[]",
        desvios_libres_json: str = "[]",
        stock_total: int = 0,
        stock_actual: int = 0,
        punto_actual: int = 0,
        hallazgos_json: str = "[]",
        omitidos_json: str = "[]",
    ) -> None:
        self.db.update_sesion(
            id_sesion=id_sesion,
            estado=estado,
            timestamp_ultimo_punto=timestamp_ultimo_punto,
            bloque_actual=bloque_actual,
            resultados_json=resultados_json,
            stock_items_json=stock_items_json,
            desvios_libres_json=desvios_libres_json,
            stock_total=stock_total,
            stock_actual=stock_actual,
            punto_actual=punto_actual,
            hallazgos_json=hallazgos_json,
            omitidos_json=omitidos_json,
        )

    def update_sesion_punto(self, id_sesion: str, punto_actual: int) -> None:
        self.db.update_sesion_punto(id_sesion, punto_actual)

    def update_resultados(self, id_sesion: str, resultados_json: str) -> None:
        self.db.update_resultados(id_sesion, resultados_json)

    def update_bloque(self, id_sesion: str, bloque_actual: str) -> None:
        self.db.update_bloque(id_sesion, bloque_actual)

    def get_sesiones_activas_expiradas(self, timeout_min: int = 15) -> List[SesionAuditoria]:
        return self.db.get_sesiones_activas_expiradas(timeout_min=timeout_min)

    # ------------------------------------------------------------------
    # Flujo de auditoría
    # ------------------------------------------------------------------
    def save_bloque_resultado(
        self,
        auditoria_id: str,
        bloque_id: str,
        sucursal_id: str,
        auditor_nombre: str,
        resultados: List[ResultadoItem],
    ) -> None:
        self.db.save_bloque_resultado(
            auditoria_id=auditoria_id,
            bloque_id=bloque_id,
            sucursal_id=sucursal_id,
            auditor_nombre=auditor_nombre,
            resultados=resultados,
        )

    def save_stock_item(
        self,
        auditoria_id: str,
        sucursal_id: str,
        auditor: str,
        item: StockItem,
    ) -> None:
        self.db.save_stock_item(auditoria_id, sucursal_id, auditor, item)

    def save_desvio_libre(
        self,
        auditoria_id: str,
        sucursal_id: str,
        auditor_nombre: str,
        desvio: DesvioLibre,
    ) -> str:
        return self.db.save_desvio_libre(auditoria_id, sucursal_id, auditor_nombre, desvio)


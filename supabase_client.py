"""Supabase data access layer for AuditBot.

Example:
    from supabase_client import SupabaseManager

    db = SupabaseManager()
    db.validate_connection()
    auditor = db.get_auditor("5491112345678")
    db.update_conversacion("5491112345678", "esperando_confirmacion", "pend-123")
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

from config import get_settings
from models import (
    Auditor,
    ChecklistPerfumeriaPunto,
    ChecklistPunto,
    Conversacion,
    DesvioLibre,
    Gestion,
    GestionState,
    ItemBloque,
    Pendiente,
    Reporte,
    ResultadoItem,
    ResultadoPerfumeria,
    Sucursal,
    SesionAuditoria,
    Severidad,
    StockItem,
    ConversationState,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    try:
        return json.loads(value)
    except Exception:
        return default


def _ensure_str(value: Any, default: str = "") -> str:
    if value in (None, ""):
        return default
    return str(value)


def _ensure_bool(value: Any, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "si"}


def _ensure_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _ensure_date(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    if "T" in text:
        return text.split("T", 1)[0]
    return text


def _ensure_datetime(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


class SupabaseManager:
    """Supabase CRUD helpers for AuditBot."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_service_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be configured")

        self.client: Client = create_client(settings.supabase_url, settings.supabase_service_key)

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------
    def _table(self, table_name: str):
        return self.client.table(table_name)

    def _select_one(self, table_name: str, column: str, value: Any) -> Optional[Dict[str, Any]]:
        response = self._table(table_name).select("*").eq(column, value).limit(1).execute()
        data = response.data or []
        return data[0] if data else None

    def _select_many(self, table_name: str, filters: Optional[Dict[str, Any]] = None, order: Optional[str] = None) -> List[Dict[str, Any]]:
        query = self._table(table_name).select("*")
        for key, value in (filters or {}).items():
            if isinstance(value, tuple) and len(value) == 2:
                op, op_value = value
                if op == "lt":
                    query = query.lt(key, op_value)
                elif op == "lte":
                    query = query.lte(key, op_value)
                elif op == "gt":
                    query = query.gt(key, op_value)
                elif op == "gte":
                    query = query.gte(key, op_value)
                elif op == "neq":
                    query = query.neq(key, op_value)
                else:
                    query = query.eq(key, op_value)
            else:
                query = query.eq(key, value)
        if order:
            query = query.order(order)
        response = query.execute()
        return response.data or []

    def _upsert(self, table_name: str, payload: Dict[str, Any], on_conflict: Optional[str] = None) -> Dict[str, Any]:
        response = self._table(table_name).upsert(
            payload,
            on_conflict=on_conflict or "",
        ).execute()
        data = response.data or []
        return data[0] if data else payload

    def _insert(self, table_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self._table(table_name).insert(payload).execute()
        data = response.data or []
        return data[0] if data else payload

    def _update(self, table_name: str, filters: Dict[str, Any], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        query = self._table(table_name).update(payload)
        for key, value in filters.items():
            query = query.eq(key, value)
        response = query.execute()
        return response.data or []

    def _delete(self, table_name: str, filters: Dict[str, Any]) -> None:
        query = self._table(table_name).delete()
        for key, value in filters.items():
            query = query.eq(key, value)
        query.execute()

    def validate_connection(self) -> bool:
        """Ensure Supabase is reachable."""
        self._table("sucursales").select("id").limit(1).execute()
        return True

    def count_rows(self, table_name: str) -> int:
        """Return an exact row count for a table."""
        response = self._table(table_name).select("*", count="exact", head=True).execute()
        return int(response.count or 0)

    # ------------------------------------------------------------------
    # Maestros
    # ------------------------------------------------------------------
    def upsert_auditor(self, auditor: Auditor) -> Auditor:
        payload = {
            "telefono": auditor.telefono,
            "nombre": auditor.nombre,
            "cuadrilla": auditor.cuadrilla,
            "activo": auditor.activo,
        }
        self._upsert("auditores", payload, on_conflict="telefono")
        return auditor

    def get_auditor(self, telefono: str) -> Optional[Auditor]:
        row = self._select_one("auditores", "telefono", _normalize_phone(telefono))
        if not row:
            row = self._select_one("auditores", "telefono", telefono)
        return Auditor(
            telefono=_ensure_str(row.get("telefono") if row else ""),
            nombre=_ensure_str(row.get("nombre") if row else ""),
            cuadrilla=_ensure_str(row.get("cuadrilla") if row else ""),
            activo=_ensure_bool(row.get("activo") if row else True, True),
        ) if row else None

    def list_auditores(self) -> List[Auditor]:
        rows = self._select_many("auditores", order="nombre")
        return [
            Auditor(
                telefono=_ensure_str(row.get("telefono")),
                nombre=_ensure_str(row.get("nombre")),
                cuadrilla=_ensure_str(row.get("cuadrilla")),
                activo=_ensure_bool(row.get("activo"), True),
            )
            for row in rows
        ]

    def upsert_sucursal(self, sucursal: Sucursal) -> Sucursal:
        payload = {
            "id": sucursal.id,
            "nombre": sucursal.nombre,
            "direccion": sucursal.direccion,
            "responsable": sucursal.responsable,
            "tel_responsable": sucursal.tel_responsable,
            "zona": sucursal.zona,
        }
        self._upsert("sucursales", payload, on_conflict="id")
        return sucursal

    def get_sucursal(self, sucursal_id: str) -> Optional[Sucursal]:
        row = self._select_one("sucursales", "id", sucursal_id)
        return Sucursal(
            id=_ensure_str(row.get("id") if row else ""),
            nombre=_ensure_str(row.get("nombre") if row else ""),
            direccion=_ensure_str(row.get("direccion") if row else ""),
            responsable=_ensure_str(row.get("responsable") if row else ""),
            tel_responsable=_ensure_str(row.get("tel_responsable") if row else ""),
            zona=_ensure_str(row.get("zona") if row else ""),
        ) if row else None

    def list_sucursales(self) -> List[Sucursal]:
        rows = self._select_many("sucursales", order="nombre")
        return [
            Sucursal(
                id=_ensure_str(row.get("id")),
                nombre=_ensure_str(row.get("nombre")),
                direccion=_ensure_str(row.get("direccion")),
                responsable=_ensure_str(row.get("responsable")),
                tel_responsable=_ensure_str(row.get("tel_responsable")),
                zona=_ensure_str(row.get("zona")),
            )
            for row in rows
        ]

    def list_catalogo_areas(self) -> List[Dict[str, Any]]:
        return self._select_many("catalogo_areas", order="area")

    def list_checklist_plantillas(self) -> List[Dict[str, Any]]:
        rows = self._select_many("checklist_plantillas")
        return sorted(rows, key=lambda row: (
            _ensure_str(row.get("bloque")),
            _ensure_int(row.get("punto_orden")),
            _ensure_str(row.get("item_id")),
        ))

    # ------------------------------------------------------------------
    # Conversaciones
    # ------------------------------------------------------------------
    def get_conversacion(self, telefono: str) -> Optional[Conversacion]:
        telefono_norm = _normalize_phone(telefono)
        row = self._select_one("conversaciones", "telefono", telefono_norm)
        if not row:
            row = self._select_one("conversaciones", "telefono", telefono)
        if not row:
            return None
        return Conversacion(
            telefono=_ensure_str(row.get("telefono")),
            estado_actual=_parse_state(row.get("estado_actual")),
            id_pendiente=_ensure_str(row.get("id_pendiente"), "") or None,
            ultimo_mensaje=_ensure_str(row.get("ultimo_mensaje")),
            timestamp=_parse_datetime(row.get("timestamp")),
        )

    def upsert_conversacion(
        self,
        telefono: str,
        estado: ConversationState,
        id_pendiente: Optional[str] = None,
        ultimo_mensaje: str = "",
    ) -> Conversacion:
        telefono_norm = _normalize_phone(telefono)
        payload = {
            "telefono": telefono_norm,
            "estado_actual": estado.value,
            "id_pendiente": id_pendiente,
            "ultimo_mensaje": ultimo_mensaje,
            "timestamp": _utcnow().isoformat(),
        }
        self._upsert("conversaciones", payload, on_conflict="telefono")
        return Conversacion(
            telefono=telefono_norm,
            estado_actual=estado,
            id_pendiente=id_pendiente,
            ultimo_mensaje=ultimo_mensaje,
            timestamp=_utcnow(),
        )

    def update_conversacion(
        self,
        telefono: str,
        estado: ConversationState,
        id_pendiente: Optional[str] = None,
        ultimo_mensaje: str = "",
    ) -> None:
        self.upsert_conversacion(telefono, estado, id_pendiente, ultimo_mensaje)

    # ------------------------------------------------------------------
    # Pendientes
    # ------------------------------------------------------------------
    def get_pendiente(self, id_temp: str) -> Optional[Pendiente]:
        row = self._select_one("pendientes", "id_temp", id_temp)
        if not row:
            return None
        return Pendiente(
            id_temp=_ensure_str(row.get("id_temp")),
            telefono_auditor=_ensure_str(row.get("telefono_auditor")),
            estado=_ensure_str(row.get("estado")),
            datos_json=json.dumps(_ensure_json(row.get("datos_json"), {}), ensure_ascii=False),
            timestamp_creacion=_parse_datetime(row.get("timestamp_creacion")) or _utcnow(),
            expira_en=_parse_datetime(row.get("expira_en")) or _utcnow(),
        )

    def create_pendiente(
        self,
        telefono_auditor: str,
        estado: str = "esperando_confirmacion",
        datos_json: str = "{}",
        timeout_minutes: int = 5,
    ) -> str:
        id_temp = uuid.uuid4().hex[:8]
        payload = {
            "id_temp": id_temp,
            "telefono_auditor": _normalize_phone(telefono_auditor),
            "estado": estado,
            "datos_json": _ensure_json(datos_json, {}),
            "timestamp_creacion": _utcnow().isoformat(),
            "expira_en": (_utcnow() + timedelta(minutes=timeout_minutes)).isoformat(),
        }
        self._insert("pendientes", payload)
        return id_temp

    def delete_pendiente(self, id_temp: str) -> None:
        self._delete("pendientes", {"id_temp": id_temp})

    def get_expired_pendientes(self) -> List[Pendiente]:
        now_iso = _utcnow().isoformat()
        rows = self._select_many(
            "pendientes",
            filters={"expira_en": ("lt", now_iso)},
            order="expira_en",
        )
        return [self._row_to_pendiente(row) for row in rows]

    # ------------------------------------------------------------------
    # Sesiones
    # ------------------------------------------------------------------
    def get_sesion(self, id_sesion: str) -> Optional[SesionAuditoria]:
        row = self._select_one("sesiones_auditoria", "id_sesion", id_sesion)
        return self._row_to_sesion(row) if row else None

    def create_sesion(self, sesion: SesionAuditoria) -> str:
        payload = self._sesion_payload(sesion)
        self._insert("sesiones_auditoria", payload)
        return sesion.id_sesion

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
        payload = {
            "estado": estado,
            "timestamp_ultimo_punto": _ensure_datetime(timestamp_ultimo_punto),
            "bloque_actual": bloque_actual,
            "resultados_json": _ensure_json(resultados_json, {}),
            "stock_items_json": _ensure_json(stock_items_json, []),
            "desvios_libres_json": _ensure_json(desvios_libres_json, []),
            "stock_total": stock_total,
            "stock_actual": stock_actual,
            "punto_actual": punto_actual,
            "hallazgos_json": _ensure_json(hallazgos_json, []),
            "omitidos_json": _ensure_json(omitidos_json, []),
        }
        self._update("sesiones_auditoria", {"id_sesion": id_sesion}, payload)

    def update_sesion_punto(self, id_sesion: str, punto_actual: int) -> None:
        self._update("sesiones_auditoria", {"id_sesion": id_sesion}, {"punto_actual": punto_actual, "timestamp_ultimo_punto": _utcnow().isoformat()})

    def update_resultados(self, id_sesion: str, resultados_json: str) -> None:
        self._update("sesiones_auditoria", {"id_sesion": id_sesion}, {"resultados_json": _ensure_json(resultados_json, {})})

    def update_bloque(self, id_sesion: str, bloque_actual: str) -> None:
        self._update("sesiones_auditoria", {"id_sesion": id_sesion}, {"bloque_actual": bloque_actual, "timestamp_ultimo_punto": _utcnow().isoformat()})

    def get_sesiones_activas_expiradas(self, timeout_min: int = 15) -> List[SesionAuditoria]:
        threshold = (_utcnow() - timedelta(minutes=timeout_min)).isoformat()
        rows = self._select_many(
            "sesiones_auditoria",
            filters={
                "estado": ("neq", "cerrada"),
                "timestamp_ultimo_punto": ("lt", threshold),
            },
            order="timestamp_ultimo_punto",
        )
        return [self._row_to_sesion(row) for row in rows]

    # ------------------------------------------------------------------
    # Reportes / Gestion
    # ------------------------------------------------------------------
    def get_reporte(self, reporte_id: str) -> Optional[Reporte]:
        row = self._select_one("reportes", "id", reporte_id)
        return self._row_to_reporte(row) if row else None

    def create_reporte(self, reporte: Reporte) -> str:
        if not reporte.id:
            reporte.id = uuid.uuid4().hex[:12]
        payload = self._reporte_payload(reporte)
        self._insert("reportes", payload)
        return reporte.id

    def list_reportes_by_sucursal(self, id_sucursal: str) -> List[Reporte]:
        rows = self._select_many("reportes", filters={"id_sucursal": id_sucursal}, order="timestamp")
        return [self._row_to_reporte(row) for row in rows]

    def list_by_sucursal(self, id_sucursal: str) -> List[Reporte]:
        return self.list_reportes_by_sucursal(id_sucursal)

    def get_gestion(self, id_gestion: str) -> Optional[Gestion]:
        row = self._select_one("gestion", "id_gestion", id_gestion)
        return self._row_to_gestion(row) if row else None

    def create_gestion(self, gestion: Gestion) -> str:
        if not gestion.id_gestion:
            gestion.id_gestion = uuid.uuid4().hex[:12]
        payload = self._gestion_payload(gestion)
        self._insert("gestion", payload)
        return gestion.id_gestion

    def update_gestion_estado(self, id_gestion: str, nuevo_estado: str, cerrado_por: Optional[str] = None) -> None:
        payload: Dict[str, Any] = {"estado": nuevo_estado}
        if cerrado_por:
            payload["cerrado_por"] = cerrado_por
        if nuevo_estado.lower() == "cerrada":
            payload["fecha_cierre"] = _utcnow().isoformat()
        self._update("gestion", {"id_gestion": id_gestion}, payload)

    def list_gestion_vencidas(self) -> List[Gestion]:
        today = date.today().isoformat()
        rows = self._select_many(
            "gestion",
            filters={"plazo_fecha": ("lt", today), "estado": ("neq", "Cerrada")},
            order="plazo_fecha",
        )
        return [self._row_to_gestion(row) for row in rows]

    def list_vencidas(self) -> List[Gestion]:
        return self.list_gestion_vencidas()

    # ------------------------------------------------------------------
    # Checklist perfumería
    # ------------------------------------------------------------------
    def get_checklist_perfumeria(self) -> Dict[str, List[ChecklistPerfumeriaPunto]]:
        rows = self._select_many("checklist_perfumeria")
        grouped: Dict[str, List[ChecklistPerfumeriaPunto]] = {}
        for row in rows:
            punto = self._row_to_checklist_perfumeria(row)
            grouped.setdefault(punto.bloque_id, []).append(punto)
        for bloque_id in grouped:
            grouped[bloque_id].sort(key=lambda p: p.punto_orden)
        return grouped

    def get_checklist_perfumeria_flat(self) -> List[ChecklistPerfumeriaPunto]:
        puntos: List[ChecklistPerfumeriaPunto] = []
        for items in self.get_checklist_perfumeria().values():
            puntos.extend(items)
        return sorted(puntos, key=lambda p: (p.bloque_id, p.punto_orden))

    def get_checklist_perfumeria_by_bloque(self, bloque_id: str) -> List[ChecklistPerfumeriaPunto]:
        rows = self._select_many("checklist_perfumeria", filters={"bloque_id": bloque_id}, order="punto_orden")
        return [self._row_to_checklist_perfumeria(row) for row in rows]

    def get_all_checklist_perfumeria(self) -> List[ChecklistPerfumeriaPunto]:
        return self.get_checklist_perfumeria_flat()

    def get_by_bloque(self, bloque_id: str) -> List[ChecklistPerfumeriaPunto]:
        return self.get_checklist_perfumeria_by_bloque(bloque_id)

    # ------------------------------------------------------------------
    # Resultados perfumería / stock
    # ------------------------------------------------------------------
    def get_resultado_perfumeria(self, resultado_id: str) -> Optional[ResultadoPerfumeria]:
        row = self._select_one("resultados_perfumeria", "id", resultado_id)
        return self._row_to_resultado_perfumeria(row) if row else None

    def create_resultado_perfumeria(self, resultado: ResultadoPerfumeria) -> str:
        if not resultado.id:
            resultado.id = uuid.uuid4().hex[:12]
        payload = self._resultado_perfumeria_payload(resultado)
        self._insert("resultados_perfumeria", payload)
        return resultado.id

    def list_resultados_perfumeria_by_sesion(self, id_sesion: str) -> List[ResultadoPerfumeria]:
        rows = self._select_many("resultados_perfumeria", filters={"id_sesion": id_sesion}, order="timestamp")
        return [self._row_to_resultado_perfumeria(row) for row in rows]

    def get_control_stock_by_sucursal(self, sucursal_id: str) -> List[Dict[str, Any]]:
        return self._select_many("control_stock", filters={"sucursal_id": sucursal_id}, order="fecha")

    # ------------------------------------------------------------------
    # Compatibilidad con el flujo actual
    # ------------------------------------------------------------------
    def get_all_areas(self) -> List[Any]:
        return [
            type("AreaSubitem", (), {
                "area": row.get("area", ""),
                "subitems": _ensure_json(row.get("subitems"), []),
            })()
            for row in self.list_catalogo_areas()
        ]

    def get_all_auditores(self) -> List[Auditor]:
        return self.list_auditores()

    def get_all_sucursales(self) -> List[Sucursal]:
        return self.list_sucursales()

    def get_checklist(self) -> List[ChecklistPunto]:
        rows = self.list_checklist_plantillas()
        puntos: List[ChecklistPunto] = []
        for row in rows:
            puntos.append(
                ChecklistPunto(
                    punto_orden=_ensure_int(row.get("punto_orden")),
                    area=_ensure_str(row.get("area")),
                    descripcion=_ensure_str(row.get("descripcion")),
                    responsable_default=_ensure_str(row.get("responsable_default")),
                    severidad_default=_ensure_str(row.get("severidad_default"), "Media"),
                )
            )
        return sorted(puntos, key=lambda p: p.punto_orden)

    def get_checklist_bloques(self) -> Dict[str, List[ItemBloque]]:
        bloques: Dict[str, List[ItemBloque]] = {}
        for row in self.list_checklist_plantillas():
            item = ItemBloque(
                item_id=_ensure_str(row.get("item_id")),
                bloque=_ensure_str(row.get("bloque")),
                descripcion=_ensure_str(row.get("descripcion")),
                peso=_ensure_int(row.get("peso"), 5),
            )
            bloques.setdefault(item.bloque, []).append(item)
        return bloques


    # ------------------------------------------------------------------
    # Block-based audit helpers
    # ------------------------------------------------------------------
    def save_bloque_resultado(
        self,
        auditoria_id: str,
        bloque_id: str,
        sucursal_id: str,
        auditor_nombre: str,
        resultados: List[ResultadoItem],
    ) -> None:
        sesion = self.get_sesion(auditoria_id)
        if not sesion:
            logger.warning("Sesion %s not found when saving bloque resultado", auditoria_id)
            return

        sucursal = self.get_sucursal(sucursal_id)
        sucursal_nombre = sucursal.nombre if sucursal else sucursal_id
        hoy = date.today().isoformat()
        hora = _utcnow().strftime("%H:%M")

        for resultado in resultados:
            if not resultado.tiene_desvio or not resultado.descripcion_desvio:
                continue

            severidad = Severidad(resultado.severidad or "Baja")
            reporte = Reporte(
                id="",
                fecha=hoy,
                hora=hora,
                cuadrilla="",
                auditor=auditor_nombre,
                id_sucursal=sucursal_id,
                sucursal=sucursal_nombre,
                area=f"Bloque {bloque_id}",
                subitem=resultado.item_id,
                descripcion=resultado.descripcion_desvio,
                severidad=severidad,
                creado_por_audio=False,
            )
            reporte_id = self.create_reporte(reporte)
            gestion = Gestion(
                id_gestion="",
                id_reporte=reporte_id,
                id_sucursal=sucursal_id,
                sucursal=sucursal_nombre,
                desvio=resultado.descripcion_desvio,
                severidad=severidad,
                responsable=sucursal.responsable if sucursal else "",
                tel_responsable=sucursal.tel_responsable if sucursal else "",
                plazo_fecha=date.today() + timedelta(days=7),
                plan_accion="",
                estado=GestionState.ABIERTA,
            )
            self.create_gestion(gestion)

    def save_stock_item(self, auditoria_id: str, sucursal_id: str, auditor: str, item: StockItem) -> None:
        payload = {
            "id": uuid.uuid4().hex[:12],
            "auditoria_id": auditoria_id,
            "sucursal_id": sucursal_id,
            "fecha": date.today().isoformat(),
            "auditor": auditor,
            "nombre_item": item.nombre,
            "stock_fisico": item.stock_fisico,
            "stock_sistema": item.stock_sistema,
            "diferencia": item.stock_fisico - item.stock_sistema,
            "alerta": "SI" if item.stock_fisico != item.stock_sistema else "NO",
        }
        self._insert("control_stock", payload)

    def save_desvio_libre(
        self,
        auditoria_id: str,
        sucursal_id: str,
        auditor_nombre: str,
        desvio: DesvioLibre,
    ) -> str:
        sucursal = self.get_sucursal(sucursal_id)
        sucursal_nombre = sucursal.nombre if sucursal else sucursal_id
        reporte = Reporte(
            id="",
            fecha=date.today().isoformat(),
            hora=_utcnow().strftime("%H:%M"),
            cuadrilla="",
            auditor=auditor_nombre,
            id_sucursal=sucursal_id,
            sucursal=sucursal_nombre,
            area=desvio.area_estimada or "Observación libre",
            subitem="",
            descripcion=desvio.descripcion,
            severidad=Severidad(desvio.severidad or "Baja"),
            creado_por_audio=False,
        )
        reporte_id = self.create_reporte(reporte)
        gestion = Gestion(
            id_gestion="",
            id_reporte=reporte_id,
            id_sucursal=sucursal_id,
            sucursal=sucursal_nombre,
            desvio=desvio.descripcion,
            severidad=Severidad(desvio.severidad or "Baja"),
            responsable=sucursal.responsable if sucursal else "",
            tel_responsable=sucursal.tel_responsable if sucursal else "",
            plazo_fecha=date.today() + timedelta(days=7),
            plan_accion="",
            estado=GestionState.ABIERTA,
        )
        self.create_gestion(gestion)
        return reporte_id

    # ------------------------------------------------------------------
    # Row mappers
    # ------------------------------------------------------------------
    def _row_to_pendiente(self, row: Dict[str, Any]) -> Pendiente:
        return Pendiente(
            id_temp=_ensure_str(row.get("id_temp")),
            telefono_auditor=_ensure_str(row.get("telefono_auditor")),
            estado=_ensure_str(row.get("estado")),
            datos_json=json.dumps(_ensure_json(row.get("datos_json"), {}), ensure_ascii=False),
            timestamp_creacion=_parse_datetime(row.get("timestamp_creacion")) or _utcnow(),
            expira_en=_parse_datetime(row.get("expira_en")) or _utcnow(),
        )

    def _row_to_sesion(self, row: Optional[Dict[str, Any]]) -> Optional[SesionAuditoria]:
        if not row:
            return None
        return SesionAuditoria(
            id_sesion=_ensure_str(row.get("id_sesion")),
            telefono_auditor=_ensure_str(row.get("telefono_auditor")),
            sucursal_id=_ensure_str(row.get("sucursal_id")),
            estado=_ensure_str(row.get("estado"), "en_curso"),
            timestamp_inicio=_ensure_str(row.get("timestamp_inicio"), _utcnow().isoformat()),
            timestamp_ultimo_punto=_ensure_str(row.get("timestamp_ultimo_punto"), _utcnow().isoformat()),
            punto_actual=_ensure_int(row.get("punto_actual")),
            total_puntos=_ensure_int(row.get("total_puntos")),
            hallazgos_json=json.dumps(_ensure_json(row.get("hallazgos_json"), []), ensure_ascii=False),
            omitidos_json=json.dumps(_ensure_json(row.get("omitidos_json"), []), ensure_ascii=False),
            bloque_actual=_ensure_str(row.get("bloque_actual"), "A"),
            resultados_json=json.dumps(_ensure_json(row.get("resultados_json"), {}), ensure_ascii=False),
            stock_total=_ensure_int(row.get("stock_total")),
            stock_actual=_ensure_int(row.get("stock_actual")),
            stock_items_json=json.dumps(_ensure_json(row.get("stock_items_json"), []), ensure_ascii=False),
            desvios_libres_json=json.dumps(_ensure_json(row.get("desvios_libres_json"), []), ensure_ascii=False),
            compromisos_firmados=_ensure_str(row.get("compromisos_firmados")),
        )

    def _row_to_reporte(self, row: Optional[Dict[str, Any]]) -> Optional[Reporte]:
        if not row:
            return None
        return Reporte(
            id=_ensure_str(row.get("id")),
            fecha=_ensure_str(row.get("fecha")),
            hora=_ensure_str(row.get("hora")),
            cuadrilla=_ensure_str(row.get("cuadrilla")),
            auditor=_ensure_str(row.get("auditor")),
            id_sucursal=_ensure_str(row.get("id_sucursal")),
            sucursal=_ensure_str(row.get("sucursal")),
            area=_ensure_str(row.get("area")),
            subitem=_ensure_str(row.get("subitem")),
            descripcion=_ensure_str(row.get("descripcion")),
            severidad=Severidad(_ensure_str(row.get("severidad"), "Baja")),
            foto_url=row.get("foto_url"),
            creado_por_audio=_ensure_bool(row.get("creado_por_audio"), False),
            timestamp=_parse_datetime(row.get("timestamp")),
        )

    def _row_to_gestion(self, row: Optional[Dict[str, Any]]) -> Optional[Gestion]:
        if not row:
            return None
        return Gestion(
            id_gestion=_ensure_str(row.get("id_gestion")),
            id_reporte=_ensure_str(row.get("id_reporte")),
            id_sucursal=_ensure_str(row.get("id_sucursal")),
            sucursal=_ensure_str(row.get("sucursal")),
            desvio=_ensure_str(row.get("desvio")),
            severidad=Severidad(_ensure_str(row.get("severidad"), "Baja")),
            responsable=_ensure_str(row.get("responsable")),
            tel_responsable=_ensure_str(row.get("tel_responsable")),
            plazo_fecha=_parse_date(row.get("plazo_fecha")) or date.today(),
            plan_accion=_ensure_str(row.get("plan_accion")),
            estado=GestionState(_ensure_str(row.get("estado"), GestionState.ABIERTA.value)),
            fecha_cierre=_parse_datetime(row.get("fecha_cierre")),
            cerrado_por=row.get("cerrado_por"),
        )

    def _row_to_checklist_perfumeria(self, row: Dict[str, Any]) -> ChecklistPerfumeriaPunto:
        return ChecklistPerfumeriaPunto(
            bloque_id=_ensure_str(row.get("bloque_id")),
            bloque_nombre=_ensure_str(row.get("bloque_nombre")),
            punto_orden=_ensure_int(row.get("punto_orden")),
            tipo_respuesta=_ensure_str(row.get("tipo_respuesta"), "si_no"),
            pregunta=_ensure_str(row.get("pregunta")),
            peso=_ensure_int(row.get("peso"), 5),
            critico=_ensure_bool(row.get("critico"), False),
        )

    def _row_to_resultado_perfumeria(self, row: Optional[Dict[str, Any]]) -> Optional[ResultadoPerfumeria]:
        if not row:
            return None
        return ResultadoPerfumeria(
            id=_ensure_str(row.get("id")),
            id_sesion=_ensure_str(row.get("id_sesion")),
            bloque_id=_ensure_str(row.get("bloque_id")),
            punto_orden=_ensure_int(row.get("punto_orden")),
            pregunta=_ensure_str(row.get("pregunta")),
            respuesta_json=self._json_string(row.get("respuesta_json"), {}),
            tipo_respuesta=_ensure_str(row.get("tipo_respuesta")),
            foto_url=row.get("foto_url"),
            timestamp=_parse_datetime(row.get("timestamp")),
        )

    def _sesion_payload(self, sesion: SesionAuditoria) -> Dict[str, Any]:
        return {
            "id_sesion": sesion.id_sesion,
            "telefono_auditor": sesion.telefono_auditor,
            "sucursal_id": sesion.sucursal_id,
            "estado": sesion.estado,
            "timestamp_inicio": _ensure_datetime(sesion.timestamp_inicio) or _utcnow().isoformat(),
            "timestamp_ultimo_punto": _ensure_datetime(sesion.timestamp_ultimo_punto) or _utcnow().isoformat(),
            "punto_actual": sesion.punto_actual,
            "total_puntos": sesion.total_puntos,
            "hallazgos_json": _ensure_json(sesion.hallazgos_json, []),
            "omitidos_json": _ensure_json(sesion.omitidos_json, []),
            "bloque_actual": sesion.bloque_actual,
            "resultados_json": _ensure_json(sesion.resultados_json, {}),
            "stock_total": sesion.stock_total,
            "stock_actual": sesion.stock_actual,
            "stock_items_json": _ensure_json(sesion.stock_items_json, []),
            "desvios_libres_json": _ensure_json(sesion.desvios_libres_json, []),
            "compromisos_firmados": sesion.compromisos_firmados,
        }

    def _reporte_payload(self, reporte: Reporte) -> Dict[str, Any]:
        return {
            "id": reporte.id,
            "fecha": _ensure_date(reporte.fecha),
            "hora": reporte.hora,
            "cuadrilla": reporte.cuadrilla,
            "auditor": reporte.auditor,
            "id_sucursal": reporte.id_sucursal,
            "sucursal": reporte.sucursal,
            "area": reporte.area,
            "subitem": reporte.subitem,
            "descripcion": reporte.descripcion,
            "severidad": reporte.severidad.value if isinstance(reporte.severidad, Severidad) else str(reporte.severidad),
            "foto_url": reporte.foto_url,
            "creado_por_audio": reporte.creado_por_audio,
            "timestamp": _ensure_datetime(reporte.timestamp) if reporte.timestamp else _utcnow().isoformat(),
        }

    def _gestion_payload(self, gestion: Gestion) -> Dict[str, Any]:
        return {
            "id_gestion": gestion.id_gestion,
            "id_reporte": gestion.id_reporte,
            "id_sucursal": gestion.id_sucursal,
            "sucursal": gestion.sucursal,
            "desvio": gestion.desvio,
            "severidad": gestion.severidad.value if isinstance(gestion.severidad, Severidad) else str(gestion.severidad),
            "responsable": gestion.responsable,
            "tel_responsable": gestion.tel_responsable,
            "plazo_fecha": _ensure_date(gestion.plazo_fecha),
            "plan_accion": gestion.plan_accion,
            "estado": gestion.estado.value if isinstance(gestion.estado, GestionState) else str(gestion.estado),
            "fecha_cierre": _ensure_datetime(gestion.fecha_cierre) if gestion.fecha_cierre else None,
            "cerrado_por": gestion.cerrado_por,
        }

    def _resultado_perfumeria_payload(self, resultado: ResultadoPerfumeria) -> Dict[str, Any]:
        return {
            "id": resultado.id,
            "id_sesion": resultado.id_sesion,
            "bloque_id": resultado.bloque_id,
            "punto_orden": resultado.punto_orden,
            "pregunta": resultado.pregunta,
            "respuesta_json": _ensure_json(resultado.respuesta_json, {}),
            "tipo_respuesta": resultado.tipo_respuesta,
            "foto_url": resultado.foto_url,
            "timestamp": _ensure_datetime(resultado.timestamp) if resultado.timestamp else _utcnow().isoformat(),
        }


def _normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    return "".join(ch for ch in str(phone) if ch.isdigit())


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


def _parse_state(value: Any) -> ConversationState:
    raw = _ensure_str(value, "idle").strip()
    try:
        return ConversationState(raw)
    except ValueError:
        try:
            return ConversationState(raw.lower())
        except ValueError:
            return ConversationState.IDLE

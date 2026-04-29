"""Supabase integration for AuditBot - replaces Google Sheets."""

import json
import logging
from typing import List, Optional, Any, Dict
from datetime import datetime, timedelta, timezone

from supabase import create_client, Client
from config import get_settings
from models import (
    Auditor, Sucursal, AreaSubitem, Conversacion, Pendiente, Reporte,
    Gestion, ConversationState, Severidad, GestionState, ChecklistPunto,
    SesionAuditoria, ItemBloque, ResultadoItem, StockItem, DesvioLibre,
    ChecklistPerfumeriaPunto
)

logger = logging.getLogger(__name__)


class SupabaseManager:
    """Manager for Supabase CRUD operations."""

    _instance = None
    _cache: Dict[str, tuple] = {}  # {table_name: (data, timestamp)}

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super(SupabaseManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Initialize Supabase client."""
        settings = get_settings()
        try:
            if not settings.supabase_url or not settings.supabase_service_key:
                raise ValueError("Supabase credentials not configured")
            self.client: Client = create_client(settings.supabase_url, settings.supabase_service_key)
            logger.info("Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase: {e}")
            raise

    def _is_cache_valid(self, table_name: str) -> bool:
        """Check if cached data is still valid (5 min TTL)."""
        if table_name not in self._cache:
            return False
        data, timestamp = self._cache[table_name]
        ttl = get_settings().cache_ttl
        return (datetime.utcnow() - timestamp).total_seconds() < ttl

    def _set_cache(self, table_name: str, data: List[Dict]) -> None:
        """Cache table data."""
        self._cache[table_name] = (data, datetime.utcnow())

    def _get_cache(self, table_name: str) -> Optional[List[Dict]]:
        """Get cached data if valid."""
        if self._is_cache_valid(table_name):
            return self._cache[table_name][0]
        return None

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normalize phone numbers for matching."""
        if not phone:
            return ""
        return "".join(ch for ch in str(phone) if ch.isdigit())

    @staticmethod
    def _parse_datetime(date_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _parse_conversation_state(value: Optional[str]) -> ConversationState:
        """Parse conversation state with safe fallback."""
        raw = (value or "idle").strip()
        try:
            return ConversationState(raw)
        except ValueError:
            try:
                return ConversationState(raw.lower())
            except ValueError:
                return ConversationState.IDLE

    @staticmethod
    def _first_value(row: Dict[str, Any], *keys: str, default: str = "") -> str:
        """Return first non-empty value from row for given keys."""
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return str(value)
        return default

    # ========== Auditores ==========

    def get_auditor(self, telefono: str) -> Optional[Auditor]:
        """Get auditor by phone number."""
        telefono_norm = self._normalize_phone(telefono)
        try:
            response = self.client.table("auditores").select("*").execute()
            auditores = response.data or []
            for aud in auditores:
                if self._normalize_phone(str(aud.get("telefono", ""))) == telefono_norm:
                    return Auditor(
                        telefono=str(aud.get("telefono", "")),
                        nombre=aud.get("nombre", ""),
                        cuadrilla=aud.get("cuadrilla", ""),
                        activo=aud.get("activo", False),
                    )
            return None
        except Exception as e:
            logger.error(f"Failed to get auditor {telefono}: {e}")
            return None

    def get_all_auditores(self) -> List[Auditor]:
        """Get all auditors."""
        try:
            response = self.client.table("auditores").select("*").execute()
            auditores = [
                Auditor(
                    telefono=str(row.get("telefono", "")),
                    nombre=row.get("nombre", ""),
                    cuadrilla=row.get("cuadrilla", ""),
                    activo=row.get("activo", False),
                )
                for row in response.data or []
            ]
            logger.info(f"Retrieved {len(auditores)} auditors")
            return auditores
        except Exception as e:
            logger.error(f"Failed to get auditors: {e}")
            return []

    # ========== Sucursales ==========

    def get_sucursal(self, id_sucursal: str) -> Optional[Sucursal]:
        """Get facility by ID."""
        try:
            response = self.client.table("sucursales").select("*").eq("id", id_sucursal).execute()
            data = response.data
            if data:
                row = data[0]
                return Sucursal(
                    id=row.get("id", ""),
                    nombre=row.get("nombre", ""),
                    direccion=row.get("direccion", ""),
                    responsable=row.get("responsable", ""),
                    tel_responsable=row.get("tel_responsable", ""),
                    zona=row.get("zona", ""),
                )
            return None
        except Exception as e:
            logger.error(f"Failed to get sucursal {id_sucursal}: {e}")
            return None

    def get_all_sucursales(self) -> List[Sucursal]:
        """Get all facilities (cached)."""
        cached = self._get_cache("sucursales")
        if cached:
            return [Sucursal(**row) for row in cached]

        try:
            response = self.client.table("sucursales").select("*").execute()
            sucursales = [
                Sucursal(
                    id=row.get("id", ""),
                    nombre=row.get("nombre", ""),
                    direccion=row.get("direccion", ""),
                    responsable=row.get("responsable", ""),
                    tel_responsable=row.get("tel_responsable", ""),
                    zona=row.get("zona", ""),
                )
                for row in response.data or []
            ]
            self._set_cache("sucursales", [vars(s) for s in sucursales])
            logger.info(f"Retrieved {len(sucursales)} facilities")
            return sucursales
        except Exception as e:
            logger.error(f"Failed to get facilities: {e}")
            return []

    # ========== Areas ==========

    def get_all_areas(self) -> List[AreaSubitem]:
        """Get all areas with subitems (cached)."""
        cached = self._get_cache("areas")
        if cached:
            return [AreaSubitem(**row) for row in cached]

        try:
            response = self.client.table("areas").select("*").execute()
            areas = [
                AreaSubitem(
                    area=row.get("area", ""),
                    subitems=json.loads(row.get("subitems", "[]")) if isinstance(row.get("subitems"), str) else row.get("subitems", []),
                )
                for row in response.data or []
            ]
            self._set_cache("areas", [vars(a) for a in areas])
            logger.info(f"Retrieved {len(areas)} areas")
            return areas
        except Exception as e:
            logger.error(f"Failed to get areas: {e}")
            return []

    # ========== Conversaciones ==========

    def get_conversacion(self, telefono: str) -> Optional[Conversacion]:
        """Get conversation state by phone."""
        try:
            telefono_norm = self._normalize_phone(telefono)
            response = self.client.table("conversaciones").select("*").execute()

            for row in response.data or []:
                telefono_row = self._first_value(row, "telefono", "telefono_auditor", default="")
                if self._normalize_phone(telefono_row) == telefono_norm:
                    estado_raw = row.get("estado_actual") or row.get("estado") or "idle"
                    id_pendiente = row.get("id_pendiente") or row.get("hallazgo_temp") or ""
                    ultimo_mensaje = row.get("ultimo_mensaje") or ""
                    timestamp_raw = row.get("timestamp") or row.get("timestamp_creacion") or ""

                    return Conversacion(
                        telefono=telefono_row,
                        estado_actual=self._parse_conversation_state(str(estado_raw)),
                        id_pendiente=id_pendiente,
                        ultimo_mensaje=ultimo_mensaje,
                        timestamp=self._parse_datetime(timestamp_raw),
                    )
            return None
        except Exception as e:
            logger.error(f"Failed to get conversation for {telefono}: {e}")
            return None

    def update_conversacion(
        self,
        telefono: str,
        estado: ConversationState,
        id_pendiente: Optional[str] = None,
        ultimo_mensaje: str = "",
    ) -> None:
        """Update conversation state."""
        try:
            telefono_norm = self._normalize_phone(telefono)
            timestamp_now = datetime.utcnow().isoformat()

            # Try to find existing conversation
            response = self.client.table("conversaciones").select("*").execute()
            existing = None
            for row in response.data or []:
                if self._normalize_phone(row.get("telefono", "")) == telefono_norm:
                    existing = row
                    break

            update_data = {
                "telefono": telefono_norm,
                "estado_actual": estado.value,
                "id_pendiente": id_pendiente or "",
                "ultimo_mensaje": ultimo_mensaje,
                "timestamp": timestamp_now,
            }

            if existing:
                # Update existing
                self.client.table("conversaciones").update(update_data).eq(
                    "telefono", existing.get("telefono")
                ).execute()
            else:
                # Insert new
                self.client.table("conversaciones").insert(update_data).execute()

            logger.info(f"Updated conversation for {telefono}: {estado.value}")
        except Exception as e:
            logger.error(f"Failed to update conversation for {telefono}: {e}")
            raise

    # ========== Pendientes ==========

    def create_pendiente(
        self,
        telefono_auditor: str,
        estado: str,
        datos_json: str,
        timeout_minutes: int = 5,
    ) -> str:
        """Create pending record and return ID."""
        try:
            import uuid
            id_temp = str(uuid.uuid4())[:8]
            expira_en = datetime.utcnow() + timedelta(minutes=timeout_minutes)

            self.client.table("pendientes").insert({
                "id_temp": id_temp,
                "telefono_auditor": telefono_auditor,
                "estado": estado,
                "datos_json": datos_json,
                "timestamp_creacion": datetime.utcnow().isoformat(),
                "expira_en": expira_en.isoformat(),
            }).execute()

            logger.info(f"Created pendiente {id_temp} for {telefono_auditor}")
            return id_temp
        except Exception as e:
            logger.error(f"Failed to create pendiente: {e}")
            raise

    def get_pendiente(self, id_temp: str) -> Optional[Pendiente]:
        """Get pending record by ID."""
        try:
            response = self.client.table("pendientes").select("*").eq("id_temp", id_temp).execute()
            data = response.data
            if data:
                row = data[0]
                return Pendiente(
                    id_temp=row.get("id_temp", ""),
                    telefono_auditor=str(row.get("telefono_auditor", "")),
                    estado=row.get("estado", ""),
                    datos_json=row.get("datos_json", ""),
                    timestamp_creacion=self._parse_datetime(row.get("timestamp_creacion")),
                    expira_en=self._parse_datetime(row.get("expira_en")),
                )
            return None
        except Exception as e:
            logger.error(f"Failed to get pendiente {id_temp}: {e}")
            return None

    def delete_pendiente(self, id_temp: str) -> None:
        """Delete pending record."""
        try:
            self.client.table("pendientes").delete().eq("id_temp", id_temp).execute()
            logger.info(f"Deleted pendiente {id_temp}")
        except Exception as e:
            logger.error(f"Failed to delete pendiente {id_temp}: {e}")
            raise

    def get_expired_pendientes(self) -> List[Pendiente]:
        """Get all expired pending records."""
        try:
            now = datetime.utcnow()
            response = self.client.table("pendientes").select("*").execute()
            expired = []

            for row in response.data or []:
                expira_en = self._parse_datetime(row.get("expira_en"))
                if expira_en and expira_en < now:
                    expired.append(Pendiente(
                        id_temp=row.get("id_temp", ""),
                        telefono_auditor=str(row.get("telefono_auditor", "")),
                        estado=row.get("estado", ""),
                        datos_json=row.get("datos_json", ""),
                        timestamp_creacion=self._parse_datetime(row.get("timestamp_creacion")),
                        expira_en=expira_en,
                    ))

            return expired
        except Exception as e:
            logger.error(f"Failed to get expired pendientes: {e}")
            return []

    # ========== Reportes ==========

    def create_reporte(self, reporte: Reporte) -> str:
        """Create audit report."""
        try:
            import uuid
            reporte.id = str(uuid.uuid4())[:12]

            self.client.table("reportes").insert({
                "id": reporte.id,
                "fecha": reporte.fecha,
                "hora": reporte.hora,
                "cuadrilla": reporte.cuadrilla,
                "auditor": reporte.auditor,
                "id_sucursal": reporte.id_sucursal,
                "sucursal": reporte.sucursal,
                "area": reporte.area,
                "subitem": reporte.subitem,
                "descripcion": reporte.descripcion,
                "severidad": reporte.severidad.value,
                "foto_url": reporte.foto_url or "",
                "creado_por_audio": reporte.creado_por_audio,
                "timestamp": datetime.utcnow().isoformat(),
            }).execute()

            logger.info(f"Created reporte {reporte.id}")
            return reporte.id
        except Exception as e:
            logger.error(f"Failed to create reporte: {e}")
            raise

    # ========== Gestion ==========

    def create_gestion(self, gestion: Gestion) -> str:
        """Create action plan (gestión)."""
        try:
            import uuid
            gestion.id_gestion = str(uuid.uuid4())[:12]

            self.client.table("gestiones").insert({
                "id_gestion": gestion.id_gestion,
                "id_reporte": gestion.id_reporte,
                "id_sucursal": gestion.id_sucursal,
                "sucursal": gestion.sucursal,
                "desvio": gestion.desvio,
                "severidad": gestion.severidad.value,
                "responsable": gestion.responsable,
                "tel_responsable": gestion.tel_responsable,
                "plazo_fecha": gestion.plazo_fecha.isoformat(),
                "plan_accion": gestion.plan_accion,
                "estado": gestion.estado.value,
                "fecha_cierre": gestion.fecha_cierre.isoformat() if gestion.fecha_cierre else None,
                "cerrado_por": gestion.cerrado_por or "",
            }).execute()

            logger.info(f"Created gestion {gestion.id_gestion}")
            return gestion.id_gestion
        except Exception as e:
            logger.error(f"Failed to create gestion: {e}")
            raise

    # ========== Checklists ==========

    def get_checklist(self) -> List[ChecklistPunto]:
        """Get guided audit checklist (cached)."""
        cached = self._get_cache("checklist_plantillas")
        if cached:
            return [ChecklistPunto(**row) for row in cached]

        try:
            response = self.client.table("checklist_plantillas").select("*").order(
                "punto_orden"
            ).execute()
            puntos = [
                ChecklistPunto(
                    punto_orden=int(row.get("punto_orden", 0)),
                    area=row.get("area", ""),
                    descripcion=row.get("descripcion", ""),
                    responsable_default=row.get("responsable_default", ""),
                    severidad_default=row.get("severidad_default", "Media"),
                )
                for row in response.data or []
            ]
            self._set_cache("checklist_plantillas", [vars(p) for p in puntos])
            logger.info(f"Retrieved {len(puntos)} checklist points")
            return puntos
        except Exception as e:
            logger.error(f"Failed to get checklist: {e}")
            return []

    def get_checklist_bloques(self) -> Dict[str, List[ItemBloque]]:
        """Get block-based checklist items grouped by block (cached)."""
        cached = self._get_cache("checklist_plantillas_bloques")
        if cached:
            return {
                bloque: [ItemBloque(**item) for item in items]
                for bloque, items in cached.items()
            }

        try:
            response = self.client.table("checklist_plantillas").select("*").execute()
            bloques: Dict[str, List[ItemBloque]] = {}

            for row in response.data or []:
                item = ItemBloque(
                    item_id=row.get("item_id", ""),
                    bloque=row.get("bloque", ""),
                    descripcion=row.get("descripcion", ""),
                    peso=int(row.get("peso", 5)),
                )
                bloque = item.bloque
                if bloque not in bloques:
                    bloques[bloque] = []
                bloques[bloque].append(item)

            self._set_cache(
                "checklist_plantillas_bloques",
                {b: [vars(item) for item in items] for b, items in bloques.items()}
            )
            logger.info(f"Retrieved checklist bloques: {list(bloques.keys())}")
            return bloques
        except Exception as e:
            logger.error(f"Failed to get checklist bloques: {e}")
            return {}

    def get_checklist_perfumeria(self) -> Dict[str, List[ChecklistPerfumeriaPunto]]:
        """Get perfumery audit checklist grouped by block (cached)."""
        cached = self._get_cache("checklist_perfumeria")
        if cached:
            return {
                bloque: [ChecklistPerfumeriaPunto(**item) for item in items]
                for bloque, items in cached.items()
            }

        try:
            response = self.client.table("checklist_perfumeria").select("*").execute()
            bloques: Dict[str, List[ChecklistPerfumeriaPunto]] = {}

            for row in response.data or []:
                critico = str(row.get("critico", "FALSE")).upper() == "TRUE"
                punto = ChecklistPerfumeriaPunto(
                    bloque_id=row.get("bloque_id", ""),
                    bloque_nombre=row.get("bloque_nombre", ""),
                    punto_orden=int(row.get("punto_orden", 0)),
                    tipo_respuesta=row.get("tipo_respuesta", "si_no"),
                    pregunta=row.get("pregunta", ""),
                    peso=int(row.get("peso", 5)),
                    critico=critico,
                )
                bloque_id = punto.bloque_id
                if bloque_id not in bloques:
                    bloques[bloque_id] = []
                bloques[bloque_id].append(punto)

            # Sort by punto_orden
            for bloque_id in bloques:
                bloques[bloque_id].sort(key=lambda p: p.punto_orden)

            self._set_cache(
                "checklist_perfumeria",
                {b: [vars(item) for item in items] for b, items in bloques.items()}
            )
            logger.info(f"Retrieved perfumery checklist bloques: {list(bloques.keys())}")
            return bloques
        except Exception as e:
            logger.error(f"Failed to get perfumery checklist: {e}")
            return {}

    def get_checklist_perfumeria_flat(self) -> List[ChecklistPerfumeriaPunto]:
        """Get all perfumery audit points as flat list."""
        bloques = self.get_checklist_perfumeria()
        puntos = []
        for bloque_list in bloques.values():
            puntos.extend(bloque_list)
        return sorted(puntos, key=lambda p: (p.bloque_id, p.punto_orden))

    # ========== Sesiones de Auditoria ==========

    def create_sesion(self, sesion: SesionAuditoria) -> str:
        """Create guided audit session."""
        try:
            self.client.table("sesiones_auditoria").insert({
                "id_sesion": sesion.id_sesion,
                "telefono_auditor": sesion.telefono_auditor,
                "sucursal_id": sesion.sucursal_id,
                "estado": sesion.estado,
                "timestamp_inicio": sesion.timestamp_inicio,
                "timestamp_ultimo_punto": sesion.timestamp_ultimo_punto,
                "punto_actual": sesion.punto_actual,
                "total_puntos": sesion.total_puntos,
                "hallazgos_json": sesion.hallazgos_json,
                "omitidos_json": sesion.omitidos_json,
                "bloque_actual": sesion.bloque_actual,
                "resultados_json": sesion.resultados_json,
                "stock_total": sesion.stock_total,
                "stock_actual": sesion.stock_actual,
                "stock_items_json": sesion.stock_items_json,
                "desvios_libres_json": sesion.desvios_libres_json,
                "compromisos_firmados": sesion.compromisos_firmados,
            }).execute()

            logger.info(f"Created sesion {sesion.id_sesion}")
            return sesion.id_sesion
        except Exception as e:
            logger.error(f"Failed to create sesion: {e}")
            raise

    def get_sesion(self, id_sesion: str) -> Optional[SesionAuditoria]:
        """Get audit session by ID."""
        try:
            response = self.client.table("sesiones_auditoria").select("*").eq(
                "id_sesion", id_sesion
            ).execute()
            data = response.data
            if data:
                row = data[0]
                return SesionAuditoria(
                    id_sesion=row.get("id_sesion", ""),
                    telefono_auditor=str(row.get("telefono_auditor", "")),
                    sucursal_id=row.get("sucursal_id", ""),
                    estado=row.get("estado", "en_curso"),
                    timestamp_inicio=row.get("timestamp_inicio", ""),
                    timestamp_ultimo_punto=row.get("timestamp_ultimo_punto", ""),
                    punto_actual=int(row.get("punto_actual", 0)),
                    total_puntos=int(row.get("total_puntos", 0)),
                    hallazgos_json=row.get("hallazgos_json", "[]"),
                    omitidos_json=row.get("omitidos_json", "[]"),
                    bloque_actual=row.get("bloque_actual", "A"),
                    resultados_json=row.get("resultados_json", "{}"),
                    stock_total=int(row.get("stock_total", 0)),
                    stock_actual=int(row.get("stock_actual", 0)),
                    stock_items_json=row.get("stock_items_json", "[]"),
                    desvios_libres_json=row.get("desvios_libres_json", "[]"),
                    compromisos_firmados=row.get("compromisos_firmados", ""),
                )
            return None
        except Exception as e:
            logger.error(f"Failed to get sesion {id_sesion}: {e}")
            return None

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
        """Update audit session."""
        try:
            self.client.table("sesiones_auditoria").update({
                "estado": estado,
                "timestamp_ultimo_punto": timestamp_ultimo_punto,
                "bloque_actual": bloque_actual,
                "resultados_json": resultados_json,
                "stock_items_json": stock_items_json,
                "desvios_libres_json": desvios_libres_json,
                "stock_total": stock_total,
                "stock_actual": stock_actual,
                "punto_actual": punto_actual,
                "hallazgos_json": hallazgos_json,
                "omitidos_json": omitidos_json,
            }).eq("id_sesion", id_sesion).execute()

            logger.info(f"Updated sesion {id_sesion}")
        except Exception as e:
            logger.error(f"Failed to update sesion {id_sesion}: {e}")
            raise

    def get_sesiones_activas_expiradas(self, timeout_min: int = 15) -> List[SesionAuditoria]:
        """Get active sessions that have exceeded timeout."""
        try:
            response = self.client.table("sesiones_auditoria").select("*").execute()
            expiradas = []
            now = datetime.utcnow()

            active_states = {
                "en_curso", "en_bloque", "confirmando_bloque", "stock_loop",
                "en_stock_item", "desvio_libre", "compromisos",
                "esperando_confirmacion", "esperando_edicion",
            }

            for row in response.data or []:
                if row.get("estado") in active_states:
                    timestamp_str = row.get("timestamp_ultimo_punto", "")
                    ts = self._parse_datetime(timestamp_str)
                    if not ts:
                        continue

                    if ts.tzinfo is not None:
                        elapsed_seconds = (now - ts.astimezone(timezone.utc)).total_seconds()
                    else:
                        elapsed_seconds = (now - ts).total_seconds()

                    if elapsed_seconds > timeout_min * 60:
                        expiradas.append(SesionAuditoria(
                            id_sesion=row.get("id_sesion", ""),
                            telefono_auditor=str(row.get("telefono_auditor", "")),
                            sucursal_id=row.get("sucursal_id", ""),
                            estado=row.get("estado", "en_curso"),
                            timestamp_inicio=row.get("timestamp_inicio", ""),
                            timestamp_ultimo_punto=timestamp_str,
                            punto_actual=int(row.get("punto_actual", 0)),
                            total_puntos=int(row.get("total_puntos", 0)),
                            hallazgos_json=row.get("hallazgos_json", "[]"),
                            omitidos_json=row.get("omitidos_json", "[]"),
                            bloque_actual=row.get("bloque_actual", "A"),
                            resultados_json=row.get("resultados_json", "{}"),
                            stock_total=int(row.get("stock_total", 0)),
                            stock_actual=int(row.get("stock_actual", 0)),
                            stock_items_json=row.get("stock_items_json", "[]"),
                            desvios_libres_json=row.get("desvios_libres_json", "[]"),
                            compromisos_firmados=row.get("compromisos_firmados", ""),
                        ))

            return expiradas
        except Exception as e:
            logger.error(f"Failed to get expired sesiones: {e}")
            return []

    # ========== Block-based Audit Methods ==========

    def save_bloque_resultado(
        self,
        auditoria_id: str,
        bloque_id: str,
        sucursal_id: str,
        auditor_nombre: str,
        resultados: List[ResultadoItem],
    ) -> None:
        """Save block results and create Reportes + Gestiones for deviations."""
        try:
            from datetime import date
            sesion = self.get_sesion(auditoria_id)
            if not sesion:
                logger.error(f"Sesion {auditoria_id} not found")
                return

            sucursal = self.get_sucursal(sucursal_id)
            sucursal_nombre = sucursal.nombre if sucursal else sucursal_id

            hoy = date.today().isoformat()
            hora = datetime.utcnow().strftime("%H:%M")

            for resultado in resultados:
                if resultado.tiene_desvio and resultado.descripcion_desvio:
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

                    plazo = date.today() + timedelta(days=7)
                    gestion = Gestion(
                        id_gestion="",
                        id_reporte=reporte_id,
                        id_sucursal=sucursal_id,
                        sucursal=sucursal_nombre,
                        desvio=resultado.descripcion_desvio,
                        severidad=severidad,
                        responsable=sucursal.responsable if sucursal else "",
                        tel_responsable=sucursal.tel_responsable if sucursal else "",
                        plazo_fecha=plazo,
                        plan_accion="",
                        estado=GestionState.ABIERTA,
                    )
                    self.create_gestion(gestion)

            logger.info(f"Saved bloque {bloque_id} results for sesion {auditoria_id}")
        except Exception as e:
            logger.error(f"Failed to save bloque resultado: {e}")
            raise

    def save_stock_item(
        self,
        auditoria_id: str,
        sucursal_id: str,
        auditor: str,
        item: StockItem,
    ) -> None:
        """Save stock verification item."""
        try:
            diferencia = item.stock_fisico - item.stock_sistema
            alerta = "SI" if abs(diferencia) > 0 else "NO"

            self.client.table("control_stock").insert({
                "auditoria_id": auditoria_id,
                "sucursal_id": sucursal_id,
                "fecha": datetime.utcnow().strftime("%Y-%m-%d"),
                "auditor": auditor,
                "nombre": item.nombre,
                "stock_fisico": item.stock_fisico,
                "stock_sistema": item.stock_sistema,
                "diferencia": diferencia,
                "alerta": alerta,
            }).execute()

            logger.info(f"Saved stock item {item.nombre} for sesion {auditoria_id}")
        except Exception as e:
            logger.error(f"Failed to save stock item: {e}")
            raise

    def save_desvio_libre(
        self,
        auditoria_id: str,
        sucursal_id: str,
        auditor_nombre: str,
        desvio: DesvioLibre,
    ) -> str:
        """Create Reporte for free-form deviation, return reporte_id."""
        try:
            from datetime import date
            sucursal = self.get_sucursal(sucursal_id)
            sucursal_nombre = sucursal.nombre if sucursal else sucursal_id

            hoy = date.today().isoformat()
            hora = datetime.utcnow().strftime("%H:%M")

            severidad = Severidad(desvio.severidad or "Baja")
            reporte = Reporte(
                id="",
                fecha=hoy,
                hora=hora,
                cuadrilla="",
                auditor=auditor_nombre,
                id_sucursal=sucursal_id,
                sucursal=sucursal_nombre,
                area=desvio.area_estimada or "Observación libre",
                subitem="",
                descripcion=desvio.descripcion,
                severidad=severidad,
                creado_por_audio=False,
            )
            reporte_id = self.create_reporte(reporte)

            plazo = date.today() + timedelta(days=7)
            gestion = Gestion(
                id_gestion="",
                id_reporte=reporte_id,
                id_sucursal=sucursal_id,
                sucursal=sucursal_nombre,
                desvio=desvio.descripcion,
                severidad=severidad,
                responsable=sucursal.responsable if sucursal else "",
                tel_responsable=sucursal.tel_responsable if sucursal else "",
                plazo_fecha=plazo,
                plan_accion="",
                estado=GestionState.ABIERTA,
            )
            self.create_gestion(gestion)

            logger.info(f"Created reporte {reporte_id} for desvio libre")
            return reporte_id
        except Exception as e:
            logger.error(f"Failed to save desvio libre: {e}")
            raise

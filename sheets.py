"""Google Sheets integration for AuditBot."""

import json
import logging
from typing import List, Optional, Any, Dict
from datetime import datetime, timedelta
import base64

import gspread
from gspread.exceptions import GSpreadException

from config import get_settings
from models import (
    Auditor, Sucursal, AreaSubitem, Conversacion, Pendiente, Reporte,
    Gestion, ConversationState, Severidad, GestionState, ChecklistPunto,
    SesionAuditoria, ItemBloque, ResultadoItem, StockItem, DesvioLibre
)

logger = logging.getLogger(__name__)


class SheetsManager:
    """Manager for Google Sheets CRUD operations."""

    _instance = None
    _cache: Dict[str, tuple] = {}  # {sheet_name: (data, timestamp)}

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super(SheetsManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Initialize Google Sheets client."""
        settings = get_settings()
        try:
            service_account_json = base64.b64decode(
                settings.google_service_account_json
            ).decode("utf-8")
            creds_dict = json.loads(service_account_json)
            self.client = gspread.service_account_from_dict(creds_dict)
            self.sheet_id = settings.google_sheets_id
            self.workbook = self.client.open_by_key(self.sheet_id)
            logger.info("Google Sheets client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
            raise

    def _get_sheet(self, sheet_name: str) -> gspread.Worksheet:
        """Get worksheet by name."""
        try:
            return self.workbook.worksheet(sheet_name)
        except GSpreadException as e:
            logger.error(f"Failed to get sheet '{sheet_name}': {e}")
            raise

    def _is_cache_valid(self, sheet_name: str) -> bool:
        """Check if cached data is still valid (5 min TTL)."""
        if sheet_name not in self._cache:
            return False
        data, timestamp = self._cache[sheet_name]
        ttl = get_settings().cache_ttl
        return (datetime.utcnow() - timestamp).total_seconds() < ttl

    def _set_cache(self, sheet_name: str, data: List[Dict]) -> None:
        """Cache sheet data."""
        self._cache[sheet_name] = (data, datetime.utcnow())

    def _get_cache(self, sheet_name: str) -> Optional[List[Dict]]:
        """Get cached data if valid."""
        if self._is_cache_valid(sheet_name):
            return self._cache[sheet_name][0]
        return None

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normalize phone numbers for matching across data sources."""
        if not phone:
            return ""
        return "".join(ch for ch in str(phone) if ch.isdigit())

    # ========== Maestro_Auditores ==========

    def get_auditor(self, telefono: str) -> Optional[Auditor]:
        """Get auditor by phone number."""
        telefono_norm = self._normalize_phone(telefono)
        auditores = self.get_all_auditores()
        for aud in auditores:
            if self._normalize_phone(aud.telefono) == telefono_norm:
                return aud
        return None

    def get_all_auditores(self) -> List[Auditor]:
        """Get all auditors."""
        try:
            sheet = self._get_sheet("Maestro_Auditores")
            rows = sheet.get_all_records()
            auditores = [
                Auditor(
                    telefono=str(row.get("Telefono", "")),
                    nombre=row.get("Nombre", ""),
                    cuadrilla=row.get("Cuadrilla", ""),
                    activo=row.get("Activo", "").lower() == "true",
                )
                for row in rows
            ]
            logger.info(f"Retrieved {len(auditores)} auditors")
            return auditores
        except Exception as e:
            logger.error(f"Failed to get auditors: {e}")
            raise

    # ========== Maestro_Sucursales ==========

    def get_sucursal(self, id_sucursal: str) -> Optional[Sucursal]:
        """Get facility by ID."""
        sucursales = self.get_all_sucursales()
        for suc in sucursales:
            if suc.id == id_sucursal:
                return suc
        return None

    def get_all_sucursales(self) -> List[Sucursal]:
        """Get all facilities (cached)."""
        cached = self._get_cache("Maestro_Sucursales")
        if cached:
            return [Sucursal(**row) for row in cached]

        try:
            sheet = self._get_sheet("Maestro_Sucursales")
            rows = sheet.get_all_records()
            sucursales = [
                Sucursal(
                    id=row.get("ID", ""),
                    nombre=row.get("Nombre", ""),
                    direccion=row.get("Dirección", ""),
                    responsable=row.get("Responsable", ""),
                    tel_responsable=row.get("Tel_Responsable", ""),
                    zona=row.get("Zona", ""),
                )
                for row in rows
            ]
            self._set_cache("Maestro_Sucursales", [vars(s) for s in sucursales])
            logger.info(f"Retrieved {len(sucursales)} facilities")
            return sucursales
        except Exception as e:
            logger.error(f"Failed to get facilities: {e}")
            raise

    # ========== Catalogo_Areas ==========

    def get_all_areas(self) -> List[AreaSubitem]:
        """Get all areas with subitems (cached)."""
        cached = self._get_cache("Catalogo_Areas")
        if cached:
            return [AreaSubitem(**row) for row in cached]

        try:
            sheet = self._get_sheet("Catalogo_Areas")
            rows = sheet.get_all_records()
            areas = [
                AreaSubitem(
                    area=row.get("Area", ""),
                    subitems=json.loads(row.get("SubItems", "[]")),
                )
                for row in rows
            ]
            self._set_cache("Catalogo_Areas", [vars(a) for a in areas])
            logger.info(f"Retrieved {len(areas)} areas")
            return areas
        except Exception as e:
            logger.error(f"Failed to get areas: {e}")
            raise

    # ========== Conversaciones ==========

    def get_conversacion(self, telefono: str) -> Optional[Conversacion]:
        """Get conversation state by phone."""
        try:
            sheet = self._get_sheet("Conversaciones")
            rows = sheet.get_all_records()
            telefono_norm = self._normalize_phone(telefono)
            for row in rows:
                telefono_row = self._first_value(
                    row,
                    "Telefono",
                    "Telefono_Auditor",
                )
                if self._normalize_phone(telefono_row) == telefono_norm:
                    estado_raw = (
                        self._first_value(
                            row,
                            "Estado_actual",
                            "estado_actual",
                            "Estado",
                            "estado",
                        )
                        or "idle"
                    )
                    id_pendiente = self._first_value(
                        row,
                        "ID_pendiente",
                        "id_pendiente",
                        "ID_Pendiente",
                        "Hallazgo_Temp",
                    )
                    ultimo_mensaje = self._first_value(
                        row,
                        "Ultimo_mensaje",
                        "ultimo_mensaje",
                        "Hallazgo_Temp",
                        default="",
                    )
                    timestamp_raw = self._first_value(
                        row,
                        "Timestamp",
                        "timestamp",
                        "timestamp_ultimo",
                    )
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
            raise

    def update_conversacion(
        self,
        telefono: str,
        estado: ConversationState,
        id_pendiente: Optional[str] = None,
        ultimo_mensaje: str = "",
    ) -> None:
        """Update conversation state."""
        try:
            sheet = self._get_sheet("Conversaciones")
            rows = sheet.get_all_records()
            headers = sheet.row_values(1)
            row_idx = None
            telefono_norm = self._normalize_phone(telefono)
            timestamp_now = datetime.utcnow().isoformat()

            for idx, row in enumerate(rows):
                telefono_row = self._first_value(
                    row,
                    "Telefono",
                    "Telefono_Auditor",
                )
                if self._normalize_phone(telefono_row) == telefono_norm:
                    row_idx = idx + 2  # +1 for header, +1 for 1-based indexing
                    break

            def value_for_header(header: str) -> str:
                if header in {"Telefono", "Telefono_Auditor"}:
                    return telefono_norm
                if header in {"Estado_actual", "estado_actual", "Estado", "estado"}:
                    return estado.value
                if header in {"ID_pendiente", "id_pendiente", "ID_Pendiente"}:
                    return id_pendiente or ""
                if header in {"Hallazgo_Temp"}:
                    return id_pendiente or ""
                if header in {"Ultimo_mensaje", "ultimo_mensaje"}:
                    return ultimo_mensaje
                if header in {"Timestamp", "timestamp", "timestamp_ultimo", "Timestamp_creacion", "Timeout_At", "Expira_en"}:
                    return timestamp_now
                return ""

            if row_idx is None:
                # Create new row honoring the current sheet schema.
                if headers:
                    sheet.append_row([value_for_header(header.strip()) for header in headers])
                else:
                    sheet.append_row([
                        telefono_norm,
                        estado.value,
                        id_pendiente or "",
                        ultimo_mensaje,
                        timestamp_now,
                    ])
            else:
                # Update existing row honoring whichever schema is present.
                header_to_col = {header.strip(): idx + 1 for idx, header in enumerate(headers) if header.strip()}

                for header_name in ("Telefono", "Telefono_Auditor"):
                    col = header_to_col.get(header_name)
                    if col:
                        sheet.update_cell(row_idx, col, telefono_norm)
                        break

                for header_name in ("Estado_actual", "estado_actual", "Estado", "estado"):
                    col = header_to_col.get(header_name)
                    if col:
                        sheet.update_cell(row_idx, col, estado.value)
                        break

                for header_name in ("ID_pendiente", "id_pendiente", "ID_Pendiente", "Hallazgo_Temp"):
                    col = header_to_col.get(header_name)
                    if col:
                        sheet.update_cell(row_idx, col, id_pendiente or "")
                        break

                for header_name in ("Ultimo_mensaje", "ultimo_mensaje"):
                    col = header_to_col.get(header_name)
                    if col:
                        sheet.update_cell(row_idx, col, ultimo_mensaje)
                        break

                for header_name in ("Timestamp", "timestamp", "timestamp_ultimo", "Timestamp_creacion", "Timeout_At", "Expira_en"):
                    col = header_to_col.get(header_name)
                    if col:
                        sheet.update_cell(row_idx, col, timestamp_now)
                        break

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

            sheet = self._get_sheet("Pendientes")
            sheet.append_row([
                id_temp,
                telefono_auditor,
                estado,
                datos_json,
                datetime.utcnow().isoformat(),
                expira_en.isoformat(),
            ])

            logger.info(f"Created pendiente {id_temp} for {telefono_auditor}")
            return id_temp
        except Exception as e:
            logger.error(f"Failed to create pendiente: {e}")
            raise

    def get_pendiente(self, id_temp: str) -> Optional[Pendiente]:
        """Get pending record by ID."""
        try:
            sheet = self._get_sheet("Pendientes")
            rows = sheet.get_all_records()
            for row in rows:
                if row.get("ID_temp") == id_temp:
                    return Pendiente(
                        id_temp=row.get("ID_temp", ""),
                        telefono_auditor=str(row.get("Telefono_Auditor", "")),
                        estado=row.get("Estado", ""),
                        datos_json=row.get("Datos_JSON", ""),
                        timestamp_creacion=self._parse_datetime(row.get("Timestamp_creacion")),
                        expira_en=self._parse_datetime(row.get("Expira_en")),
                    )
            return None
        except Exception as e:
            logger.error(f"Failed to get pendiente {id_temp}: {e}")
            raise

    def delete_pendiente(self, id_temp: str) -> None:
        """Delete pending record."""
        try:
            sheet = self._get_sheet("Pendientes")
            rows = sheet.get_all_records()
            for idx, row in enumerate(rows):
                if row.get("ID_temp") == id_temp:
                    sheet.delete_rows(idx + 2, 1)  # +2 for header and 1-based indexing
                    logger.info(f"Deleted pendiente {id_temp}")
                    return
        except Exception as e:
            logger.error(f"Failed to delete pendiente {id_temp}: {e}")
            raise

    def get_expired_pendientes(self) -> List[Pendiente]:
        """Get all expired pending records."""
        try:
            sheet = self._get_sheet("Pendientes")
            rows = sheet.get_all_records()
            expired = []
            now = datetime.utcnow()

            for row in rows:
                expira_en = self._parse_datetime(row.get("Expira_en"))
                if expira_en and expira_en < now:
                    expired.append(Pendiente(
                        id_temp=row.get("ID_temp", ""),
                        telefono_auditor=str(row.get("Telefono_Auditor", "")),
                        estado=row.get("Estado", ""),
                        datos_json=row.get("Datos_JSON", ""),
                        timestamp_creacion=self._parse_datetime(row.get("Timestamp_creacion")),
                        expira_en=expira_en,
                    ))

            return expired
        except Exception as e:
            logger.error(f"Failed to get expired pendientes: {e}")
            raise

    # ========== Reportes ==========

    def create_reporte(self, reporte: Reporte) -> str:
        """Create audit report."""
        try:
            import uuid
            reporte.id = str(uuid.uuid4())[:12]

            sheet = self._get_sheet("Reportes")
            sheet.append_row([
                reporte.id,
                reporte.fecha,
                reporte.hora,
                reporte.cuadrilla,
                reporte.auditor,
                reporte.id_sucursal,
                reporte.sucursal,
                reporte.area,
                reporte.subitem,
                reporte.descripcion,
                reporte.severidad.value,
                reporte.foto_url or "",
                str(reporte.creado_por_audio),
                datetime.utcnow().isoformat(),
            ])

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

            sheet = self._get_sheet("Gestion")
            sheet.append_row([
                gestion.id_gestion,
                gestion.id_reporte,
                gestion.id_sucursal,
                gestion.sucursal,
                gestion.desvio,
                gestion.severidad.value,
                gestion.responsable,
                gestion.tel_responsable,
                gestion.plazo_fecha.isoformat(),
                gestion.plan_accion,
                gestion.estado.value,
                gestion.fecha_cierre.isoformat() if gestion.fecha_cierre else "",
                gestion.cerrado_por or "",
            ])

            logger.info(f"Created gestion {gestion.id_gestion}")
            return gestion.id_gestion
        except Exception as e:
            logger.error(f"Failed to create gestion: {e}")
            raise

    # ========== Checklist_Plantillas ==========

    def get_checklist(self) -> List[ChecklistPunto]:
        """Get guided audit checklist (global, cached)."""
        cached = self._get_cache("Checklist_Plantillas")
        if cached:
            return [ChecklistPunto(**row) for row in cached]

        try:
            sheet = self._get_sheet("Checklist_Plantillas")
            rows = sheet.get_all_records()
            puntos = [
                ChecklistPunto(
                    punto_orden=int(row.get("punto_orden", 0)),
                    area=row.get("area", ""),
                    descripcion=row.get("descripcion", ""),
                    responsable_default=row.get("responsable_default", ""),
                    severidad_default=row.get("severidad_default", "Media"),
                )
                for row in rows
            ]
            puntos.sort(key=lambda p: p.punto_orden)
            self._set_cache("Checklist_Plantillas", [vars(p) for p in puntos])
            logger.info(f"Retrieved {len(puntos)} checklist points")
            return puntos
        except Exception as e:
            logger.error(f"Failed to get checklist: {e}")
            raise

    def get_checklist_bloques(self) -> Dict[str, List[ItemBloque]]:
        """Get block-based checklist items grouped by block (cached 5 min)."""
        cached = self._get_cache("Checklist_Plantillas_Bloques")
        if cached:
            return {
                bloque: [ItemBloque(**item) for item in items]
                for bloque, items in cached.items()
            }

        try:
            sheet = self._get_sheet("Checklist_Plantillas")
            rows = sheet.get_all_records()
            bloques: Dict[str, List[ItemBloque]] = {}

            for row in rows:
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
                "Checklist_Plantillas_Bloques",
                {b: [vars(item) for item in items] for b, items in bloques.items()}
            )
            logger.info(f"Retrieved checklist bloques: {list(bloques.keys())}")
            return bloques
        except Exception as e:
            logger.error(f"Failed to get checklist bloques: {e}")
            raise

    # ========== Sesiones_Auditoria ==========

    def create_sesion(self, sesion: SesionAuditoria) -> str:
        """Create guided audit session."""
        try:
            sheet = self._get_sheet("Sesiones_Auditoria")
            sheet.append_row([
                sesion.id_sesion,
                sesion.telefono_auditor,
                sesion.sucursal_id,
                sesion.estado,
                sesion.timestamp_inicio,
                sesion.timestamp_ultimo_punto,
                sesion.punto_actual,
                sesion.total_puntos,
                sesion.hallazgos_json,
                sesion.omitidos_json,
                sesion.bloque_actual,
                sesion.resultados_json,
                sesion.stock_total,
                sesion.stock_actual,
                sesion.stock_items_json,
                sesion.desvios_libres_json,
                sesion.compromisos_firmados,
            ])
            logger.info(f"Created sesion {sesion.id_sesion}")
            return sesion.id_sesion
        except Exception as e:
            logger.error(f"Failed to create sesion: {e}")
            raise

    def get_sesion(self, id_sesion: str) -> Optional[SesionAuditoria]:
        """Get audit session by ID."""
        try:
            sheet = self._get_sheet("Sesiones_Auditoria")
            rows = sheet.get_all_records()
            for row in rows:
                if row.get("id_sesion") == id_sesion:
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
            raise

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
            sheet = self._get_sheet("Sesiones_Auditoria")
            rows = sheet.get_all_records()
            row_idx = None

            for idx, row in enumerate(rows):
                if row.get("id_sesion") == id_sesion:
                    row_idx = idx + 2
                    break

            if row_idx is not None:
                sheet.update_cell(row_idx, 4, estado)
                sheet.update_cell(row_idx, 5, timestamp_ultimo_punto)
                sheet.update_cell(row_idx, 7, punto_actual)
                sheet.update_cell(row_idx, 9, hallazgos_json)
                sheet.update_cell(row_idx, 10, omitidos_json)
                sheet.update_cell(row_idx, 11, bloque_actual)
                sheet.update_cell(row_idx, 12, resultados_json)
                sheet.update_cell(row_idx, 13, stock_total)
                sheet.update_cell(row_idx, 14, stock_actual)
                sheet.update_cell(row_idx, 15, stock_items_json)
                sheet.update_cell(row_idx, 16, desvios_libres_json)
                logger.info(f"Updated sesion {id_sesion}")
            else:
                logger.warning(f"Sesion {id_sesion} not found for update")
        except Exception as e:
            logger.error(f"Failed to update sesion {id_sesion}: {e}")
            raise

    def get_sesiones_activas_expiradas(self, timeout_min: int = 15) -> List[SesionAuditoria]:
        """Get active sessions that have exceeded timeout."""
        try:
            sheet = self._get_sheet("Sesiones_Auditoria")
            rows = sheet.get_all_records()
            expiradas = []
            now = datetime.utcnow()

            active_states = {
                "en_curso",
                "en_bloque",
                "confirmando_bloque",
                "stock_loop",
                "en_stock_item",
                "desvio_libre",
                "compromisos",
                "esperando_confirmacion",
                "esperando_edicion",
            }

            for row in rows:
                if row.get("estado") in active_states:
                    timestamp_str = row.get("timestamp_ultimo_punto", "")
                    ts = self._parse_datetime(timestamp_str)
                    if ts and (now - ts).total_seconds() > timeout_min * 60:
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
        except GSpreadException as e:
            logger.warning(f"Sesiones_Auditoria sheet is missing or unavailable: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to get expired sesiones: {e}")
            raise

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
        """Save stock verification item to Control_Stock sheet."""
        try:
            sheet = self._get_sheet("Control_Stock")
            diferencia = item.stock_fisico - item.stock_sistema
            alerta = "SI" if abs(diferencia) > 0 else "NO"

            sheet.append_row([
                "",  # id (will be auto-generated)
                auditoria_id,
                sucursal_id,
                datetime.utcnow().strftime("%Y-%m-%d"),
                auditor,
                item.nombre,
                item.stock_fisico,
                item.stock_sistema,
                diferencia,
                alerta,
            ])

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

    # ========== Utilities ==========

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
        """Parse a conversation state with safe fallback."""
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
        """Return the first non-empty value from a row for the given keys."""
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return str(value)
        return default

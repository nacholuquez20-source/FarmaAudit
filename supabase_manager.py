"""Supabase integration for AuditBot - replaces Google Sheets."""

import json
import logging
import uuid
from typing import List, Optional, Any, Dict
from datetime import datetime, timedelta, timezone

from supabase import create_client, Client
from config import get_settings
from models import (
    Auditor, Sucursal, AreaSubitem, Conversacion, Pendiente, Reporte,
    Gestion, ConversationState, Severidad, GestionState, ChecklistPunto,
    SesionAuditoria, ItemBloque, ResultadoItem, StockItem, DesvioLibre,
    ChecklistPerfumeriaPunto, RespuestaPregunta, RespuestaPreguntaAuditLog
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
            logger.debug(f"get_auditor: searching for {telefono_norm}, total auditores in DB: {len(auditores)}")
            for aud in auditores:
                aud_phone_norm = self._normalize_phone(str(aud.get("telefono", "")))
                logger.debug(f"get_auditor: comparing {telefono_norm} == {aud_phone_norm} (stored: {aud.get('telefono')}, nombre: {aud.get('nombre')})")
                if aud_phone_norm == telefono_norm:
                    logger.info(f"get_auditor: MATCH found for {telefono_norm}")
                    return Auditor(
                        telefono=str(aud.get("telefono", "")),
                        nombre=aud.get("nombre", ""),
                        cuadrilla=aud.get("cuadrilla", ""),
                        activo=aud.get("activo", False),
                    )
            logger.warning(f"get_auditor: NO MATCH found for {telefono_norm}")
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
        id_respuesta_actual: Optional[str] = None,
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
            if id_respuesta_actual is not None:
                update_data["id_respuesta_actual"] = id_respuesta_actual or None

            def persist(data: Dict[str, Any]) -> None:
                if existing:
                    self.client.table("conversaciones").update(data).eq(
                        "telefono", existing.get("telefono")
                    ).execute()
                else:
                    self.client.table("conversaciones").insert(data).execute()

            try:
                persist(update_data)
            except Exception as write_error:
                if id_respuesta_actual is not None and "id_respuesta_actual" in str(write_error):
                    fallback_data = dict(update_data)
                    fallback_data.pop("id_respuesta_actual", None)
                    persist(fallback_data)
                    logger.warning(
                        "conversaciones.id_respuesta_actual is unavailable; "
                        "collector state was saved without the optional pointer."
                    )
                else:
                    raise

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
            now_utc = datetime.now(timezone.utc)
            now_naive = datetime.utcnow()
            response = self.client.table("pendientes").select("*").execute()
            expired = []

            for row in response.data or []:
                expira_en = self._parse_datetime(row.get("expira_en"))
                if not expira_en:
                    continue
                now = now_utc if expira_en.tzinfo is not None else now_naive
                if expira_en < now:
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

            self.client.table("gestion").insert({
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

    def save_perfumeria_desvio(
        self,
        auditoria_id: str,
        sucursal_id: str,
        auditor_nombre: str,
        bloque_nombre: str,
        descripcion: str,
        severidad: str,
        evidencia: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Create Reporte + Gestion for an extracted perfumery finding."""
        try:
            from datetime import date

            descripcion_limpia = (descripcion or "").strip()
            if not descripcion_limpia:
                raise ValueError("descripcion is required")

            try:
                severidad_enum = Severidad(severidad or "Media")
            except ValueError:
                severidad_enum = Severidad.MEDIA

            sucursal = self.get_sucursal(sucursal_id)
            sucursal_nombre = sucursal.nombre if sucursal else sucursal_id
            hoy = date.today().isoformat()
            hora = datetime.utcnow().strftime("%H:%M")
            evidencia_path = str(evidencia.get("path") or "") if evidencia else ""
            evidencia_url = f"storage://auditoria-respuestas/{evidencia_path}" if evidencia_path else ""

            reporte = Reporte(
                id="",
                fecha=hoy,
                hora=hora,
                cuadrilla="",
                auditor=auditor_nombre,
                id_sucursal=sucursal_id,
                sucursal=sucursal_nombre,
                area=f"Perfumeria - {bloque_nombre}",
                subitem="",
                descripcion=descripcion_limpia,
                severidad=severidad_enum,
                foto_url=evidencia_url,
                creado_por_audio=False,
            )
            reporte_id = self.create_reporte(reporte)

            plazo = date.today() + timedelta(days=7)
            gestion = Gestion(
                id_gestion="",
                id_reporte=reporte_id,
                id_sucursal=sucursal_id,
                sucursal=sucursal_nombre,
                desvio=descripcion_limpia,
                severidad=severidad_enum,
                responsable=sucursal.responsable if sucursal else "",
                tel_responsable=sucursal.tel_responsable if sucursal else "",
                plazo_fecha=plazo,
                plan_accion="[Por definir por el responsable]",
                estado=GestionState.ABIERTA,
            )
            gestion_id = self.create_gestion(gestion)

            if evidencia_path:
                self.save_encargado_evento(
                    id_gestion=gestion_id,
                    tipo="evidencia",
                    contenido="Evidencia enviada por WhatsApp durante la auditoria.",
                    actor_nombre=auditor_nombre,
                    metadata={
                        "origen": "auditor",
                        "foto_path": evidencia_path,
                        "bucket": "auditoria-respuestas",
                        "mime_type": evidencia.get("mime_type", ""),
                        "canal": "whatsapp",
                    },
                )

            logger.info(f"Created perfumeria desvio reporte={reporte_id} gestion={gestion_id} sesion={auditoria_id}")
            return {"id_reporte": reporte_id, "id_gestion": gestion_id}
        except Exception as e:
            logger.error(f"Failed to save perfumeria desvio for sesion {auditoria_id}: {e}")
            raise

    def save_perfumeria_desvio_borrador(
        self,
        auditoria_id: str,
        sucursal_id: str,
        auditor_nombre: str,
        bloque_id: str,
        bloque_nombre: str,
        descripcion: str,
        severidad: str,
        id_respuesta: Optional[str] = None,
        respuesta_consolidada: str = "",
        evidencia: Optional[Dict[str, Any]] = None,
        confianza: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Create a WhatsApp finding draft for frontend review."""
        try:
            descripcion_limpia = (descripcion or "").strip()
            if not descripcion_limpia:
                raise ValueError("descripcion is required")

            severidad_limpia = severidad if severidad in {"Alta", "Media", "Baja"} else "Media"
            sucursal = self.get_sucursal(sucursal_id)
            sucursal_nombre = sucursal.nombre if sucursal else sucursal_id
            evidencia_items: List[Dict[str, Any]] = []
            if evidencia:
                evidencia_items.append({
                    "tipo": evidencia.get("tipo") or "image",
                    "path": evidencia.get("path") or "",
                    "url": evidencia.get("url") or "",
                    "mime_type": evidencia.get("mime_type") or "",
                    "media_id": evidencia.get("media_id") or "",
                    "bucket": "auditoria-respuestas",
                })

            response = self.client.table("desvios_borrador").insert({
                "id_respuesta": id_respuesta,
                "id_sesion": auditoria_id,
                "id_sucursal": sucursal_id,
                "sucursal": sucursal_nombre,
                "bloque_id": bloque_id,
                "bloque_nombre": bloque_nombre,
                "descripcion": descripcion_limpia,
                "severidad_sugerida": severidad_limpia,
                "estado": "pendiente",
                "evidencias_json": evidencia_items,
                "respuesta_consolidada": respuesta_consolidada or descripcion_limpia,
                "auditor_nombre": auditor_nombre,
                "confianza": confianza,
                "metadata_json": metadata or {},
            }).execute()

            draft = (response.data or [{}])[0]
            draft_id = str(draft.get("id") or "")
            logger.info(f"Created desvio borrador {draft_id} sesion={auditoria_id}")
            return {"id_borrador": draft_id, "estado": "pendiente"}
        except Exception as e:
            message = str(e).lower()
            if "desvios_borrador" in message or "could not find the table" in message or "42p01" in message:
                logger.warning("desvios_borrador table missing; falling back to direct gestion persistence")
                persisted = self.save_perfumeria_desvio(
                    auditoria_id=auditoria_id,
                    sucursal_id=sucursal_id,
                    auditor_nombre=auditor_nombre,
                    bloque_nombre=bloque_nombre,
                    descripcion=descripcion,
                    severidad=severidad,
                    evidencia=evidencia,
                )
                return {**persisted, "estado": "converted_fallback"}
            logger.error(f"Failed to save desvio borrador for sesion {auditoria_id}: {e}")
            raise

    def get_desvio_borrador(self, draft_id: str) -> Optional[Dict[str, Any]]:
        """Fetch one WhatsApp deviation draft."""
        try:
            response = self.client.table("desvios_borrador").select("*").eq("id", draft_id).maybe_single().execute()
            return response.data
        except Exception as e:
            logger.error(f"Failed to get desvio borrador {draft_id}: {e}")
            return None

    def approve_desvio_borrador(self, draft_id: str, user_id: str) -> Dict[str, str]:
        """Convert one draft into Reporte + Gestion."""
        draft = self.get_desvio_borrador(draft_id)
        if not draft:
            raise ValueError("Draft not found")

        if draft.get("id_gestion") and draft.get("id_reporte"):
            return {
                "id_borrador": draft_id,
                "id_reporte": str(draft.get("id_reporte")),
                "id_gestion": str(draft.get("id_gestion")),
                "estado": str(draft.get("estado") or "convertido"),
            }

        evidencia = None
        evidencias = draft.get("evidencias_json") or []
        if isinstance(evidencias, str):
            try:
                evidencias = json.loads(evidencias)
            except Exception:
                evidencias = []
        if isinstance(evidencias, list) and evidencias:
            evidencia = evidencias[0]

        persisted = self.save_perfumeria_desvio(
            auditoria_id=str(draft.get("id_sesion") or ""),
            sucursal_id=str(draft.get("id_sucursal") or ""),
            auditor_nombre=str(draft.get("auditor_nombre") or "Auditor"),
            bloque_nombre=str(draft.get("bloque_nombre") or draft.get("bloque_id") or ""),
            descripcion=str(draft.get("descripcion") or ""),
            severidad=str(draft.get("severidad_sugerida") or "Media"),
            evidencia=evidencia,
        )

        self.client.table("desvios_borrador").update({
            "estado": "convertido",
            "id_reporte": persisted["id_reporte"],
            "id_gestion": persisted["id_gestion"],
            "aprobado_por": user_id,
            "aprobado_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", draft_id).execute()

        return {
            "id_borrador": draft_id,
            **persisted,
            "estado": "convertido",
        }

    def discard_desvio_borrador(self, draft_id: str, user_id: str, reason: str = "") -> Dict[str, str]:
        """Discard one WhatsApp deviation draft without deleting audit evidence."""
        draft = self.get_desvio_borrador(draft_id)
        if not draft:
            raise ValueError("Draft not found")

        self.client.table("desvios_borrador").update({
            "estado": "descartado",
            "descartado_por": user_id,
            "descartado_at": datetime.utcnow().isoformat(),
            "razon_descarte": reason,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", draft_id).execute()

        return {"id_borrador": draft_id, "estado": "descartado"}

    def save_whatsapp_bot_message(
        self,
        whatsapp_message_id: str,
        telefono: str,
        id_sesion: str,
        bloque_id: str,
        bloque_nombre: str,
        tipo: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Remember outbound bot messages so quoted replies can be routed later."""
        if not whatsapp_message_id:
            return
        try:
            self.client.table("whatsapp_bot_messages").upsert({
                "whatsapp_message_id": whatsapp_message_id,
                "telefono": telefono,
                "id_sesion": id_sesion,
                "bloque_id": bloque_id,
                "bloque_nombre": bloque_nombre,
                "tipo": tipo,
                "payload_json": payload or {},
            }, on_conflict="whatsapp_message_id").execute()
        except Exception as e:
            logger.warning(f"Could not save whatsapp bot message context: {e}")

    def get_whatsapp_bot_message(self, whatsapp_message_id: str) -> Optional[Dict[str, Any]]:
        """Get outbound bot message context by WhatsApp message id."""
        if not whatsapp_message_id:
            return None
        try:
            result = (
                self.client.table("whatsapp_bot_messages")
                .select("*")
                .eq("whatsapp_message_id", whatsapp_message_id)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.warning(f"Could not get whatsapp bot message context: {e}")
            return None

    def get_encargado_by_phone(self, telefono: str) -> Optional[Dict[str, Any]]:
        """Find a branch manager by profiles.telefono or sucursales.tel_responsable."""
        telefono_norm = self._normalize_phone(telefono)
        if not telefono_norm:
            return None

        try:
            response = self.client.table("profiles").select("id, role, nombre, telefono, id_sucursal").execute()
            for row in response.data or []:
                if row.get("role") != "sucursal":
                    continue
                if self._normalize_phone(row.get("telefono", "")) == telefono_norm and row.get("id_sucursal"):
                    sucursal = self.get_sucursal(str(row.get("id_sucursal")))
                    return {
                        "source": "profiles",
                        "user_id": row.get("id"),
                        "nombre": row.get("nombre") or (sucursal.nombre if sucursal else "Encargado"),
                        "telefono": telefono_norm,
                        "id_sucursal": row.get("id_sucursal"),
                        "sucursal": sucursal.nombre if sucursal else row.get("id_sucursal"),
                    }
        except Exception as e:
            logger.warning(f"Could not lookup encargado in profiles: {e}")

        try:
            for sucursal in self.get_all_sucursales():
                if self._normalize_phone(sucursal.tel_responsable) == telefono_norm:
                    return {
                        "source": "sucursales",
                        "user_id": None,
                        "nombre": sucursal.responsable or "Encargado",
                        "telefono": telefono_norm,
                        "id_sucursal": sucursal.id,
                        "sucursal": sucursal.nombre,
                    }
        except Exception as e:
            logger.warning(f"Could not lookup encargado in sucursales: {e}")

        return None

    def get_gestiones_pendientes_sucursal(self, id_sucursal: str) -> List[Dict[str, Any]]:
        """Get open deviations for a branch manager portal/chat flow."""
        try:
            response = (
                self.client.table("gestion")
                .select("*")
                .eq("id_sucursal", id_sucursal)
                .in_("estado", ["Abierta", "En_proceso", "Vencida"])
                .order("plazo_fecha")
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get pending gestiones for {id_sucursal}: {e}")
            return []

    def get_gestion_by_id(self, id_gestion: str) -> Optional[Dict[str, Any]]:
        """Get one gestion by ID."""
        try:
            response = self.client.table("gestion").select("*").eq("id_gestion", id_gestion).execute()
            data = response.data or []
            return data[0] if data else None
        except Exception as e:
            logger.error(f"Failed to get gestion {id_gestion}: {e}")
            return None

    def upload_desvio_evidencia(self, id_gestion: str, content: bytes, mime_type: str) -> str:
        """Upload evidence bytes to the private desvio-evidencias bucket."""
        ext_by_mime = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "application/pdf": "pdf",
        }
        ext = ext_by_mime.get(mime_type, "jpg")
        path = f"gestion/{id_gestion}/whatsapp-{uuid.uuid4().hex}.{ext}"
        self.client.storage.from_("desvio-evidencias").upload(
            path,
            content,
            {"content-type": mime_type, "upsert": "false"},
        )
        return path

    def create_signed_evidencia_url(self, path: str, expires_seconds: int = 86400) -> str:
        """Create a signed URL for a Storage evidence object."""
        try:
            response = self.client.storage.from_("desvio-evidencias").create_signed_url(path, expires_seconds)
            if isinstance(response, dict):
                return response.get("signedURL") or response.get("signedUrl") or ""
            return getattr(response, "signed_url", "") or getattr(response, "signedURL", "")
        except Exception as e:
            logger.warning(f"Failed to create signed URL for {path}: {e}")
            return ""

    def save_encargado_evento(
        self,
        id_gestion: str,
        tipo: str,
        contenido: str,
        metadata: Dict[str, Any],
        actor_nombre: str = "Encargado",
    ) -> None:
        """Save a branch manager message/evidence in desvio_eventos."""
        self.client.table("desvio_eventos").insert({
            "id_gestion": id_gestion,
            "tipo": tipo,
            "comentario": contenido,
            "actor_id": None,
            "actor_nombre": actor_nombre,
            "metadata": metadata,
        }).execute()

    def create_notification_for_auditor(self, id_gestion: str, auditor_id: str) -> None:
        """Create one in-app notification for an auditor/admin user."""
        self.client.table("desvio_notificaciones").insert({
            "id_gestion": id_gestion,
            "user_id": auditor_id,
            "tipo": "encargado_respondio",
        }).execute()

    def create_notifications_for_auditors(self, id_gestion: str) -> None:
        """Notify all auditor/admin users that a manager responded."""
        try:
            response = self.client.table("profiles").select("id, role").in_("role", ["admin", "auditor"]).execute()
            for row in response.data or []:
                user_id = row.get("id")
                if user_id:
                    self.create_notification_for_auditor(id_gestion, str(user_id))
        except Exception as e:
            logger.warning(f"Failed to create auditor notifications for {id_gestion}: {e}")

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
            now_utc = datetime.now(timezone.utc)
            now_naive = datetime.utcnow()

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
                        elapsed_seconds = (now_utc - ts.astimezone(timezone.utc)).total_seconds()
                    else:
                        elapsed_seconds = (now_naive - ts).total_seconds()

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

    # ========== Respuesta Pregunta Recolectora ==========

    def create_respuesta_pregunta(self, respuesta: RespuestaPregunta) -> RespuestaPregunta:
        """Create a new multi-message response collector."""
        try:
            estado = respuesta.estado.value if hasattr(respuesta.estado, "value") else str(respuesta.estado)
            data = {
                "id": respuesta.id,
                "id_sesion": respuesta.id_sesion,
                "telefono_auditor": respuesta.telefono_auditor,
                "pregunta_numero": respuesta.pregunta_numero,
                "bloque_id": respuesta.bloque_id,
                "estado": estado,
                "timestamp_inicio": respuesta.timestamp_inicio,
                "timestamp_ultimo_mensaje": respuesta.timestamp_ultimo_mensaje,
                "timeout_segundos": respuesta.timeout_segundos,
                "confirmado_por_auditor": respuesta.confirmado_por_auditor,
                "timeout_prompt_enviado": respuesta.timeout_prompt_enviado,
                "mensajes_json": respuesta.mensajes_json,
                "media_ids_json": respuesta.media_ids_json,
            }
            result = self.client.table("respuesta_pregunta").insert(data).execute()
            return RespuestaPregunta(**result.data[0])
        except Exception as e:
            logger.error(f"Error creating respuesta_pregunta: {e}")
            raise

    def get_respuesta_pregunta(self, id_respuesta: str) -> Optional[RespuestaPregunta]:
        """Get a response collector by ID."""
        try:
            result = self.client.table("respuesta_pregunta").select("*").eq("id", id_respuesta).execute()
            if result.data:
                return RespuestaPregunta(**result.data[0])
            return None
        except Exception as e:
            logger.error(f"Error getting respuesta_pregunta {id_respuesta}: {e}")
            return None

    def get_respuesta_pregunta_activa(self, telefono: str) -> Optional[RespuestaPregunta]:
        """Get the active response collector for an auditor phone."""
        try:
            result = (
                self.client.table("respuesta_pregunta")
                .select("*")
                .eq("telefono_auditor", telefono)
                .eq("estado", "recolectando")
                .order("timestamp_inicio", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                return RespuestaPregunta(**result.data[0])
            return None
        except Exception as e:
            logger.error(f"Error getting respuesta_pregunta_activa for {telefono}: {e}")
            return None

    def update_respuesta_pregunta(self, id_respuesta: str, **kwargs: Any) -> Optional[RespuestaPregunta]:
        """Update a response collector."""
        try:
            kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
            result = (
                self.client.table("respuesta_pregunta")
                .update(kwargs)
                .eq("id", id_respuesta)
                .execute()
            )
            if result.data:
                return RespuestaPregunta(**result.data[0])
            return None
        except Exception as e:
            logger.error(f"Error updating respuesta_pregunta {id_respuesta}: {e}")
            raise

    def get_respuestas_incompletas_timeout(self, timeout_segundos: int) -> List[RespuestaPregunta]:
        """Get active response collectors older than the inactivity timeout."""
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=timeout_segundos)).isoformat()
            result = (
                self.client.table("respuesta_pregunta")
                .select("*")
                .eq("estado", "recolectando")
                .lt("timestamp_ultimo_mensaje", cutoff)
                .order("timestamp_ultimo_mensaje", desc=False)
                .execute()
            )
            return [RespuestaPregunta(**row) for row in result.data] if result.data else []
        except Exception as e:
            logger.error(f"Error getting respuestas_incompletas_timeout: {e}")
            return []

    def create_respuesta_audit_log(self, id_respuesta: str, evento: str, detalles: Dict[str, Any]) -> bool:
        """Append one audit event for a response collector."""
        try:
            self.client.table("respuesta_pregunta_audit_log").insert({
                "id": str(uuid.uuid4()),
                "id_respuesta": id_respuesta,
                "evento": evento,
                "detalles_json": json.dumps(detalles, ensure_ascii=False),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Error creating respuesta audit log: {e}")
            return False

    def get_respuesta_audit_trail(self, id_respuesta: str) -> List[RespuestaPreguntaAuditLog]:
        """Get the audit trail for one response collector."""
        try:
            result = (
                self.client.table("respuesta_pregunta_audit_log")
                .select("*")
                .eq("id_respuesta", id_respuesta)
                .order("timestamp", desc=False)
                .execute()
            )
            return [RespuestaPreguntaAuditLog(**row) for row in result.data] if result.data else []
        except Exception as e:
            logger.error(f"Error getting audit trail for {id_respuesta}: {e}")
            return []

    def upload_auditoria_respuesta_media(self, id_sesion: str, id_respuesta: str, content: bytes, mime_type: str) -> str:
        """Upload collected audit response media to Storage."""
        ext_by_mime = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "audio/mpeg": "mp3",
            "audio/ogg": "ogg",
            "audio/mp4": "m4a",
            "application/pdf": "pdf",
        }
        ext = ext_by_mime.get(mime_type, "bin")
        path = f"auditoria/{id_sesion}/{id_respuesta}/{uuid.uuid4().hex}.{ext}"
        self.client.storage.from_("auditoria-respuestas").upload(
            path,
            content,
            {"content-type": mime_type, "upsert": "false"},
        )
        return path

    def create_signed_auditoria_respuesta_url(self, path: str, expires_seconds: int = 86400) -> str:
        """Create signed URL for collected audit response media."""
        try:
            response = self.client.storage.from_("auditoria-respuestas").create_signed_url(path, expires_seconds)
            if isinstance(response, dict):
                return response.get("signedURL") or response.get("signedUrl") or ""
            return getattr(response, "signed_url", "") or getattr(response, "signedURL", "")
        except Exception as e:
            logger.warning(f"Failed to create signed audit response URL for {path}: {e}")
            return ""

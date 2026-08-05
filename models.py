"""Data models for AuditBot."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


class ConversationState(str, Enum):
    """Possible states in conversation flow."""

    IDLE = "idle"
    ESPERANDO_CONFIRMACION = "esperando_confirmacion"
    ESPERANDO_EDICION = "esperando_edicion"
    SELECCIONANDO_ESCUADRON = "seleccionando_escuadron"
    SELECCIONANDO_SUCURSAL_PERFUMERIA = "seleccionando_sucursal_perfumeria"
    SELECCIONANDO_SUCURSAL = "seleccionando_sucursal"
    SELECCIONANDO_TIPO_AUDITORIA = "seleccionando_tipo_auditoria"
    EN_AUDITORIA = "en_auditoria"  # Guided point-by-point audit flow
    EN_BLOQUE = "en_bloque"
    EN_BLOQUE_PERFUMERIA = "en_bloque_perfumeria"
    CONFIRMANDO_BLOQUE = "confirmando_bloque"
    STOCK_LOOP = "stock_loop"
    EN_STOCK_ITEM = "en_stock_item"
    DESVIO_LIBRE = "desvio_libre"
    COMPROMISOS = "compromisos"
    AUDITORIA_PAUSADA = "auditoria_pausada"
    RECOLECTANDO_RESPUESTA = "recolectando_respuesta"
    ENCARGADO_SELECCIONANDO_DESVIO = "encargado_seleccionando_desvio"
    ENCARGADO_ESPERANDO_RESPUESTA = "encargado_esperando_respuesta"
    ENCARGADO_ELIGIENDO_MODULO = "encargado_eligiendo_modulo"
    CAMPANIA_LISTANDO_TAREAS = "campania_listando_tareas"
    CAMPANIA_TAREA_ACTIVA = "campania_tarea_activa"
    CAMPANIA_ESPERANDO_EVIDENCIA = "campania_esperando_evidencia"
    CAMPANIA_SOLICITANDO_INSUMO_DETALLE = "campania_solicitando_insumo_detalle"
    CAMPANIA_SOLICITANDO_INSUMO_PROVEEDOR = "campania_solicitando_insumo_proveedor"
    AUDITORIA_PERFUMERIA_LIBRE = "auditoria_perfumeria_libre"
    PERFUMERIA_SELECCIONANDO_BLOQUE = "perfumeria_seleccionando_bloque"
    PERFUMERIA_ESPERANDO_CALIFICACION = "perfumeria_esperando_calificacion"
    PERFUMERIA_CAPTURANDO_EVIDENCIA = "perfumeria_capturando_evidencia"
    PERFUMERIA_DESCRIBIENDO_DESVIO = "perfumeria_describiendo_desvio"


class Severidad(str, Enum):
    """Severity levels for findings."""

    ALTA = "Alta"
    MEDIA = "Media"
    BAJA = "Baja"


class TipoRespuesta(str, Enum):
    """Expected response types for audit questions."""

    FOTO_SI_NO = "foto_si_no"      # Photo + sí/no confirmation
    NUMERO_AUDIO = "numero_audio"  # Quantities (text/audio)
    LISTA_TEXTO = "lista_texto"    # Product list
    MIXTO = "mixto"                # Free text/audio/photo
    SI_NO = "si_no"                # Yes/no only
    FOTO = "foto"                  # Photo only


class GestionState(str, Enum):
    """States for action plans (gestión)."""

    ABIERTA = "Abierta"
    EN_PROCESO = "En_proceso"
    EN_REVISION = "En_revision"
    EN_GESTION_TERCEROS = "En_gestion_terceros"
    RESUELTA = "Resuelta"
    CERRADA = "Cerrada"
    VENCIDA = "Vencida"


@dataclass
class Auditor:
    """Auditor model from Maestro_Auditores."""

    telefono: str
    nombre: str
    cuadrilla: str
    activo: bool = True


@dataclass
class Sucursal:
    """Facility model from Maestro_Sucursales."""

    id: str
    nombre: str
    direccion: str
    responsable: str
    tel_responsable: str
    zona: str


@dataclass
class AreaSubitem:
    """Area with sub-items from Catalogo_Areas."""

    area: str
    subitems: List[str]


@dataclass
class ChecklistPunto:
    """Single point in a guided audit checklist."""

    punto_orden: int
    area: str
    descripcion: str
    responsable_default: str
    severidad_default: str


@dataclass
class ChecklistPerfumeriaPunto:
    """Single point in perfumery audit checklist."""

    bloque_id: str
    bloque_nombre: str
    punto_orden: int
    tipo_respuesta: str
    pregunta: str
    peso: int = 5
    critico: bool = False


@dataclass
class ItemBloque:
    """Item in a block-based audit checklist."""

    item_id: str
    bloque: str
    descripcion: str
    peso: int = 5


@dataclass
class ResultadoItem:
    """Result from evaluating a single item in a block."""

    item_id: str
    puntaje: Optional[int]
    tiene_desvio: bool
    descripcion_desvio: Optional[str]
    severidad: Optional[str]


@dataclass
class StockItem:
    """Stock verification item."""

    nombre: str
    stock_fisico: int
    stock_sistema: int


@dataclass
class DesvioLibre:
    """Free-form deviation/finding."""

    area_estimada: str
    descripcion: str
    severidad: str


@dataclass
class PuntoEvalResult:
    """Result from evaluating an auditor's response to a checklist point."""

    tiene_desvio: bool
    descripcion_desvio: str
    severidad: str
    ok_message: str


@dataclass
class SesionAuditoria:
    """Active audit session (supports both guided and free-form perfumery audits)."""

    id_sesion: str
    telefono_auditor: str
    sucursal_id: str
    estado: str
    timestamp_inicio: str
    timestamp_ultimo_punto: str
    punto_actual: int = 0
    total_puntos: int = 0
    hallazgos_json: str = "[]"
    omitidos_json: str = "[]"
    bloque_actual: str = "A"
    resultados_json: str = "{}"
    stock_total: int = 0
    stock_actual: int = 0
    stock_items_json: str = "[]"
    desvios_libres_json: str = "[]"
    compromisos_firmados: str = ""


@dataclass
class Hallazgo:
    """Finding (hallazgo) from parser."""

    sucursal_id: str
    sucursal_nombre: str
    area: str
    subitem: str
    descripcion: str
    severidad: Severidad
    confianza: float


@dataclass
class ParserResponse:
    """Response from Claude parser."""

    hallazgos: List[Hallazgo] = field(default_factory=list)
    datos_faltantes: List[str] = field(default_factory=list)
    mensaje_original_limpio: str = ""


@dataclass
class Conversacion:
    """Conversation state from Conversaciones sheet."""

    telefono: str
    estado_actual: ConversationState
    id_pendiente: Optional[str] = None
    ultimo_mensaje: str = ""
    timestamp: Optional[datetime] = None


@dataclass
class Pendiente:
    """Pending confirmation record from Pendientes sheet."""

    id_temp: str
    telefono_auditor: str
    estado: str
    datos_json: str
    timestamp_creacion: datetime
    expira_en: datetime


@dataclass
class Reporte:
    """Audit report from Reportes sheet."""

    id: str
    fecha: str
    hora: str
    cuadrilla: str
    auditor: str
    id_sucursal: str
    sucursal: str
    area: str
    subitem: str
    descripcion: str
    severidad: Severidad
    foto_url: Optional[str] = None
    creado_por_audio: bool = False
    timestamp: Optional[datetime] = None


@dataclass
class Gestion:
    """Action plan (gestión) from Gestion sheet."""

    id_gestion: str
    id_reporte: str
    id_sucursal: str
    sucursal: str
    desvio: str
    severidad: Severidad
    responsable: str
    tel_responsable: str
    plazo_fecha: datetime
    plan_accion: str
    estado: GestionState = GestionState.ABIERTA
    fecha_cierre: Optional[datetime] = None
    cerrado_por: Optional[str] = None
    bloque: Optional[str] = None  # LIMPIEZA/STOCK/OFERTAS/BURBUJAS (perfumería v2)
    plazo_fecha_original: Optional[datetime] = None
    veces_rechazado: int = 0
    en_revision_desde: Optional[datetime] = None


@dataclass
class WhatsAppPayload:
    """Incoming payload from the WhatsApp webhook."""

    telefono: str
    tipo: str  # "text", "audio", "image"
    contenido: Optional[str] = None
    media_url: Optional[str] = None
    media_id: Optional[str] = None
    mime_type: Optional[str] = None
    message_id: Optional[str] = None
    context_message_id: Optional[str] = None
    timestamp: Optional[datetime] = field(default_factory=datetime.utcnow)


@dataclass
class WhatsAppMessage:
    """Message to send via WhatsApp."""

    phone: str
    text: str
    caption: Optional[str] = None
    file_url: Optional[str] = None


class RespuestaPreguntaEstado(str, Enum):
    """State for multi-message response collection."""

    RECOLECTANDO = "recolectando"
    COMPLETADA = "completada"
    DESCARTADA = "descartada"


class TipoMensajeRespuesta(str, Enum):
    """Message type inside a collected response."""

    TEXTO = "text"
    IMAGEN = "image"
    AUDIO = "audio"


@dataclass
class MensajeEnRespuesta:
    """One WhatsApp message collected for one audit question."""

    tipo: str
    contenido: str
    media_ids: List[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    estado_procesamiento: str = "pendiente"
    error_mensaje: Optional[str] = None


@dataclass
class RespuestaPregunta:
    """Multi-message response collector for a single audit question/block."""

    id: str
    id_sesion: str
    telefono_auditor: str
    pregunta_numero: int
    bloque_id: str
    estado: RespuestaPreguntaEstado | str
    timestamp_inicio: str
    timestamp_ultimo_mensaje: str
    user_id_auditor: Optional[str] = None
    timeout_segundos: int = 120
    confirmado_por_auditor: bool = False
    timeout_prompt_enviado: bool = False
    mensajes_json: str = "[]"
    media_ids_json: str = "[]"
    respuesta_consolidada: Optional[str] = None
    desvios_json: Optional[str] = None
    razon_descarte: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def get_mensajes(self) -> List[MensajeEnRespuesta]:
        """Deserialize collected messages."""
        try:
            raw = json.loads(self.mensajes_json) if self.mensajes_json else []
            return [MensajeEnRespuesta(**msg) for msg in raw]
        except Exception as e:
            logger.error(f"Error deserializing mensajes_json: {e}")
            return []

    def get_media_ids(self) -> List[dict]:
        """Deserialize collected media metadata."""
        try:
            raw = json.loads(self.media_ids_json) if self.media_ids_json else []
            return raw if isinstance(raw, list) else []
        except Exception as e:
            logger.error(f"Error deserializing media_ids_json: {e}")
            return []


@dataclass
class RespuestaPreguntaAuditLog:
    """Audit trail event for a collected response."""

    id: str
    id_respuesta: str
    evento: str
    detalles_json: str
    timestamp: str


RESPUESTA_CONFIG = {
    "timeout_sin_actividad_segundos": 120,
    "auto_complete_enabled": False,
    "timeout_auto_complete_segundos": 150,
    "timeout_max_segundos": 300,
    "mensaje_max_por_respuesta": 20,
    "respuesta_max_caracteres": 5000,
}

RESPUESTA_VALIDACION = {
    "PRES": {"min_texto": 10, "requiere_foto": False, "requiere_audio": False},
    "GOND": {"min_texto": 15, "requiere_foto": True, "requiere_audio": False},
    "STOCK": {"min_texto": 5, "requiere_foto": False, "requiere_audio": False},
    "TEMP": {"min_texto": 8, "requiere_foto": True, "requiere_audio": False},
}

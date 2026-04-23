"""Data models for AuditBot."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class ConversationState(str, Enum):
    """Possible states in conversation flow."""

    IDLE = "idle"
    ESPERANDO_CONFIRMACION = "esperando_confirmacion"
    ESPERANDO_EDICION = "esperando_edicion"
    SELECCIONANDO_SUCURSAL = "seleccionando_sucursal"
    EN_AUDITORIA = "en_auditoria"  # Legacy: punto-por-punto
    EN_BLOQUE = "en_bloque"
    CONFIRMANDO_BLOQUE = "confirmando_bloque"
    STOCK_LOOP = "stock_loop"
    EN_STOCK_ITEM = "en_stock_item"
    DESVIO_LIBRE = "desvio_libre"
    COMPROMISOS = "compromisos"
    AUDITORIA_PAUSADA = "auditoria_pausada"


class Severidad(str, Enum):
    """Severity levels for findings."""

    ALTA = "Alta"
    MEDIA = "Media"
    BAJA = "Baja"


class GestionState(str, Enum):
    """States for action plans (gestión)."""

    ABIERTA = "Abierta"
    EN_PROCESO = "En_proceso"
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
    """Active guided audit session."""

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


@dataclass
class WAHAPayload:
    """Incoming payload from the WhatsApp webhook."""

    telefono: str
    tipo: str  # "text", "audio", "image"
    contenido: Optional[str] = None
    media_url: Optional[str] = None
    timestamp: Optional[datetime] = field(default_factory=datetime.utcnow)


@dataclass
class WAHAMessage:
    """Message to send via WhatsApp."""

    phone: str
    text: str
    caption: Optional[str] = None
    file_url: Optional[str] = None

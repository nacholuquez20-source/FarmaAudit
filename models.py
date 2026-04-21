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
    """Incoming payload from WAHA webhook."""

    telefono: str
    tipo: str  # "text", "audio", "image"
    contenido: Optional[str] = None
    media_url: Optional[str] = None
    timestamp: Optional[datetime] = field(default_factory=datetime.utcnow)


@dataclass
class WAHAMessage:
    """Message to send via WAHA."""

    phone: str
    text: str
    caption: Optional[str] = None
    file_url: Optional[str] = None

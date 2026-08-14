"""Audit session state machine for WhatsApp perfumery audits."""

from enum import Enum
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import json
import logging
import os
import uuid

logger = logging.getLogger(__name__)


class AuditState(Enum):
    """State machine for audit conversation flow."""
    IDLE = "idle"                              # No audit in progress
    SELECT_SUCURSAL = "select_sucursal"        # Choosing sucursal for a new audit
    VERIFY_SELECT_SUCURSAL = "verify_select_sucursal"  # Choosing sucursal for standalone desvío management
    VERIFY_PREVIOUS = "verify_previous"        # Verifying open desvíos from previous audits
    SCORING = "scoring"                        # Collecting area scores (1-5)
    BLOQUE_EVIDENCE_COLLECTION = "bloque_evidence"  # Collecting evidence for current bloque
    SCORING_BRANDS = "scoring_brands"         # Collecting brand scores for OFERTAS
    SUMMARY = "summary"                        # Showing summary, waiting confirmation
    DONE = "done"                              # Audit completed and saved
    REVISION_BANDEJA = "revision_bandeja"      # Aprobar/rechazar correcciones del encargado, standalone


class BloqueType(Enum):
    """Audit areas (bloques)."""
    LIMPIEZA = "LIMPIEZA"
    STOCK = "STOCK"
    OFERTAS = "OFERTAS"
    BURBUJAS = "BURBUJAS"


class BrandType(Enum):
    """Brands for OFERTAS evaluation."""
    UNILEVER = "unilever"
    COLGATE = "colgate"
    HALEON = "haleon"
    GENOMMA = "genomma"


BLOQUE_ORDER = [
    BloqueType.LIMPIEZA.value,
    BloqueType.STOCK.value,
    BloqueType.OFERTAS.value,
    BloqueType.BURBUJAS.value,
]

BRAND_ORDER = [
    BrandType.UNILEVER.value,
    BrandType.COLGATE.value,
    BrandType.HALEON.value,
    BrandType.GENOMMA.value,
]

BRAND_LABELS = {
    BrandType.UNILEVER.value: "Unilever",
    BrandType.COLGATE.value: "Colgate-Palmolive",
    BrandType.HALEON.value: "Haleon",
    BrandType.GENOMMA.value: "Genomma Lab",
}

BLOQUE_LABELS = {
    BloqueType.LIMPIEZA.value: "Limpieza & Organización",
    BloqueType.STOCK.value: "Stock & Inventario",
    BloqueType.OFERTAS.value: "Ofertas & Exhibición",
    BloqueType.BURBUJAS.value: "Displays & Señalización",
}

BLOQUE_DESCRIPTIONS = {
    BloqueType.LIMPIEZA.value: "Estado de góndolas, orden general, polvo",
    BloqueType.STOCK.value: "Niveles, productos vencidos, reposición",
    BloqueType.OFERTAS.value: "Precios, promociones, exhibición por marca",
    BloqueType.BURBUJAS.value: "Displays atractivos, señalización clara",
}


@dataclass
class FotoEvidence:
    """Photo evidence for deviations."""
    id: str                          # foto_XXX
    media_id: str                    # Meta media ID
    media_url: Optional[str] = None  # Downloaded URL
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    bloque: Optional[str] = None     # LIMPIEZA, STOCK, OFERTAS, BURBUJAS
    descripcion: Optional[str] = None
    validated: bool = False          # Quality check passed

    def to_dict(self):
        return asdict(self)


@dataclass
class Desvio:
    """Deviation/problem found during audit."""
    id: str                          # desvio_XXX
    bloque: str                      # Which area
    descripcion: str                 # Problem description
    fotos: List[str] = field(default_factory=list)  # foto_XXX IDs
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self):
        return asdict(self)


@dataclass
class AuditSession:
    """Active audit session in progress."""

    # Session ID and identifiers
    id_sesion: str                   # audit_TIMESTAMP
    telefono: str                    # Auditor phone
    sucursal_id: str                 # SC-001
    auditor_nombre: Optional[str] = None

    # State
    estado: AuditState = AuditState.IDLE

    # Scoring
    bloques: Dict[str, int] = field(default_factory=dict)  # {LIMPIEZA: 4, STOCK: 3}
    current_bloque_index: int = 0   # Index in BLOQUE_ORDER

    # Brands (for OFERTAS)
    brands: Dict[str, Dict[str, int]] = field(
        default_factory=lambda: {BloqueType.OFERTAS.value: {}}
    )
    current_brand_index: int = 0    # Index in BRAND_ORDER for OFERTAS

    # Evidence
    fotos: List[FotoEvidence] = field(default_factory=list)
    desvios: List[Desvio] = field(default_factory=list)

    # Foto "ancla" del bloque actual: la última FotoEvidence.id recibida. Todo
    # audio/texto que llegue despues se liga a esta foto (Desvio.fotos), hasta
    # que llegue una foto nueva que la reemplaza. Se resetea en enter_bloque(),
    # antes de que arranque la recoleccion de evidencia de cada bloque.
    current_foto_id: Optional[str] = None

    # Verification of previous open desvíos (per bloque)
    pending_verifications: List[Dict[str, Any]] = field(default_factory=list)
    current_verification_index: int = 0
    awaiting_verification_photo: bool = False
    # True mientras se espera el motivo obligatorio de "depende de terceros"
    # (Meta limita a 3 botones por quick_reply, ya ocupados por
    # Resuelto/Persiste/Omitir — esta opcion se ofrece como comando de texto).
    awaiting_verification_motivo: bool = False
    verified_resueltos: int = 0
    verified_persisten: int = 0

    # Bandeja de revision (aprobar/rechazar correcciones del encargado desde
    # WhatsApp, comando 'pendientes'): reusa pending_verifications/
    # current_verification_index como cola (mismo mecanismo ya probado por
    # la verificacion de desvios pendientes), pero es un flujo distinto —
    # AuditState.REVISION_BANDEJA, no VERIFY_PREVIOUS. True mientras se
    # espera el motivo obligatorio de un rechazo.
    awaiting_revision_motivo: bool = False

    # Standalone desvío management (no scoring, queue spans all bloques)
    verification_only: bool = False
    verification_menu: List[Dict[str, Any]] = field(default_factory=list)

    # Post-audit fields (persisted so they survive session reload between messages)
    pending_ficha_reporte_id: Optional[str] = None   # reporte_id deferred until responsable is known
    pending_ficha_gestion_ids: List[str] = field(default_factory=list)  # gestion ids to link once ficha_id exists
    desvios_responsable: Optional[str] = None         # name of person responsible for desvíos
    ficha_url: Optional[str] = None                   # Drive URL of the generated PDF

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    last_message_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = field(
        default_factory=lambda: (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    )
    # Cuándo se le avisó al auditor que tenía la auditoría parada. Sirve para no
    # repetir el aviso en cada corrida del job.
    inactivity_notice_at: Optional[str] = None

    def __post_init__(self):
        """Ensure brands dict has OFERTAS key."""
        if BloqueType.OFERTAS.value not in self.brands:
            self.brands[BloqueType.OFERTAS.value] = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            'id_sesion': self.id_sesion,
            'telefono': self.telefono,
            'sucursal_id': self.sucursal_id,
            'auditor_nombre': self.auditor_nombre,
            'estado': self.estado.value,
            'bloques': self.bloques,
            'current_bloque_index': self.current_bloque_index,
            'brands': self.brands,
            'current_brand_index': self.current_brand_index,
            'fotos': [f.to_dict() for f in self.fotos],
            'desvios': [d.to_dict() for d in self.desvios],
            'current_foto_id': self.current_foto_id,
            'pending_verifications': self.pending_verifications,
            'current_verification_index': self.current_verification_index,
            'awaiting_verification_photo': self.awaiting_verification_photo,
            'awaiting_verification_motivo': self.awaiting_verification_motivo,
            'awaiting_revision_motivo': self.awaiting_revision_motivo,
            'verified_resueltos': self.verified_resueltos,
            'verified_persisten': self.verified_persisten,
            'verification_only': self.verification_only,
            'verification_menu': self.verification_menu,
            'pending_ficha_reporte_id': self.pending_ficha_reporte_id,
            'pending_ficha_gestion_ids': self.pending_ficha_gestion_ids,
            'desvios_responsable': self.desvios_responsable,
            'ficha_url': self.ficha_url,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'last_message_at': self.last_message_at,
            'expires_at': self.expires_at,
            'inactivity_notice_at': self.inactivity_notice_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AuditSession':
        """Reconstruct from dict."""
        data = data.copy()
        data['estado'] = AuditState(data.get('estado', 'idle'))

        # Reconstruct fotos
        fotos_data = data.pop('fotos', [])
        fotos = [FotoEvidence(**f) for f in fotos_data]

        # Reconstruct desvios
        desvios_data = data.pop('desvios', [])
        desvios = [Desvio(**d) for d in desvios_data]

        # Ahora que las sesiones se persisten, una fila escrita por una versión
        # anterior del bot tiene que seguir siendo legible después de un deploy.
        # Se descartan las claves que ya no existen en la dataclass en vez de
        # reventar con TypeError y perder la auditoría en curso.
        known = {f.name for f in fields(cls)}
        extra = set(data) - known
        if extra:
            logger.warning(f"Sesion con campos desconocidos, se ignoran: {sorted(extra)}")
            data = {k: v for k, v in data.items() if k in known}

        session = cls(**data)
        session.fotos = fotos
        session.desvios = desvios
        return session

    def get_current_bloque(self) -> str:
        """Get current bloque being scored."""
        if self.current_bloque_index < len(BLOQUE_ORDER):
            return BLOQUE_ORDER[self.current_bloque_index]
        return BLOQUE_ORDER[-1]

    def get_current_brand(self) -> Optional[str]:
        """Get current brand being scored."""
        if self.estado != AuditState.SCORING_BRANDS:
            return None
        if self.current_brand_index < len(BRAND_ORDER):
            return BRAND_ORDER[self.current_brand_index]
        return None

    def is_all_bloques_scored(self) -> bool:
        """Check if all bloques have been scored."""
        return len(self.bloques) == len(BLOQUE_ORDER)

    def is_ofertas_completed(self) -> bool:
        """Check if all brands in OFERTAS have been scored."""
        if BloqueType.OFERTAS.value not in self.bloques:
            return False
        if BloqueType.OFERTAS.value not in self.brands:
            return False
        ofertas_brands = self.brands[BloqueType.OFERTAS.value]
        return len(ofertas_brands) == len(BRAND_ORDER)

    def set_bloque_score(self, bloque: str, score: int) -> None:
        """Set score for bloque."""
        self.bloques[bloque] = score
        self.last_message_at = datetime.now(timezone.utc).isoformat()

    def set_brand_score(self, brand: str, score: int) -> None:
        """Set score for brand in OFERTAS."""
        if BloqueType.OFERTAS.value not in self.brands:
            self.brands[BloqueType.OFERTAS.value] = {}
        self.brands[BloqueType.OFERTAS.value][brand] = score
        self.last_message_at = datetime.now(timezone.utc).isoformat()

    def add_foto(self, foto: FotoEvidence) -> None:
        """Add photo evidence."""
        self.fotos.append(foto)
        self.last_message_at = datetime.now(timezone.utc).isoformat()

    def add_desvio(self, bloque: str, descripcion: str, fotos: Optional[List[str]] = None) -> Desvio:
        """Add deviation/problem, optionally linked to one or more FotoEvidence ids."""
        desvio = Desvio(
            id=f"desvio_{uuid.uuid4().hex[:8]}",
            bloque=bloque,
            descripcion=descripcion,
            fotos=fotos or [],
        )
        self.desvios.append(desvio)
        self.last_message_at = datetime.now(timezone.utc).isoformat()
        return desvio

    def get_current_verification(self) -> Optional[Dict[str, Any]]:
        """Get the gestion currently being verified, or None if queue is done."""
        if self.current_verification_index < len(self.pending_verifications):
            return self.pending_verifications[self.current_verification_index]
        return None

    def move_to_next_verification(self) -> bool:
        """Advance verification queue. Returns True if there is another pending."""
        self.current_verification_index += 1
        self.awaiting_verification_photo = False
        self.last_message_at = datetime.now(timezone.utc).isoformat()
        return self.current_verification_index < len(self.pending_verifications)

    def move_to_next_bloque(self) -> bool:
        """Move to next bloque in scoring."""
        if self.current_bloque_index < len(BLOQUE_ORDER) - 1:
            self.current_bloque_index += 1
            return True
        return False

    def move_to_next_brand(self) -> bool:
        """Move to next brand in OFERTAS scoring."""
        if self.current_brand_index < len(BRAND_ORDER) - 1:
            self.current_brand_index += 1
            return True
        return False

    def get_desvios_summary(self) -> Dict[str, Any]:
        """Get summary of deviations found."""
        desvios_by_bloque = {}
        for desvio in self.desvios:
            if desvio.bloque not in desvios_by_bloque:
                desvios_by_bloque[desvio.bloque] = []
            desvios_by_bloque[desvio.bloque].append(desvio)

        return desvios_by_bloque

    def is_expired(self) -> bool:
        """Check if session has expired."""
        expires = datetime.fromisoformat(self.expires_at)
        return datetime.now(timezone.utc) > expires


# ---------------------------------------------------------------------------
# Almacenamiento de sesiones
#
# Postgres (tabla `sesiones_whatsapp`, etapa-19) es la fuente de verdad; el dict
# en memoria es sólo un cache para no ir a la base en cada mensaje.
#
# Si la base no está disponible el bot sigue funcionando SOLO en memoria: se
# pierde la resistencia al redeploy, pero la conversación en curso no se corta.
# Esa degradación es deliberada y es también lo que permite que la suite de
# tests corra sin Supabase configurado.
# ---------------------------------------------------------------------------

_TABLE = "sesiones_whatsapp"

_sessions_cache: Dict[str, AuditSession] = {}


def _client():
    """Cliente Supabase, o None si no está configurado o si corren los tests."""
    # Bajo pytest no se toca la base. Las sesiones son estado efímero y la
    # máquina de desarrollo tiene credenciales de producción en .env: una
    # corrida de tests no tiene por qué escribir ahí.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    try:
        from supabase_manager import SupabaseManager
        return SupabaseManager().client
    except Exception as exc:
        logger.error(f"Sesiones: sin cliente Supabase, se degrada a memoria ({exc})")
        return None


def _persist(session: AuditSession) -> None:
    """Upsert de la sesión. Nunca propaga excepciones."""
    client = _client()
    if client is None:
        return
    try:
        client.table(_TABLE).upsert(
            {
                "telefono": session.telefono,
                "id_sesion": session.id_sesion,
                "estado": session.estado.value,
                "sucursal_id": session.sucursal_id or None,
                "expires_at": session.expires_at,
                "last_message_at": session.last_message_at,
                "data": session.to_dict(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="telefono",
        ).execute()
    except Exception as exc:
        logger.error(f"Sesiones: no se pudo guardar la de {session.telefono}: {exc}")


def _load(telefono: str) -> Optional[AuditSession]:
    """Rehidrata la sesión desde la base. None si no hay o si está corrupta."""
    client = _client()
    if client is None:
        return None
    try:
        res = client.table(_TABLE).select("data").eq("telefono", telefono).limit(1).execute()
    except Exception as exc:
        logger.error(f"Sesiones: no se pudo leer la de {telefono}: {exc}")
        return None

    rows = res.data or []
    if not rows:
        return None

    try:
        return AuditSession.from_dict(rows[0]["data"])
    except Exception as exc:
        # Una fila ilegible bloquearía al auditor en cada mensaje: se descarta.
        logger.error(f"Sesiones: fila corrupta para {telefono}, se descarta: {exc}")
        _forget(telefono)
        return None


def _forget(telefono: str) -> None:
    """Borra la fila. Nunca propaga excepciones."""
    client = _client()
    if client is None:
        return
    try:
        client.table(_TABLE).delete().eq("telefono", telefono).execute()
    except Exception as exc:
        logger.error(f"Sesiones: no se pudo borrar la de {telefono}: {exc}")


def create_session(telefono: str, sucursal_id: str, auditor_nombre: Optional[str] = None) -> AuditSession:
    """Create new audit session."""
    session = AuditSession(
        id_sesion=f"audit_{int(datetime.now(timezone.utc).timestamp())}",
        telefono=telefono,
        sucursal_id=sucursal_id,
        auditor_nombre=auditor_nombre,
        estado=AuditState.IDLE,
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    _sessions_cache[telefono] = session
    _persist(session)
    return session


def get_session(telefono: str) -> Optional[AuditSession]:
    """Get active session for phone number (memoria, si no la base)."""
    session = _sessions_cache.get(telefono)

    if session is None:
        session = _load(telefono)
        if session is not None:
            _sessions_cache[telefono] = session
            logger.info(f"Sesion de {telefono} recuperada desde la base ({session.estado.value})")

    if session is not None and session.is_expired():
        delete_session(telefono)
        return None

    return session


def save_session(session: AuditSession) -> None:
    """Save session to cache and database."""
    session.last_message_at = datetime.now(timezone.utc).isoformat()
    _sessions_cache[session.telefono] = session
    _persist(session)


def delete_session(telefono: str) -> None:
    """Delete session (after completion or timeout)."""
    _sessions_cache.pop(telefono, None)
    _forget(telefono)


def get_all_sessions() -> List[AuditSession]:
    """Todas las sesiones vivas. Lee de la base porque es lo que necesita el job
    de expiración: el cache en memoria sólo tiene las de este proceso."""
    client = _client()
    if client is None:
        return list(_sessions_cache.values())

    try:
        res = client.table(_TABLE).select("data").execute()
    except Exception as exc:
        logger.error(f"Sesiones: no se pudieron listar: {exc}")
        return list(_sessions_cache.values())

    sessions: List[AuditSession] = []
    for row in res.data or []:
        try:
            sessions.append(AuditSession.from_dict(row["data"]))
        except Exception as exc:
            logger.error(f"Sesiones: fila ilegible al listar, se omite: {exc}")
    return sessions

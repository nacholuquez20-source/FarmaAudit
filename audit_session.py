"""Audit session state machine for WhatsApp perfumery audits."""

from enum import Enum
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import json
import uuid


class AuditState(Enum):
    """State machine for audit conversation flow."""
    IDLE = "idle"                              # No audit in progress
    VERIFY_SELECT_SUCURSAL = "verify_select_sucursal"  # Choosing sucursal for standalone desvío management
    VERIFY_PREVIOUS = "verify_previous"        # Verifying open desvíos from previous audits
    SCORING = "scoring"                        # Collecting area scores (1-5)
    BLOQUE_EVIDENCE_COLLECTION = "bloque_evidence"  # Collecting evidence for current bloque
    SCORING_BRANDS = "scoring_brands"         # Collecting brand scores for OFERTAS
    SUMMARY = "summary"                        # Showing summary, waiting confirmation
    DONE = "done"                              # Audit completed and saved


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

    # Verification of previous open desvíos (per bloque)
    pending_verifications: List[Dict[str, Any]] = field(default_factory=list)
    current_verification_index: int = 0
    awaiting_verification_photo: bool = False
    verified_resueltos: int = 0
    verified_persisten: int = 0

    # Standalone desvío management (no scoring, queue spans all bloques)
    verification_only: bool = False
    verification_menu: List[Dict[str, Any]] = field(default_factory=list)

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    last_message_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = field(
        default_factory=lambda: (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    )

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
            'pending_verifications': self.pending_verifications,
            'current_verification_index': self.current_verification_index,
            'awaiting_verification_photo': self.awaiting_verification_photo,
            'verified_resueltos': self.verified_resueltos,
            'verified_persisten': self.verified_persisten,
            'verification_only': self.verification_only,
            'verification_menu': self.verification_menu,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'last_message_at': self.last_message_at,
            'expires_at': self.expires_at,
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

    def add_desvio(self, bloque: str, descripcion: str) -> Desvio:
        """Add deviation/problem."""
        desvio = Desvio(
            id=f"desvio_{uuid.uuid4().hex[:8]}",
            bloque=bloque,
            descripcion=descripcion,
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


# Session storage: in-memory cache with Redis fallback
_sessions_cache: Dict[str, AuditSession] = {}


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
    return session


def get_session(telefono: str) -> Optional[AuditSession]:
    """Get active session for phone number."""
    return _sessions_cache.get(telefono)


def save_session(session: AuditSession) -> None:
    """Save session to cache."""
    session.last_message_at = datetime.now(timezone.utc).isoformat()
    _sessions_cache[session.telefono] = session


def delete_session(telefono: str) -> None:
    """Delete session (after completion or timeout)."""
    _sessions_cache.pop(telefono, None)


def get_all_sessions() -> List[AuditSession]:
    """Get all active sessions."""
    return list(_sessions_cache.values())

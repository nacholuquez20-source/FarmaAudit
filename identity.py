"""Resolución única de identidad de WhatsApp.

Reemplaza las dos consultas separadas que existían antes (auditores por un
lado, profiles/sucursales.tel_responsable por otro) por una sola lectura de
usuarios_whatsapp (etapa-21), que es ahora la fuente única de "quién es este
teléfono y qué puede hacer".

get_auditor y get_encargado_by_phone en supabase_manager.py quedan como
envoltorios finos sobre resolve_whatsapp_user para no tener que tocar los
~13 call sites que ya existen en router.py.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


def normalize_phone(phone: Optional[str]) -> str:
    """Deja solo dígitos, igual que SupabaseManager._normalize_phone."""
    if not phone:
        return ""
    return re.sub(r"\D", "", str(phone))


@dataclass
class WhatsAppUser:
    """Una persona identificada por su teléfono de WhatsApp."""

    id: str
    telefono: str
    nombre: str
    rol: str  # 'responsable_sucursal' | 'auditor'
    activo: bool
    id_sucursal: Optional[str] = None
    tipos_auditoria: List[str] = field(default_factory=list)


def resolve_whatsapp_user(telefono: str) -> Optional[WhatsAppUser]:
    """Resuelve un teléfono contra usuarios_whatsapp con una sola consulta indexada."""
    from supabase_manager import SupabaseManager

    telefono_norm = normalize_phone(telefono)
    if not telefono_norm:
        return None

    try:
        db = SupabaseManager()
        response = (
            db.client.table("usuarios_whatsapp")
            .select("id, telefono, nombre, rol, activo, id_sucursal")
            .eq("telefono", telefono_norm)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return None
        row = rows[0]

        tipos: List[str] = []
        if row.get("rol") == "auditor":
            tipos_response = (
                db.client.table("usuario_tipos_auditoria")
                .select("tipo_auditoria_id")
                .eq("usuario_id", row["id"])
                .execute()
            )
            tipos = [t["tipo_auditoria_id"] for t in (tipos_response.data or [])]

        return WhatsAppUser(
            id=row["id"],
            telefono=row.get("telefono", telefono_norm),
            nombre=row.get("nombre", ""),
            rol=row.get("rol", ""),
            activo=bool(row.get("activo", False)),
            id_sucursal=row.get("id_sucursal"),
            tipos_auditoria=tipos,
        )
    except Exception as e:
        logger.error(f"Failed to resolve whatsapp user {telefono}: {e}")
        return None

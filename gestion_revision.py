"""Lógica de aprobar/rechazar la corrección de un encargado sobre un desvío
en revisión (o marcarlo dependiente de terceros / retomarlo).

Fuente única de esta lógica — antes vivía solo en el endpoint del panel
(`POST /api/gestion/{id_gestion}/revision`, main.py). Se extrajo acá para que
la bandeja de revisión del bot de WhatsApp (audit_handlers.py) pueda aplicar
exactamente el mismo comportamiento sin duplicar el código: mismas
actualizaciones de estado, mismo evento en desvio_eventos, mismo aviso al
encargado, misma escalada al coordinador en el 3er rechazo.

Este módulo es deliberadamente chico y sin dependencias circulares (mismo
criterio que identity.py) — lo importan tanto main.py como audit_handlers.py.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from identity import resolve_responsable_by_sucursal
from meta_client import MetaClient
from supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

ACCIONES_VALIDAS = {"aprobar", "rechazar", "en_gestion_terceros", "retomar"}


async def aplicar_revision_gestion(
    db: SupabaseManager,
    meta_client: MetaClient,
    gestion: Dict[str, Any],
    accion: str,
    actor_nombre: str,
    actor_id: Optional[str],
    motivo: Optional[str] = None,
    plazo_dias: int = 2,
) -> Dict[str, Any]:
    """Aplica una acción de revisión sobre una gestión ya obtenida por el
    caller (no valida HTTP ni busca la gestión — eso es responsabilidad de
    quien llama, sea el endpoint del panel o la bandeja del bot).

    accion: 'aprobar' | 'rechazar' | 'en_gestion_terceros' | 'retomar'
    motivo: obligatorio para 'rechazar' y 'en_gestion_terceros' — el caller
        debe validarlo antes de llegar acá (esta función asume que ya está
        validado, igual que el endpoint original hacía antes de llamar a
        esta lógica).

    Devuelve {"veces_rechazado": int, "updates": dict} — el caller decide si
    necesita esos datos (ej. la bandeja del bot los usa para decidir si
    avisar sobre escalada, aunque la escalada al coordinador ya la maneja
    esta misma función).
    """
    id_gestion = gestion["id_gestion"]
    motivo = (motivo or "").strip()
    now = datetime.now(timezone.utc)

    veces_rechazado = int(gestion.get("veces_rechazado") or 0)
    evento_tipo = "nota"
    evento_comentario = motivo

    if accion == "aprobar":
        updates = {
            "estado": "Resuelta",
            "cerrado_por": actor_nombre,
            "en_revision_desde": None,
        }
        evento_tipo = "cierre"
        evento_comentario = motivo or "Correccion aprobada por el auditor."
    elif accion == "rechazar":
        nueva_plazo = (now + timedelta(days=plazo_dias)).strftime("%Y-%m-%d")
        veces_rechazado += 1
        updates = {
            "estado": "En_proceso",
            "plazo_fecha": nueva_plazo,
            "plazo_fecha_original": gestion.get("plazo_fecha_original") or gestion.get("plazo_fecha"),
            "veces_rechazado": veces_rechazado,
            "en_revision_desde": None,
        }
        evento_tipo = "rechazo"
    elif accion == "en_gestion_terceros":
        updates = {"estado": "En_gestion_terceros", "en_revision_desde": None}
    elif accion == "retomar":
        updates = {"estado": "En_proceso"}
        evento_comentario = motivo or "Se retoma la gestion del desvio."
    else:
        raise ValueError(f"accion invalida: {accion!r}")

    db.update_gestion_fields(id_gestion, updates)

    db.client.table("desvio_eventos").insert({
        "id_gestion": id_gestion,
        "tipo": evento_tipo,
        "comentario": evento_comentario,
        "actor_id": actor_id,
        "actor_nombre": actor_nombre,
        "metadata": {"accion": accion},
    }).execute()

    try:
        db.client.table("desvio_notificaciones").update({"leida": True}).eq("id_gestion", id_gestion).eq(
            "tipo", "encargado_respondio"
        ).eq("leida", False).execute()
    except Exception as exc:
        logger.warning(f"Failed to mark notifications read for {id_gestion}: {exc}")

    # gestion.tel_responsable es una foto congelada al momento de crear la
    # gestion (queda vacía en la mayoría de las filas históricas) — se
    # resuelve en vivo, mismo criterio que el resto de los avisos al
    # encargado desde Bloque 3 del circuito de vuelta.
    responsable = resolve_responsable_by_sucursal(gestion.get("id_sucursal"))
    telefono = responsable.telefono if responsable else ""
    if telefono and accion in {"aprobar", "rechazar"}:
        try:
            if accion == "aprobar":
                mensaje = (
                    f"✅ Tu corrección para \"{gestion.get('desvio')}\" quedó aprobada. "
                    "¡Gracias por resolverlo!"
                )
            else:
                mensaje = (
                    f"🔄 Tu corrección para \"{gestion.get('desvio')}\" todavía necesita un ajuste.\n"
                    f"Motivo: {motivo}\n\n"
                    "Escribinos por acá cuando quieras volver a intentarlo."
                )
            await meta_client.send_text(telefono, mensaje)
        except Exception as exc:
            logger.warning(f"Failed to send WhatsApp feedback for {id_gestion}: {exc}")

        if accion == "rechazar" and veces_rechazado >= 3:
            from config import get_settings
            settings = get_settings()
            if settings.coordinador_tel:
                try:
                    await meta_client.send_text(
                        settings.coordinador_tel,
                        f"FarmaAudit: el desvio {id_gestion} ({gestion.get('sucursal')}) fue rechazado "
                        f"{veces_rechazado} veces. Requiere seguimiento.",
                    )
                except Exception as exc:
                    logger.warning(f"Failed to alert coordinator about repeated rejection {id_gestion}: {exc}")

    return {"veces_rechazado": veces_rechazado, "updates": updates}

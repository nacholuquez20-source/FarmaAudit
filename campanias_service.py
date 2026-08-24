"""Servicio compartido de activacion de campanias/tours.

Lo llaman TANTO el endpoint FastAPI (`POST /api/campanias/{id}/activar`, wizard web,
`main.py`) COMO el bot de WhatsApp (creacion por el auditor, Fase 8 de
ARQUITECTURA_DESVIOS_CAMPANIAS.md, Modulo 4) -- no duplicar esta logica en ningun otro
lado. Es una funcion de dominio pura: no depende de FastAPI (nada de `Request` ni
`HTTPException`), asi que cada caller resuelve su propia autenticacion y su propio
mapeo de error->respuesta a partir de las excepciones de dominio de abajo.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class CampaniaActivarError(Exception):
    """Base de los errores de dominio de activar_campania_core."""


class CampaniaNoEncontradaError(CampaniaActivarError):
    pass


class CampaniaSinAccionesError(CampaniaActivarError):
    pass


class SinSucursalesValidasError(CampaniaActivarError):
    pass


async def activar_campania_core(
    client: Any,
    meta_client: Any,
    campania_id: str,
    sucursal_ids: List[str],
    plazo_dias: int = 14,
) -> Dict[str, Any]:
    """Genera las tareas de campania (accion x sucursal) para las sucursales elegidas,
    activa la campania, y dispara el fan-out de WhatsApp. El envio es best-effort:
    requiere el template `campana_nueva_sucursal` aprobado en Meta Business Manager
    (ARQUITECTURA_DESVIOS_CAMPANIAS.md, seccion 2.4 bis) -- si falla, se loguea y se
    sigue sin bloquear la activacion (mismo criterio que el resto del bot, p. ej.
    `send_alerta_coordinador`). Devuelve {"tareas_creadas": N}.
    """
    if not sucursal_ids:
        raise ValueError("Selecciona al menos una sucursal")

    campania_response = client.table("campanias").select("*").eq("id", campania_id).maybe_single().execute()
    campania = campania_response.data
    if not campania:
        raise CampaniaNoEncontradaError(campania_id)

    acciones_response = client.table("campania_acciones").select("*").eq("campania_id", campania_id).execute()
    acciones = acciones_response.data or []
    if not acciones:
        raise CampaniaSinAccionesError(campania_id)

    sucursales_response = (
        client.table("sucursales")
        .select("id, nombre, responsable, tel_responsable")
        .in_("id", sucursal_ids)
        .execute()
    )
    sucursales = {row["id"]: row for row in (sucursales_response.data or [])}

    plazo_fecha = (datetime.now(timezone.utc) + timedelta(days=plazo_dias)).strftime("%Y-%m-%d")

    tareas_nuevas = []
    for sucursal_id in sucursal_ids:
        sucursal = sucursales.get(sucursal_id)
        if not sucursal:
            continue
        for accion in acciones:
            tareas_nuevas.append({
                "campania_id": campania_id,
                "accion_id": accion["id"],
                "id_sucursal": sucursal_id,
                "responsable": sucursal.get("responsable"),
                "tel_responsable": sucursal.get("tel_responsable"),
                "estado": "Pendiente",
                "plazo_fecha": plazo_fecha,
            })

    if not tareas_nuevas:
        raise SinSucursalesValidasError(campania_id)

    client.table("campanias").update({
        "estado": "Activa",
        "fecha_inicio": campania.get("fecha_inicio") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }).eq("id", campania_id).execute()

    client.table("campania_tareas").insert(tareas_nuevas).execute()

    tareas_por_sucursal: Dict[str, int] = {}
    for tarea in tareas_nuevas:
        tareas_por_sucursal[tarea["id_sucursal"]] = tareas_por_sucursal.get(tarea["id_sucursal"], 0) + 1

    campania_nombre = campania.get("nombre") or "campania"
    for sucursal_id, cantidad in tareas_por_sucursal.items():
        sucursal = sucursales.get(sucursal_id) or {}
        telefono = "".join(ch for ch in str(sucursal.get("tel_responsable") or "") if ch.isdigit())
        if not telefono:
            continue
        sent = await meta_client.send_template(
            telefono,
            "campana_nueva_sucursal",
            body_params=[sucursal.get("nombre") or "", campania_nombre, str(cantidad)],
        )
        if not sent:
            logger.warning(
                f"No se pudo enviar el template de campania a la sucursal {sucursal_id} "
                f"(campania {campania_id}) — probablemente el template no esta aprobado aun en Meta."
            )

    return {"tareas_creadas": len(tareas_nuevas)}

"""Archiva hallazgos de desvios_borrador que nadie triage nunca.

El bot inserta un hallazgo con estado='pendiente' (save_perfumeria_desvio_borrador
en supabase_manager.py) y ahi se queda para siempre — no hay TTL ni limpieza
automatica (etapa-10-desvios-borrador.sql). Sin este job, "Requiere tu
decision" acumula backlog sin fin (encontrado: 89 items, algunos de meses).

Este job junta los que llevan mas de ARCHIVO_DIAS sin revisar, arma un PDF
por sucursal (generate_hallazgos_archivados_pdf) y los pasa a
estado='descartado' con el path del PDF en metadata_json — no hace falta
migracion de esquema, el CHECK de `estado` ya admite 'descartado' y
metadata_json/razon_descarte ya existen. El path se re-firma desde el
frontend con getSignedUrl (mismo mecanismo que ficha.google_drive_id).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from audit_pdf_generator import generate_hallazgos_archivados_pdf
from supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

# Cuanto tiene que llevar sin revisar un hallazgo para considerarse
# abandonado. Coincide con el filtro de 30 dias que aplica el frontend a la
# cola activa (getDesviosBorrador en lib/api.ts) — lo que uno acota, el otro
# lo cierra, para que no vuelva a acumularse fuera de la vista.
ARCHIVO_DIAS = 30

RAZON_ARCHIVADO = "Archivado automáticamente — hallazgo sin revisar de más de 30 días"


def _evidencia_bytes(db: SupabaseManager, evidencias: List[Dict[str, Any]]) -> bytes | None:
    """La primera evidencia de imagen del hallazgo, si hay. Best-effort: un
    error de descarga no debe frenar el archivado del hallazgo."""
    for ev in evidencias or []:
        if not (ev.get("path") and (ev.get("tipo") == "image" or str(ev.get("mime_type", "")).startswith("image/"))):
            continue
        bucket = ev.get("bucket") or "auditoria-respuestas"
        try:
            return db.client.storage.from_(bucket).download(ev["path"])
        except Exception as e:
            logger.warning(f"No se pudo descargar evidencia {ev['path']} de {bucket}: {e}")
            return None
    return None


async def archivar_hallazgos_antiguos() -> Dict[str, Any]:
    """Busca desvios_borrador pendientes de mas de ARCHIVO_DIAS, genera un PDF
    por sucursal y los archiva. Pensado para correr una vez al dia (ver
    registro en main.py) y tambien disparable a demanda via
    POST /admin/archivar-hallazgos/run para el backlog ya acumulado."""
    resumen = {"sucursales_procesadas": 0, "hallazgos_archivados": 0, "fallidos": 0}
    try:
        db = SupabaseManager()
        corte = (datetime.now(timezone.utc) - timedelta(days=ARCHIVO_DIAS)).isoformat()

        borradores_resp = (
            db.client.table("desvios_borrador")
            .select("id, id_sucursal, sucursal, bloque_nombre, descripcion, severidad_sugerida, evidencias_json, metadata_json, created_at")
            .eq("estado", "pendiente")
            .lt("created_at", corte)
            .execute()
        )
        borradores = borradores_resp.data or []
        if not borradores:
            return resumen

        # Sin id_sucursal no hay a que sucursal atribuir el PDF — se dejan
        # pendientes (caso raro: hallazgo pre-etapa-10 o sucursal borrada).
        por_sucursal: Dict[str, List[Dict[str, Any]]] = {}
        for b in borradores:
            if not b.get("id_sucursal"):
                continue
            por_sucursal.setdefault(b["id_sucursal"], []).append(b)

        for id_sucursal, grupo in por_sucursal.items():
            sucursal_nombre = grupo[0].get("sucursal") or id_sucursal
            items = []
            for b in grupo:
                items.append({
                    "descripcion": b.get("descripcion"),
                    "severidad": b.get("severidad_sugerida"),
                    "bloque_nombre": b.get("bloque_nombre"),
                    "creado_at": b.get("created_at"),
                    "foto_bytes": _evidencia_bytes(db, b.get("evidencias_json") or []),
                })

            try:
                pdf_bytes = generate_hallazgos_archivados_pdf(sucursal_nombre, items)
                upload = db.upload_borrador_archivado_pdf(id_sucursal, pdf_bytes)
            except Exception as e:
                logger.error(f"No se pudo generar/subir el archivo de hallazgos para {id_sucursal}: {e}")
                resumen["fallidos"] += len(grupo)
                continue

            ahora = datetime.now(timezone.utc).isoformat()
            for b in grupo:
                metadata = dict(b.get("metadata_json") or {})
                metadata["archivo_historico_path"] = upload["path"]
                metadata["archivo_historico_bucket"] = upload["bucket"]
                db.client.table("desvios_borrador").update({
                    "estado": "descartado",
                    "descartado_at": ahora,
                    "razon_descarte": RAZON_ARCHIVADO,
                    "metadata_json": metadata,
                }).eq("id", b["id"]).execute()

            resumen["sucursales_procesadas"] += 1
            resumen["hallazgos_archivados"] += len(grupo)

        logger.info(f"Archivado de hallazgos antiguos: {resumen}")
        return resumen
    except Exception as e:
        logger.error(f"Error en job de archivado de hallazgos: {e}", exc_info=True)
        resumen["fallidos"] += 1
        return resumen

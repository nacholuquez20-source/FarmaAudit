"""Circuito de vuelta: el auditor se entera de que un encargado respondio.

El encargado responde por WhatsApp (router.py:_handle_encargado_respuesta),
que guarda cada mensaje/foto en desvio_eventos con metadata.origen='sucursal'.
Hasta aca ya funcionaba. Lo que faltaba: avisarle al AUDITOR — hoy solo se
entera si abre el panel (campanita in-app).

Este modulo agrupa esas respuestas por (sucursal, auditor) y, despues de un
periodo sin actividad nueva (para no mandar un WhatsApp por cada mensaje
suelto si el encargado esta resolviendo varios desvios seguidos), genera un
PDF que enfrenta lo detectado contra lo respondido y se lo manda al auditor.

Ver plan en memoria del proyecto ("circuito de vuelta", etapas A-D). Etapa A
(audit_fiches.auditor_telefono) y Etapa C (generate_respuestas_pdf) ya estan
hechas; este archivo es la Etapa B (el job) + Etapa D (la entrega).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from audit_pdf_generator import generate_respuestas_pdf
from identity import resolve_responsable_by_sucursal, resolve_whatsapp_user, ventana_abierta
from meta_client import MetaClient
from supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

# Cuanto esperar sin actividad nueva del encargado antes de cortar y generar
# el informe. Si sigue respondiendo, el reloj se reinicia (el corte se calcula
# contra el evento mas nuevo, no contra el mas viejo) — asi una sesion donde
# resuelve 4 desvios seguidos genera un solo informe, no cuatro.
DEBOUNCE_MINUTOS = 45

# Cuanto atras mirar en desvio_eventos para no escanear la tabla entera en
# cada corrida. 30 dias es generoso: si el job estuvo caido mas que eso hay un
# problema operativo mas grande que notar aparte, no algo que este limite deba
# resolver.
LOOKBACK_DIAS = 30

# tipos de evento que corresponden a una respuesta del encargado (ver
# save_encargado_evento en router.py — nunca usa tipo='respuesta', eso es del
# panel web). Se filtra ademas por metadata.origen == 'sucursal' en Python:
# resolver jsonb ->> desde supabase-py no tiene un patron ya probado en este
# codebase, y el volumen de esta tabla no amerita optimizarlo.
TIPOS_RESPUESTA_ENCARGADO = ("mensaje", "evidencia")


def _download_bytes(url: str) -> Optional[bytes]:
    if not url:
        return None
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, follow_redirects=True)
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        logger.warning(f"No se pudo descargar {url}: {e}")
        return None


def _mapear_auditor_telefono(db: SupabaseManager, gestion_ids: List[str]) -> Dict[str, Optional[str]]:
    """Para cada id_gestion, resuelve el telefono del auditor via su ficha
    (gestion.ficha_id -> audit_fiches.auditor_telefono). Gestiones sin
    ficha_id (previas al Bloque 2) o cuya ficha no tiene auditor_telefono
    resuelto (historicas, nombre ambiguo) mapean a None — el caller decide
    que hacer (hoy: descartarlas del envio por WhatsApp)."""
    if not gestion_ids:
        return {}
    gestiones_resp = (
        db.client.table("gestion")
        .select("id_gestion, ficha_id")
        .in_("id_gestion", gestion_ids)
        .execute()
    )
    gestiones_by_id = {g["id_gestion"]: g for g in (gestiones_resp.data or [])}

    ficha_ids = sorted({g["ficha_id"] for g in gestiones_by_id.values() if g.get("ficha_id")})
    auditor_telefono_by_ficha: Dict[str, Optional[str]] = {}
    if ficha_ids:
        fichas_resp = (
            db.client.table("audit_fiches")
            .select("id, auditor_telefono")
            .in_("id", ficha_ids)
            .execute()
        )
        auditor_telefono_by_ficha = {f["id"]: f.get("auditor_telefono") for f in (fichas_resp.data or [])}

    return {
        id_gestion: (auditor_telefono_by_ficha.get(g["ficha_id"]) if g.get("ficha_id") else None)
        for id_gestion, g in gestiones_by_id.items()
    }


def _filtrar_eventos_nuevos(
    db: SupabaseManager,
    id_sucursal: str,
    auditor_telefono: str,
    eventos_por_gestion: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Descarta eventos ya cubiertos por un informe anterior de este mismo
    (sucursal, auditor) — mismo criterio para el job de fondo y el disparo
    inmediato, asi nunca se duplica un hallazgo entre los dos caminos."""
    ultimo_informe_resp = (
        db.client.table("informes_respuesta")
        .select("corte_at")
        .eq("id_sucursal", id_sucursal)
        .eq("auditor_telefono", auditor_telefono)
        .order("corte_at", desc=True)
        .limit(1)
        .execute()
    )
    ultimo_corte = None
    if ultimo_informe_resp.data:
        ultimo_corte = datetime.fromisoformat(ultimo_informe_resp.data[0]["corte_at"].replace("Z", "+00:00"))

    eventos_pendientes: Dict[str, List[Dict[str, Any]]] = {}
    for id_gestion, eventos_gestion in eventos_por_gestion.items():
        nuevos = eventos_gestion
        if ultimo_corte:
            nuevos = [
                e for e in eventos_gestion
                if datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")) > ultimo_corte
            ]
        if nuevos:
            eventos_pendientes[id_gestion] = nuevos
    return eventos_pendientes


def _consolidar_respuesta(eventos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """De todos los eventos de un desvio dentro de la ventana, arma una sola
    respuesta: el comentario es la concatenacion en orden (el encargado puede
    mandar texto y despues una foto, o varias fotos con distinto comentario
    cada una) y la foto es la ultima que haya, porque es la mas probable de
    ser la correccion final."""
    comentarios = [e["comentario"] for e in eventos if e.get("comentario")]
    foto_path = None
    for e in eventos:
        metadata = e.get("metadata") or {}
        if metadata.get("foto_path"):
            foto_path = metadata["foto_path"]
    ultimo = max(eventos, key=lambda e: datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")))
    return {
        "comentario": " ".join(comentarios) if comentarios else None,
        "foto_path": foto_path,
        "respuesta_at": ultimo["created_at"],
    }


async def _generar_y_enviar_informe(
    db: SupabaseManager,
    meta_client: MetaClient,
    id_sucursal: str,
    auditor_telefono: str,
    gestion_ids: List[str],
    eventos_por_gestion: Dict[str, List[Dict[str, Any]]],
    corte_at: str,
) -> Dict[str, Any]:
    """Genera el PDF de un grupo (sucursal, auditor) ya decidido y lo manda.
    Siempre registra el intento en informes_respuesta, incluso si no llega a
    enviar nada — mismo principio que _enviar_recordatorio_sucursal: que "el
    job falla en silencio" no vuelva a ser cierto."""

    sucursal = db.get_sucursal(id_sucursal)
    sucursal_nombre = sucursal.nombre if sucursal else id_sucursal

    responsable = resolve_responsable_by_sucursal(id_sucursal)
    encargado_nombre = responsable.nombre if responsable else None

    gestiones_resp = (
        db.client.table("gestion")
        .select("id_gestion, desvio, severidad, created_at, id_reporte")
        .in_("id_gestion", gestion_ids)
        .execute()
    )
    gestiones_by_id = {g["id_gestion"]: g for g in (gestiones_resp.data or [])}

    reporte_ids = [g["id_reporte"] for g in gestiones_by_id.values() if g.get("id_reporte")]
    reportes_by_id: Dict[str, Any] = {}
    if reporte_ids:
        reportes_resp = db.client.table("reportes").select("id, foto_url").in_("id", reporte_ids).execute()
        reportes_by_id = {r["id"]: r for r in (reportes_resp.data or [])}

    items = []
    for id_gestion in gestion_ids:
        gestion = gestiones_by_id.get(id_gestion)
        if not gestion:
            continue

        respuesta = _consolidar_respuesta(eventos_por_gestion[id_gestion])

        # reporte.foto_url es una URL de Meta capturada en el momento del
        # hallazgo — esas URLs vencen en cuestion de horas, mucho antes de que
        # el encargado llegue a responder. Se intenta igual (best-effort); si
        # ya vencio, el PDF simplemente no muestra la foto "detectado" y se
        # apoya en la descripcion + la foto de la respuesta, que si es
        # reciente (viene de Storage propio, no de Meta).
        foto_detectada_bytes = None
        reporte = reportes_by_id.get(gestion.get("id_reporte"))
        if reporte and reporte.get("foto_url"):
            foto_detectada_bytes = _download_bytes(reporte["foto_url"])

        respuesta_foto_bytes = None
        if respuesta["foto_path"]:
            signed = db.create_signed_evidencia_url(respuesta["foto_path"])
            if signed:
                respuesta_foto_bytes = _download_bytes(signed)

        items.append({
            "id_gestion": id_gestion,
            "desvio_descripcion": gestion.get("desvio"),
            "severidad": gestion.get("severidad"),
            "detectado_at": gestion.get("created_at"),
            "foto_detectada_bytes": foto_detectada_bytes,
            "respuesta_comentario": respuesta["comentario"],
            "respuesta_foto_bytes": respuesta_foto_bytes,
            "respuesta_at": respuesta["respuesta_at"],
        })

    if not items:
        # Puede pasar si las gestiones referenciadas ya no existen (borradas).
        # Se registra igual para no reintentar en el proximo ciclo.
        db.client.table("informes_respuesta").insert({
            "id_sucursal": id_sucursal,
            "auditor_telefono": auditor_telefono,
            "corte_at": corte_at,
            "gestion_ids": [],
            "estado": "fallido",
        }).execute()
        return {"resultado": "sin_items"}

    abiertos_resp = (
        db.client.table("gestion")
        .select("id_gestion", count="exact")
        .eq("id_sucursal", id_sucursal)
        .not_.in_("estado", ["Resuelta", "Cerrada"])
        .not_.in_("id_gestion", gestion_ids)
        .execute()
    )
    desvios_abiertos_restantes = abiertos_resp.count or 0

    auditor = resolve_whatsapp_user(auditor_telefono)
    auditor_nombre = auditor.nombre if auditor else None

    pdf_bytes = generate_respuestas_pdf(
        sucursal_nombre=sucursal_nombre,
        items=items,
        encargado_nombre=encargado_nombre,
        auditor_nombre=auditor_nombre,
        desvios_abiertos_restantes=desvios_abiertos_restantes,
    )

    try:
        upload_result = db.upload_informe_respuesta_pdf(id_sucursal, pdf_bytes)
        pdf_path = upload_result["path"]
    except Exception as e:
        logger.error(f"No se pudo subir el informe de respuestas para {id_sucursal}: {e}")
        db.client.table("informes_respuesta").insert({
            "id_sucursal": id_sucursal,
            "auditor_telefono": auditor_telefono,
            "corte_at": corte_at,
            "gestion_ids": gestion_ids,
            "estado": "fallido",
        }).execute()
        return {"resultado": "fallido"}

    estado = "sin_auditor"
    enviado_at = None

    if auditor is None:
        logger.warning(f"auditor_telefono {auditor_telefono} no resuelve en usuarios_whatsapp — informe queda solo en el panel.")
    else:
        signed_url = db.create_signed_informe_url(pdf_path)
        filename = f"Respuestas_{sucursal_nombre.replace(' ', '_')}.pdf"

        if ventana_abierta(auditor):
            caption = (
                f"📋 {encargado_nombre or 'El encargado'} respondió {len(items)} desvío(s) "
                f"en {sucursal_nombre}."
            )
            ok = await meta_client.send_document(auditor_telefono, signed_url, filename, caption=caption)
            if ok:
                estado = "enviado"
                enviado_at = datetime.now(timezone.utc).isoformat()
            else:
                estado = "fallido"
        else:
            # Plantilla ya aprobada, sin adjunto — el auditor entra al panel a
            # ver el PDF. Si le contesta al bot despues, se abre la ventana y
            # ahi si se le puede mandar el documento (no automatizado todavia:
            # ver nota en el plan sobre plantilla con header de documento).
            ok = await meta_client.send_template(
                auditor_telefono,
                "farmaaudit_novedades",
                language_code="es_AR",
                body_params=[auditor_nombre or "Auditor/a", str(len(items)), sucursal_nombre],
            )
            estado = "sin_ventana" if ok else "fallido"

    db.client.table("informes_respuesta").insert({
        "id_sucursal": id_sucursal,
        "auditor_telefono": auditor_telefono,
        "corte_at": corte_at,
        "gestion_ids": gestion_ids,
        "estado": estado,
        "pdf_path": pdf_path,
        "enviado_at": enviado_at,
    }).execute()

    return {"resultado": estado, "items": len(items)}


async def enviar_informes_respuesta() -> None:
    """Background job: agrupa respuestas de encargados sin informar todavia y,
    para los grupos que llevan mas de DEBOUNCE_MINUTOS sin actividad nueva,
    genera y manda el informe al auditor correspondiente. Pensado para correr
    cada 15 minutos (ver registro en main.py)."""
    try:
        db = SupabaseManager()
        desde = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DIAS)).isoformat()

        eventos_resp = (
            db.client.table("desvio_eventos")
            .select("id, id_gestion, tipo, comentario, metadata, created_at")
            .in_("tipo", list(TIPOS_RESPUESTA_ENCARGADO))
            .gte("created_at", desde)
            .order("created_at")
            .execute()
        )
        eventos = [
            e for e in (eventos_resp.data or [])
            if (e.get("metadata") or {}).get("origen") == "sucursal"
        ]
        if not eventos:
            return

        gestion_ids = sorted({e["id_gestion"] for e in eventos})
        gestiones_resp = (
            db.client.table("gestion")
            .select("id_gestion, id_sucursal, ficha_id")
            .in_("id_gestion", gestion_ids)
            .execute()
        )
        gestiones_by_id = {g["id_gestion"]: g for g in (gestiones_resp.data or [])}
        auditor_telefono_by_gestion = _mapear_auditor_telefono(db, gestion_ids)

        # Agrupar eventos por (id_sucursal, auditor_telefono). Gestiones sin
        # ficha_id (previas al Bloque 2) o cuya ficha no tiene auditor_telefono
        # resuelto (historicas, nombre ambiguo) se descartan del WhatsApp — el
        # encargado ya quedo registrado en desvio_eventos igual, solo no hay a
        # quien avisarle por este canal.
        grupos: Dict[tuple, Dict[str, Any]] = {}
        for evento in eventos:
            gestion = gestiones_by_id.get(evento["id_gestion"])
            if not gestion:
                continue
            auditor_telefono = auditor_telefono_by_gestion.get(evento["id_gestion"])
            if not auditor_telefono:
                continue

            key = (gestion["id_sucursal"], auditor_telefono)
            grupo = grupos.setdefault(key, {"eventos_por_gestion": {}})
            grupo["eventos_por_gestion"].setdefault(evento["id_gestion"], []).append(evento)

        if not grupos:
            return

        meta_client = MetaClient()
        procesados = 0

        for (id_sucursal, auditor_telefono), grupo in grupos.items():
            eventos_por_gestion = grupo["eventos_por_gestion"]

            # Filtrar a solo eventos posteriores al ultimo corte de ESTE grupo.
            eventos_pendientes = _filtrar_eventos_nuevos(db, id_sucursal, auditor_telefono, eventos_por_gestion)
            if not eventos_pendientes:
                continue

            todos_los_eventos = [e for lst in eventos_pendientes.values() for e in lst]
            candidato_corte = max(
                datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")) for e in todos_los_eventos
            )
            minutos_inactivo = (datetime.now(timezone.utc) - candidato_corte).total_seconds() / 60
            if minutos_inactivo < DEBOUNCE_MINUTOS:
                continue  # el encargado puede seguir respondiendo, se espera al proximo ciclo

            resultado = await _generar_y_enviar_informe(
                db, meta_client, id_sucursal, auditor_telefono,
                gestion_ids=sorted(eventos_pendientes.keys()),
                eventos_por_gestion=eventos_pendientes,
                corte_at=candidato_corte.isoformat(),
            )
            procesados += 1
            if resultado["resultado"] not in ("enviado", "sin_ventana"):
                logger.warning(f"Informe de respuestas para {id_sucursal}/{auditor_telefono}: {resultado['resultado']}")

        if procesados:
            logger.info(f"Informes de respuestas procesados: {procesados}")

    except Exception as e:
        logger.error(f"Error en job de informes de respuestas: {e}", exc_info=True)


async def generar_informe_inmediato_sucursal(id_sucursal: str, gestion_ids: List[str]) -> List[Dict[str, Any]]:
    """Dispara el informe de respuestas para una sucursal ahora mismo, sin
    esperar el debounce de enviar_informes_respuesta — se usa cuando el
    encargado termina de responder todos sus desvios pendientes en una sola
    sesion de WhatsApp (ver router.py:_continue_desvio_flow). El job de
    fondo sigue corriendo igual como red de seguridad para sesiones que
    quedan a medio terminar (el encargado corta y no vuelve a escribir).

    gestion_ids: las gestiones que el encargado toco en esta sesion. Pueden
    corresponder a mas de un auditor (desvios de auditorias viejas todavia
    abiertas) — se agrupan y, si hace falta, se manda mas de un PDF."""
    if not gestion_ids:
        return []
    try:
        db = SupabaseManager()

        eventos_resp = (
            db.client.table("desvio_eventos")
            .select("id, id_gestion, tipo, comentario, metadata, created_at")
            .in_("id_gestion", gestion_ids)
            .in_("tipo", list(TIPOS_RESPUESTA_ENCARGADO))
            .order("created_at")
            .execute()
        )
        eventos = [
            e for e in (eventos_resp.data or [])
            if (e.get("metadata") or {}).get("origen") == "sucursal"
        ]
        if not eventos:
            return []

        auditor_telefono_by_gestion = _mapear_auditor_telefono(db, gestion_ids)

        grupos: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for evento in eventos:
            auditor_telefono = auditor_telefono_by_gestion.get(evento["id_gestion"])
            if not auditor_telefono:
                continue
            grupo = grupos.setdefault(auditor_telefono, {})
            grupo.setdefault(evento["id_gestion"], []).append(evento)

        if not grupos:
            return []

        meta_client = MetaClient()
        resultados = []

        for auditor_telefono, eventos_por_gestion in grupos.items():
            eventos_pendientes = _filtrar_eventos_nuevos(db, id_sucursal, auditor_telefono, eventos_por_gestion)
            if not eventos_pendientes:
                continue

            todos_los_eventos = [e for lst in eventos_pendientes.values() for e in lst]
            corte_at = max(
                datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")) for e in todos_los_eventos
            ).isoformat()

            resultado = await _generar_y_enviar_informe(
                db, meta_client, id_sucursal, auditor_telefono,
                gestion_ids=sorted(eventos_pendientes.keys()),
                eventos_por_gestion=eventos_pendientes,
                corte_at=corte_at,
            )
            resultados.append(resultado)
            if resultado["resultado"] not in ("enviado", "sin_ventana"):
                logger.warning(f"Informe inmediato para {id_sucursal}/{auditor_telefono}: {resultado['resultado']}")

        return resultados
    except Exception as e:
        logger.error(f"Error generando informe inmediato para {id_sucursal}: {e}", exc_info=True)
        return []

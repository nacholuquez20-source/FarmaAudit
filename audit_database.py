"""Database integration for audit sessions."""

import logging
from typing import Optional, Dict
from datetime import datetime, date, timedelta, timezone
from audit_session import AuditSession, BloqueType, BLOQUE_LABELS, BRAND_LABELS
from identity import resolve_responsable_by_sucursal
from models import Reporte, Gestion, Severidad, GestionState
from supabase_manager import SupabaseManager
from meta_client import MetaClient

logger = logging.getLogger(__name__)


def determine_severity(score: int) -> Severidad:
    """Determine severity level based on bloque score (1-5)."""
    if score <= 2:
        return Severidad.ALTA  # Very bad
    elif score <= 3:
        return Severidad.MEDIA  # Medium
    else:
        return Severidad.BAJA  # Minor or good


def determine_overall_severity(session: AuditSession) -> Severidad:
    """Determine overall severity from all bloque scores."""
    if not session.bloques:
        return Severidad.MEDIA

    scores = list(session.bloques.values())
    avg_score = sum(scores) / len(scores)

    if avg_score <= 2:
        return Severidad.ALTA
    elif avg_score <= 3:
        return Severidad.MEDIA
    else:
        return Severidad.BAJA


async def save_audit_to_database(
    session: AuditSession, meta_client: MetaClient
) -> Dict[str, str]:
    """Save completed audit session to database.

    Creates Reporte + Gestion records for each deviation found.
    Returns dict with id_reporte and id_gestion.
    """
    try:
        db = SupabaseManager()

        # Get sucursal info for responsible party
        sucursal = db.get_sucursal(session.sucursal_id)
        if not sucursal:
            logger.warning(f"Sucursal {session.sucursal_id} not found in database")

        results = []

        # Create records for each desvio found
        if session.desvios:
            for desvio in session.desvios:
                bloque = desvio.bloque or "UNKNOWN"
                bloque_label = BLOQUE_LABELS.get(bloque, bloque)

                # Determine severity from bloque score
                bloque_score = session.bloques.get(bloque, 3)
                severity = determine_severity(bloque_score)

                # Find associated foto URL if available. Preferir la foto
                # ligada especificamente a este desvio (desvio.fotos) — antes
                # tomaba "la primera foto del bloque" sin importar a cual
                # hallazgo correspondia, lo que con evidencia por marca
                # mostraría la foto de una marca en el reporte de otra.
                foto_url = None
                fotos_by_id = {f.id: f for f in session.fotos}
                for foto_id in desvio.fotos:
                    foto = fotos_by_id.get(foto_id)
                    if foto and foto.media_url:
                        foto_url = foto.media_url
                        break

                if not foto_url:
                    for foto in session.fotos:
                        if foto.bloque == bloque and foto.media_url:
                            foto_url = foto.media_url
                            break

                # Create Reporte
                hoy = date.today().isoformat()
                hora = datetime.now(timezone.utc).strftime("%H:%M")

                marca_label = BRAND_LABELS.get(desvio.marca, desvio.marca) if desvio.marca else None
                area = f"Perfumeria - {bloque_label}" + (f" ({marca_label})" if marca_label else "")

                reporte = Reporte(
                    id="",  # Will be generated
                    fecha=hoy,
                    hora=hora,
                    cuadrilla="",
                    auditor=session.auditor_nombre or "Auditor",
                    id_sucursal=session.sucursal_id,
                    sucursal=sucursal.nombre if sucursal else session.sucursal_id,
                    area=area,
                    subitem="",
                    descripcion=desvio.descripcion,
                    severidad=severity,
                    foto_url=foto_url,
                    creado_por_audio=False,
                    marca=desvio.marca,
                )

                reporte_id = db.create_reporte(reporte)
                logger.info(f"Created reporte {reporte_id} for {bloque}")

                # Create Gestion (action plan)
                plazo = date.today() + timedelta(days=7)
                gestion = Gestion(
                    id_gestion="",  # Will be generated
                    id_reporte=reporte_id,
                    id_sucursal=session.sucursal_id,
                    sucursal=sucursal.nombre if sucursal else session.sucursal_id,
                    desvio=f"{bloque_label}" + (f" ({marca_label})" if marca_label else "") + f": {desvio.descripcion}",
                    severidad=severity,
                    responsable=sucursal.responsable if sucursal else "",
                    tel_responsable=sucursal.tel_responsable if sucursal else "",
                    plazo_fecha=plazo,
                    plan_accion="[Por definir por el responsable]",
                    estado=GestionState.ABIERTA,
                    bloque=bloque,
                    marca=desvio.marca,
                )

                gestion_id = db.create_gestion(gestion)
                logger.info(f"Created gestion {gestion_id} for desvio in {bloque}")

                # Save evento log
                db.save_encargado_evento(
                    id_gestion=gestion_id,
                    tipo="auditor_hallazgo",
                    contenido=f"Hallazgo encontrado durante auditoría: {desvio.descripcion}",
                    actor_nombre=session.auditor_nombre or "Auditor",
                    metadata={
                        "origen": "whatsapp_audit_v2",
                        "audit_session_id": session.id_sesion,
                        "bloque": bloque,
                        "bloque_score": bloque_score,
                        "fotos_count": len([f for f in session.fotos if f.bloque == bloque]),
                        "marca": desvio.marca,
                    },
                )

                results.append({"id_reporte": reporte_id, "id_gestion": gestion_id})

        # If no desvios but audit completed, create one record for completeness
        if not results:
            hoy = date.today().isoformat()
            hora = datetime.now(timezone.utc).strftime("%H:%M")

            # Create summary reporte
            overall_severity = determine_overall_severity(session)
            summary_bloques = ", ".join(
                [
                    f"{BLOQUE_LABELS.get(b, b)}: {s}/5"
                    for b, s in session.bloques.items()
                ]
            )

            reporte = Reporte(
                id="",
                fecha=hoy,
                hora=hora,
                cuadrilla="",
                auditor=session.auditor_nombre or "Auditor",
                id_sucursal=session.sucursal_id,
                sucursal=sucursal.nombre if sucursal else session.sucursal_id,
                area="Perfumeria - Resumen",
                subitem="",
                descripcion=f"Auditoría completada sin hallazgos críticos. {summary_bloques}",
                severidad=overall_severity,
                foto_url=None,
                creado_por_audio=False,
            )

            reporte_id = db.create_reporte(reporte)
            logger.info(f"Created summary reporte {reporte_id}")

            # Create summary gestion
            plazo = date.today() + timedelta(days=7)
            gestion = Gestion(
                id_gestion="",
                id_reporte=reporte_id,
                id_sucursal=session.sucursal_id,
                sucursal=sucursal.nombre if sucursal else session.sucursal_id,
                desvio="Auditoría de Perfumeria - Resumen",
                severidad=overall_severity,
                responsable=sucursal.responsable if sucursal else "",
                tel_responsable=sucursal.tel_responsable if sucursal else "",
                plazo_fecha=plazo,
                plan_accion="[Monitorear scores para mantener calidad]",
                estado=GestionState.ABIERTA,
            )

            gestion_id = db.create_gestion(gestion)
            logger.info(f"Created summary gestion {gestion_id}")

            results.append({"id_reporte": reporte_id, "id_gestion": gestion_id})

        logger.info(f"Saved {len(results)} reporte/gestion records for session {session.id_sesion}")
        return (
            {**results[0], "gestion_ids": [r["id_gestion"] for r in results]}
            if results
            else {"id_reporte": "", "id_gestion": "", "gestion_ids": []}
        )

    except Exception as e:
        logger.error(f"Error saving audit to database: {e}")
        raise


async def get_previous_audit(sucursal_id: str) -> Optional[Dict]:
    """Get bloque scores from the most recent COMPLETED audit for a sucursal.

    Returns dict {bloque: score}, or None if no previous audit. La auditoria
    en curso todavia no tiene fila en audit_fiches (esa se crea recien al
    confirmar al final, ver audit_fiches_manager.py), asi que no hace falta
    "saltear la actual" — la mas reciente en la tabla siempre es una anterior.
    """
    try:
        db = SupabaseManager()

        response = db.client.table("audit_fiches").select(
            "bloques_json"
        ).eq("sucursal_id", sucursal_id).order(
            "fecha_auditoria", desc=True
        ).limit(1).execute()

        records = response.data if response.data else []
        if not records:
            return None

        return records[0].get("bloques_json") or None

    except Exception as e:
        logger.warning(f"Could not fetch previous audit for {sucursal_id}: {e}")
        return None


async def send_manager_notification(
    telefono: str,
    sucursal_id: str,
    meta_client: MetaClient,
    auditor_nombre: Optional[str] = None,
    desvio_count: int = 0,
) -> bool:
    """Send WhatsApp notification to branch manager about audit completion.

    Only covers the desvio_count == 0 case ("todo en orden") — cuando hay
    desvíos, el aviso con el detalle lo manda
    _notify_responsable_desvios_pendientes más adelante en el flujo, así que
    mandar algo acá también sería un segundo mensaje casi idéntico.
    """
    if desvio_count > 0:
        return True

    try:
        db = SupabaseManager()
        sucursal = db.get_sucursal(sucursal_id)

        # Resuelto en vivo (identity.resolve_responsable_by_sucursal), no
        # sucursal.tel_responsable — ese campo queda vacío o desactualizado
        # para la mayoría de las sucursales (ver Bloque 3 del circuito de
        # vuelta y el fix en gestion_revision.py).
        responsable = resolve_responsable_by_sucursal(sucursal_id)
        if not responsable or not responsable.telefono:
            logger.warning(f"No manager phone for sucursal {sucursal_id}")
            return False

        message = (
            f"📋 Se auditó {sucursal.nombre if sucursal else sucursal_id} hoy "
            f"({datetime.now(timezone.utc).strftime('%d/%m/%Y')}), "
            f"a cargo de {auditor_nombre or 'el equipo de auditoría'}.\n\n"
            f"✅ No se encontraron desvíos. ¡Felicitaciones al equipo!"
        )

        return await meta_client.send_text(responsable.telefono, message)

    except Exception as e:
        logger.error(f"Error sending manager notification: {e}")
        return False

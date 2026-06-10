"""Database integration for audit sessions."""

import logging
from typing import Optional, Dict
from datetime import datetime, date, timedelta, timezone
from audit_session import AuditSession, BloqueType, BLOQUE_LABELS
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

                # Find associated foto URL if available
                foto_url = None
                for foto in session.fotos:
                    if foto.bloque == bloque and foto.media_url:
                        foto_url = foto.media_url
                        break

                # Create Reporte
                hoy = date.today().isoformat()
                hora = datetime.now(timezone.utc).strftime("%H:%M")

                reporte = Reporte(
                    id="",  # Will be generated
                    fecha=hoy,
                    hora=hora,
                    cuadrilla="",
                    auditor=session.auditor_nombre or "Auditor",
                    id_sucursal=session.sucursal_id,
                    sucursal=sucursal.nombre if sucursal else session.sucursal_id,
                    area=f"Perfumeria - {bloque_label}",
                    subitem="",
                    descripcion=desvio.descripcion,
                    severidad=severity,
                    foto_url=foto_url,
                    creado_por_audio=False,
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
                    desvio=f"{bloque_label}: {desvio.descripcion}",
                    severidad=severity,
                    responsable=sucursal.responsable if sucursal else "",
                    tel_responsable=sucursal.tel_responsable if sucursal else "",
                    plazo_fecha=plazo,
                    plan_accion="[Por definir por el responsable]",
                    estado=GestionState.ABIERTA,
                    bloque=bloque,
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
        return results[0] if results else {"id_reporte": "", "id_gestion": ""}

    except Exception as e:
        logger.error(f"Error saving audit to database: {e}")
        raise


async def get_previous_audit(sucursal_id: str) -> Optional[Dict]:
    """Get the most recent previous audit for a sucursal.

    Returns dict with bloque scores from last audit, or None if no previous audit.
    """
    try:
        db = SupabaseManager()

        # Query for most recent reporte for this sucursal
        response = db.client.table("reporte").select(
            "id, sucursal_id, puntuaciones"
        ).eq("sucursal_id", sucursal_id).order(
            "created_at", desc=True
        ).limit(2).execute()

        records = response.data if response.data else []

        # Return the second most recent (skip current if in progress)
        if len(records) >= 2:
            prev_audit = records[1]
            puntuaciones = prev_audit.get("puntuaciones", {})
            return puntuaciones

        return None

    except Exception as e:
        logger.warning(f"Could not fetch previous audit for {sucursal_id}: {e}")
        return None


async def send_manager_notification(
    telefono: str, sucursal_id: str, meta_client: MetaClient
) -> bool:
    """Send WhatsApp notification to branch manager about audit completion."""
    try:
        db = SupabaseManager()
        sucursal = db.get_sucursal(sucursal_id)

        if not sucursal or not sucursal.tel_responsable:
            logger.warning(f"No manager phone for sucursal {sucursal_id}")
            return False

        message = f"""📋 Auditoría de Perfumería Completada

Sucursal: {sucursal.nombre}
Auditor: {telefono}
Fecha: {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')}

✅ Auditoría enviada con hallazgos pendientes de revisar.

Por favor revisar los detalles en el sistema.
"""

        return await meta_client.send_text(sucursal.tel_responsable, message)

    except Exception as e:
        logger.error(f"Error sending manager notification: {e}")
        return False

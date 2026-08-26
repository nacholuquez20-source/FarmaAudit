"""Message handlers for audit conversation states."""

import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import logging
from typing import Any, Dict, List, Optional, Tuple
from audit_session import (
    AuditSession, AuditState, create_session, get_session, save_session,
    delete_session, BloqueType, BLOQUE_ORDER, BRAND_ORDER,
    BLOQUE_LABELS, BRAND_LABELS, BLOQUE_DESCRIPTIONS, FotoEvidence,
)
from models import WhatsAppPayload
from meta_client import MetaClient
from photo_validator import PhotoValidator, PhotoValidationResult
from audio import AudioTranscriber
from audit_database import save_audit_to_database, send_manager_notification, get_previous_audit
from identity import normalize_phone, resolve_responsable_by_sucursal, ventana_abierta
from informes_respuesta import _consolidar_respuesta
from gestion_revision import aplicar_revision_gestion
from supabase_manager import SupabaseManager
from audit_pdf_generator import generate_audit_pdf
from audit_fiches_manager import AuditFichesManager
from config import get_settings
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


# Sí/No se comparan por TOKEN EXACTO, nunca por subcadena. El matcheo por
# subcadena hacía que "no sirve" confirmara la auditoría entera, porque "si"
# está contenido en "sirve".
_AFIRMATIVAS = {"si", "sí", "s", "yes", "confirmo", "confirmar", "enviar", "1"}
_NEGATIVAS = {"no", "n", "nop", "editar", "corregir", "cambiar", "modificar", "2"}

# Asentimientos que NO son contenido. Si el auditor escribe esto mientras se
# recolecta evidencia no está reportando un problema, está acusando recibo.
_ASENTIMIENTOS = {
    "ok", "oka", "okey", "okay", "dale", "listo", "gracias", "bien",
    "perfecto", "joya", "barbaro", "bárbaro", "dale gracias", "dale ok",
}


def _tokens(texto: str) -> set:
    """Palabras normalizadas del mensaje, sin puntuación."""
    limpio = "".join(c if (c.isalnum() or c.isspace()) else " " for c in texto.lower())
    return set(limpio.split())


def _es_negativo(texto: str) -> bool:
    if "❌" in texto:
        return True
    return bool(_tokens(texto) & _NEGATIVAS)


def _es_afirmativo(texto: str) -> bool:
    # La negativa gana: "no, editar" no puede leerse como un sí.
    if _es_negativo(texto):
        return False
    if "✅" in texto:
        return True
    return bool(_tokens(texto) & _AFIRMATIVAS)


def _es_asentimiento(texto: str) -> bool:
    """True si el mensaje es puro acuse de recibo y nada más."""
    t = _tokens(texto)
    return bool(t) and t <= _ASENTIMIENTOS


# Palabras que en el bloque OFERTAS son COMANDOS, nunca datos. Sin este guard,
# escribir "siguiente" cuando el bot pregunta "¿que marca es?" registraba una
# marca fantasma llamada "siguiente", con comentario "siguiente" (bug real de
# produccion, 2026-08-26). El comando ya estaba contemplado en el paso de la
# foto (handle_ofertas_marca_evidence) pero no en los dos pasos siguientes.
_COMANDOS_OFERTAS = {
    "siguiente", "next", "listo", "terminar", "fin", "seguir", "continuar",
}


def _es_comando_ofertas(texto: str) -> bool:
    """True si el texto es una orden de avanzar, no el nombre de una marca ni
    un comentario sobre ella."""
    return (texto or "").strip().lower() in _COMANDOS_OFERTAS


SCORE_OPTIONS = [
    {"id": "1", "title": "Muy malo", "description": "Crítico, acción inmediata"},
    {"id": "2", "title": "Malo", "description": "Problemas significativos"},
    {"id": "3", "title": "Regular", "description": "Necesita mejora"},
    {"id": "4", "title": "Bueno", "description": "Bien, algunos detalles"},
    {"id": "5", "title": "Excelente", "description": "Cumple perfectamente"},
]

# Botón ofrecido junto a cada confirmación de evidencia guardada (foto, audio,
# nota). El id "siguiente" no necesita manejo especial: main.py ya mapea
# button_reply.id -> payload.contenido con tipo="text", y el check de
# "SIGUIENTE" en handle_bloque_evidence usa .upper() sobre el contenido, así
# que "siguiente".upper() lo matchea sin tocar nada más.
SIGUIENTE_BUTTON = {"id": "siguiente", "title": "➡️ Siguiente"}

SEVERITY_ESCALATION = {"Baja": "Media", "Media": "Alta", "Alta": "Alta"}

# Cuanto extiende "pausar" el expires_at de la sesion, contado desde el
# momento en que se pausa (no desde que arranco la auditoria).
PAUSA_EXTENSION_HORAS = 72


async def _ficha_download_url(storage_path: str) -> str:
    """Mint a fresh signed URL for a ficha PDF stored in Supabase Storage.

    Storage is private — we generate a short-lived signed URL each time the
    file is actually needed (sent over WhatsApp, or opened from the admin
    panel) instead of relying on a permanently-public link.
    """
    if not storage_path:
        return storage_path
    db = SupabaseManager()
    signed_url = db.create_signed_ficha_url(storage_path)
    return signed_url or storage_path


async def _notify_responsable_desvios_pendientes(
    meta_client: MetaClient,
    session: AuditSession,
) -> None:
    """Send the branch manager a short heads-up (no PDF) that new desvíos were
    found. This is a best-effort safety net so the manager finds out even if
    the auditor never gets around to forwarding the full report personally —
    the detailed PDF + evidence is delivered by the auditor, not by this bot
    (see _send_forward_invitation_text).
    """
    try:
        # Resuelto en vivo, no sucursal.tel_responsable — ese campo queda
        # vacío o desactualizado para la mayoría de las sucursales (ver
        # Bloque 3 del circuito de vuelta y el fix en gestion_revision.py).
        responsable = resolve_responsable_by_sucursal(session.sucursal_id)
        tel = responsable.telefono if responsable else None
        if not tel:
            logger.info(f"No hay responsable resuelto para sucursal {session.sucursal_id} — skipping notice")
            return

        cantidad = len(session.desvios)
        texto = (
            f"📋 La auditoría de hoy encontró {cantidad} punto(s) para mejorar en tu sucursal.\n\n"
            f"Tu auditor/a te va a compartir el detalle con fotos y comentarios por WhatsApp. "
            f"A medida que resuelvas cada uno, escribinos a este mismo número para dejarlo registrado."
        )
        ok = await meta_client.send_text(tel, texto)
        if ok:
            logger.info(f"Short desvios notice sent to manager at {tel}")
        else:
            logger.warning(f"Failed to send desvios notice to manager at {tel}")
    except Exception as e:
        logger.warning(f"Could not notify responsable: {e}")


async def _send_forward_invitation_text(
    meta_client: MetaClient,
    session: AuditSession,
    telefono: str,
) -> None:
    """Send the auditor a ready-to-forward message (with the bot's number)
    to personally send to the branch manager along with the PDF, inviting
    them to write to the bot as they resolve each desvío.
    """
    try:
        db = SupabaseManager()
        sucursal = db.get_sucursal(session.sucursal_id)
        nombre = sucursal.nombre if sucursal else session.sucursal_id
        responsable = sucursal.responsable if sucursal else ""
        bot_phone = get_settings().bot_display_phone

        saludo = f"Hola {responsable}!" if responsable else "Hola!"
        mensaje_para_reenviar = (
            f"{saludo} Te comparto el informe de la auditoría de hoy en {nombre}, "
            f"con el detalle y las fotos de cada desvío encontrado.\n\n"
            f"Cuando vayas resolviendo cada uno, escribile directo a este bot de WhatsApp "
            f"({bot_phone}) para que quede registrado. ¡Gracias!"
        )

        intro = "📤 *Para reenviar al encargado junto con el PDF:*"
        await meta_client.send_text(telefono, intro)
        await meta_client.send_text(telefono, mensaje_para_reenviar)
    except Exception as e:
        logger.warning(f"Could not send forward-invitation text to auditor: {e}")


async def _ask_avisar_encargado(meta_client: MetaClient, telefono: str) -> None:
    """Ask the auditor whether the bot should send the ficha PDF directly to
    the sucursal's encargado, instead of leaving that to the auditor
    personally (ver _send_forward_invitation_text — el flujo anterior, que
    dependia de que el auditor la reenviara a mano y a veces nunca pasaba)."""
    await meta_client.send_quick_reply(
        telefono,
        "📤 ¿Querés que le mande yo el informe al encargado por WhatsApp ahora?",
        [
            {"id": "avisar_encargado_si", "title": "✅ Sí, mandalo"},
            {"id": "avisar_encargado_no", "title": "❌ No, yo lo mando"},
        ],
    )


async def _enviar_ficha_a_encargado(
    meta_client: MetaClient,
    session: AuditSession,
    telefono_auditor: str,
) -> None:
    """Send the ficha PDF directly to the sucursal's active encargado.

    Resuelve el responsable en vivo (identity.resolve_responsable_by_sucursal,
    no sucursal.tel_responsable — ese campo es una foto congelada, ver Bloque
    3 del circuito de vuelta). Si no hay responsable, o su ventana de 24h esta
    cerrada (Meta no entrega un documento fuera de ventana), degrada al texto
    para reenviar a mano en vez de fallar en silencio — el auditor siempre
    termina con alguna forma de avisarle al encargado.
    """
    ficha_url = session.ficha_url
    if not ficha_url:
        await meta_client.send_text(telefono_auditor, "⚠️ No encontré la ficha para mandarle al encargado.")
        return

    responsable = resolve_responsable_by_sucursal(session.sucursal_id)
    if not responsable or not responsable.telefono:
        await meta_client.send_text(
            telefono_auditor,
            "No hay un encargado cargado para esta sucursal, así que no te lo puedo mandar yo. "
            "Te paso el mensaje para que lo reenvíes vos:",
        )
        await _send_forward_invitation_text(meta_client, session, telefono_auditor)
        return

    if not ventana_abierta(responsable):
        await meta_client.send_text(
            telefono_auditor,
            f"{responsable.nombre or 'El encargado'} no le escribió al bot en las últimas 24h, así que no le "
            "puedo mandar el documento directo (Meta no entrega archivos fuera de esa ventana). "
            "Te paso el mensaje para que se lo reenvíes vos:",
        )
        await _send_forward_invitation_text(meta_client, session, telefono_auditor)
        return

    try:
        db = SupabaseManager()
        sucursal = db.get_sucursal(session.sucursal_id)
        nombre_sucursal = sucursal.nombre if sucursal else session.sucursal_id

        saludo = f"Hola {responsable.nombre}!" if responsable.nombre else "Hola!"
        caption = (
            f"{saludo} Te comparto el informe de la auditoría de hoy en {nombre_sucursal}, "
            f"con el detalle y las fotos de cada desvío encontrado."
        )
        filename = f"Auditoria_{session.id_sesion}.pdf"
        download_url = await _ficha_download_url(ficha_url)
        ok = await meta_client.send_document(responsable.telefono, download_url, filename, caption=caption)
    except Exception as e:
        logger.warning(f"Error sending ficha to encargado for {session.sucursal_id}: {e}")
        ok = False

    if ok:
        await meta_client.send_text(
            telefono_auditor,
            f"✅ Listo, le mandé el informe directo a {responsable.nombre or 'el encargado'}."
        )
    else:
        await meta_client.send_text(
            telefono_auditor,
            "⚠️ No pude mandarle el documento directo. Te paso el mensaje para que lo reenvíes vos:",
        )
        await _send_forward_invitation_text(meta_client, session, telefono_auditor)


async def _send_desvios_summary(
    meta_client: MetaClient,
    session: AuditSession,
    telefono: str,
) -> None:
    """Send a human-readable desvíos summary with photos to the auditor (best-effort)."""
    if not session.desvios:
        return
    try:
        # Build foto lookup
        foto_map = {f.id: f for f in session.fotos}

        # Score emoji helpers
        def score_icon(s: int) -> str:
            return "🔴" if s <= 2 else "🟡" if s == 3 else "🟢"

        def score_label(s: int) -> str:
            return {1: "Muy malo", 2: "Malo", 3: "Regular", 4: "Bueno", 5: "Excelente"}.get(s, "")

        # ── Header ──────────────────────────────────────────────────────────
        db = SupabaseManager()
        sucursal = db.get_sucursal(session.sucursal_id)
        nombre = sucursal.nombre if sucursal else session.sucursal_id
        fecha = ""
        if session.started_at:
            try:
                from datetime import datetime as _dt
                fecha = _dt.fromisoformat(session.started_at).strftime("%d/%m/%Y")
            except Exception:
                fecha = session.started_at

        scores_lines = "\n".join(
            f"  {score_icon(v)} {BLOQUE_LABELS.get(k, k)}: {v}/5 — {score_label(v)}"
            for k, v in session.bloques.items()
        )
        header = (
            f"📋 *RESUMEN DE AUDITORÍA*\n"
            f"Sucursal: {nombre}\n"
            f"📅 {fecha}   Auditor: {session.auditor_nombre or '—'}\n\n"
            f"*Puntuaciones:*\n{scores_lines}\n\n"
            f"*Desvíos encontrados: {len(session.desvios)}*"
        )
        await meta_client.send_text(telefono, header)

        # ── One block per desvío ─────────────────────────────────────────────
        for idx, desvio in enumerate(session.desvios, 1):
            bloque_label = BLOQUE_LABELS.get(desvio.bloque, desvio.bloque)
            score = session.bloques.get(desvio.bloque, 0)
            icon = score_icon(score)

            text = (
                f"{icon} *Desvío {idx} — {bloque_label}*\n"
                f"Puntaje: {score}/5 — {score_label(score)}\n\n"
                f"{desvio.descripcion}"
            )
            foto_ids = desvio.fotos or []
            has_photos = any(foto_map.get(fid) and foto_map[fid].media_id for fid in foto_ids)

            # Send description; include photo count note in caption if photos follow
            await meta_client.send_text(telefono, text)

            # Send each photo
            for foto_id in foto_ids:
                foto = foto_map.get(foto_id)
                if foto and foto.media_id:
                    caption = f"📸 Evidencia — {bloque_label} (desvío {idx})"
                    ok = await meta_client.send_image_by_id(telefono, foto.media_id, caption)
                    if not ok:
                        logger.warning(f"Could not resend photo {foto_id} for desvío {idx}")

        logger.info(f"Desvíos summary sent to auditor {telefono} ({len(session.desvios)} items)")
    except Exception as e:
        logger.warning(f"Could not send desvíos summary: {e}")


async def _ask_ficha_download(
    meta_client: MetaClient,
    telefono: str,
    session: AuditSession,
    ficha_url: str,
) -> None:
    """Store ficha URL on session and ask auditor if they want to receive it."""
    session.ficha_url = ficha_url
    save_session(session)
    await meta_client.send_quick_reply(
        telefono,
        "📄 La ficha de auditoría está lista.\n¿Querés recibirla aquí en WhatsApp?",
        [
            {"id": "descargar_ficha_si", "title": "✅ Sí, enviar"},
            {"id": "descargar_ficha_no", "title": "❌ No, gracias"},
        ],
    )


async def _send_ficha_to_auditor(
    meta_client: MetaClient,
    session: AuditSession,
    telefono: str,
) -> None:
    """Send the stored ficha PDF to the auditor as a WhatsApp document."""
    ficha_url: Optional[str] = session.ficha_url
    if not ficha_url:
        await meta_client.send_text(telefono, "⚠️ No encontré la ficha. Intentá de nuevo en unos segundos.")
        return

    filename = f"Auditoria_{session.id_sesion}.pdf"
    download_url = await _ficha_download_url(ficha_url)
    ok = await meta_client.send_document(
        telefono,
        download_url,
        filename,
        caption=f"📋 Ficha de auditoría — {session.id_sesion}",
    )
    if ok:
        logger.info(f"Ficha PDF sent to auditor {telefono}")
    else:
        await meta_client.send_text(
            telefono,
            f"⚠️ No pude enviar el archivo directamente.\nDescargalo desde:\n{download_url}",
        )


class AuditConversationHandler:
    """Handles audit conversation states and transitions."""

    @staticmethod
    async def handle_message(payload: WhatsAppPayload, meta_client: MetaClient) -> str:
        """Route message based on conversation state."""

        telefono = payload.telefono
        session = get_session(telefono)

        # No active session: start new or handle command
        if not session:
            if payload.tipo == "text":
                texto = payload.contenido.lower().strip()
                if any(word in texto for word in ["auditoria", "audit", "perfumeria", "farmacia"]):
                    return await AuditConversationHandler.handle_init(payload, meta_client)

            await meta_client.send_text(
                telefono,
                "Hola 👋\n\nPara iniciar una auditoría de perfumería escribí *auditoria*."
            )
            return "awaiting_start"

        # "cancelar" en medio de una auditoria (puntuando, cargando evidencia,
        # o confirmando) no se manejaba en absoluto: en SCORING/SCORING_BRANDS
        # tiraba "responde 1-5", y en BLOQUE_EVIDENCE_COLLECTION la palabra
        # "cancelar" se guardaba como si fuera un hallazgo real en la base.
        # Los demas estados (SELECT_SUCURSAL, VERIFY_*, DONE) ya tienen su
        # propio manejo de cancelar mas especifico, no se tocan.
        estados_sin_cancelar = {
            AuditState.SCORING,
            AuditState.SCORING_BRANDS,
            AuditState.SCORING_BRANDS_TAG,
            AuditState.SCORING_BRANDS_COMMENT,
            AuditState.BLOQUE_EVIDENCE_COLLECTION,
            AuditState.SUMMARY,
        }
        if session.estado in estados_sin_cancelar and payload.tipo == "text":
            texto_cancelar = payload.contenido.strip().lower()
            if texto_cancelar in {"cancelar", "cancel", "salir"}:
                delete_session(telefono)
                await meta_client.send_text(
                    telefono,
                    "Auditoría cancelada. Nada se guardó. Escribí *auditoria* para empezar de nuevo."
                )
                return "audit_cancelled"

            # "pausar": a diferencia de cancelar, NO borra nada. expires_at se
            # fija una sola vez al crear la sesion (created_at + 24h) y nunca
            # se extendia en ningun lado del codigo — un auditor que corta a
            # la tarde y vuelve al otro dia podia perder toda la auditoria en
            # curso sin ninguna forma de evitarlo. No hay comando "continuar"
            # explicito: cualquier mensaje ya retoma la maquina de estados
            # donde quedo, y agregar la palabra como comando especial
            # arriesgaba falsos positivos ("hay que continuar con el pedido"
            # es contenido real de un hallazgo, no una intencion de retomar).
            if texto_cancelar in {"pausar", "pausa"}:
                session.expires_at = (
                    datetime.now(timezone.utc) + timedelta(hours=PAUSA_EXTENSION_HORAS)
                ).isoformat()
                session.inactivity_notice_at = None
                save_session(session)
                await meta_client.send_text(
                    telefono,
                    "⏸️ Pausada. Tu auditoría queda guardada tal cual está — nada se pierde.\n\n"
                    "Mandá cualquier foto, audio o texto cuando quieras seguir, retomás justo donde quedaste."
                )
                return "audit_paused"

        # Active session: route by state
        if session.estado == AuditState.IDLE:
            return await AuditConversationHandler.handle_init(payload, meta_client)

        elif session.estado == AuditState.SELECT_SUCURSAL:
            return await AuditConversationHandler.handle_select_sucursal(payload, meta_client, session)

        elif session.estado == AuditState.VERIFY_SELECT_SUCURSAL:
            return await AuditConversationHandler.handle_verify_sucursal_selection(payload, meta_client, session)

        elif session.estado == AuditState.VERIFY_PREVIOUS:
            return await AuditConversationHandler.handle_verification(payload, meta_client, session)

        elif session.estado == AuditState.REVISION_BANDEJA:
            return await AuditConversationHandler.handle_revision_bandeja(payload, meta_client, session)

        elif session.estado == AuditState.SCORING:
            return await AuditConversationHandler.handle_score(payload, meta_client, session)

        elif session.estado == AuditState.BLOQUE_EVIDENCE_COLLECTION:
            return await AuditConversationHandler.handle_bloque_evidence(payload, meta_client, session)

        elif session.estado == AuditState.SCORING_BRANDS:
            return await AuditConversationHandler.handle_ofertas_marca_evidence(payload, meta_client, session)

        elif session.estado == AuditState.SCORING_BRANDS_TAG:
            return await AuditConversationHandler.handle_ofertas_marca_tag(payload, meta_client, session)

        elif session.estado == AuditState.SCORING_BRANDS_COMMENT:
            return await AuditConversationHandler.handle_ofertas_marca_comment(payload, meta_client, session)

        elif session.estado == AuditState.SUMMARY:
            return await AuditConversationHandler.handle_confirmation(payload, meta_client, session)

        elif session.estado == AuditState.DONE:
            # After audit complete, handle ficha requests or responsable input
            if payload.tipo == "text":
                texto = payload.contenido.lower().strip()

                # Quick-reply: auditor wants to download the ficha
                if texto == "descargar_ficha_si":
                    await _send_ficha_to_auditor(meta_client, session, payload.telefono)
                    delete_session(payload.telefono)
                    return "ficha_sent_to_auditor"

                # Quick-reply: auditor declined download
                if texto == "descargar_ficha_no":
                    await meta_client.send_text(payload.telefono, "¡Listo! La ficha queda guardada en el sistema. 👍")
                    delete_session(payload.telefono)
                    return "ficha_download_declined"

                # Quick-reply: auditor quiere que el bot le avise al encargado
                # directo (no borra la sesion — todavia puede quedar pendiente
                # la pregunta de si el auditor quiere su propia copia).
                if texto == "avisar_encargado_si":
                    await _enviar_ficha_a_encargado(meta_client, session, payload.telefono)
                    return "encargado_notified"

                if texto == "avisar_encargado_no":
                    await _send_forward_invitation_text(meta_client, session, payload.telefono)
                    return "encargado_notify_declined"

                # Salida explícita: sin esto una sesión en DONE quedaba viva
                # para siempre y el auditor no podía arrancar otra auditoría.
                if texto in {"cancelar", "salir", "cancel", "listo", "terminar"}:
                    delete_session(payload.telefono)
                    await meta_client.send_text(
                        payload.telefono,
                        "Listo, cerré la auditoría. Escribí *auditoria* cuando quieras arrancar otra."
                    )
                    return "audit_closed_by_user"

                # Keyword de ficha, por token exacto: "no quiero la ficha"
                # disparaba la descarga cuando se comparaba por subcadena.
                if _tokens(texto) & {"ficha", "pdf", "documento", "descargar"} and not _es_negativo(texto):
                    return await AuditConversationHandler.generate_and_send_ficha(
                        payload, meta_client, session
                    )

                # Check if user entered responsable name (when there are desvios)
                if session.desvios_responsable is None:
                    if len(session.desvios) > 0:
                        nombre = payload.contenido.strip()

                        # Antes se guardaba cualquier cosa: así terminó un "Ch"
                        # como responsable en audit_fiches. Se valida que
                        # parezca un nombre y no un acuse de recibo.
                        if len(nombre) < 3 or _es_asentimiento(texto) or nombre.isdigit():
                            await meta_client.send_text(
                                payload.telefono,
                                "Necesito el *nombre* de la persona responsable de los desvíos "
                                "(al menos 3 letras).\n\nEscribí 'cancelar' si preferís dejarlo para después."
                            )
                            return "invalid_responsable"

                        session.desvios_responsable = nombre

                        # Now that we have the responsable, generate the ficha
                        reporte_id = session.pending_ficha_reporte_id
                        ficha_url: Optional[str] = None
                        if reporte_id:
                            try:
                                ficha_url = await AuditFichesManager.generate_and_save_ficha(
                                    session=session,
                                    reporte_id=reporte_id,
                                    responsable_desvios=session.desvios_responsable,
                                    meta_client=meta_client,
                                )
                                logger.info(f"Ficha generated after responsable collected: {ficha_url}")
                            except Exception as ficha_exc:
                                logger.warning(f"Ficha generation failed: {ficha_exc}")

                        msg = f"✅ Desvíos asignados a: {session.desvios_responsable}"
                        await meta_client.send_text(payload.telefono, msg)

                        # Send desvíos summary with photos so auditor can forward to manager
                        await _send_desvios_summary(meta_client, session, payload.telefono)

                        if ficha_url:
                            # Short heads-up to the manager (no PDF) — best-effort
                            # safety net en caso de que el envio directo de abajo
                            # falle o el auditor prefiera reenviarlo el mismo.
                            await _notify_responsable_desvios_pendientes(meta_client, session)
                            # Preguntar si el bot le manda el PDF directo al
                            # encargado (en vez de depender de que el auditor lo
                            # reenvie a mano, que es el gap operativo real que
                            # esto cierra — ver _enviar_ficha_a_encargado).
                            await _ask_avisar_encargado(meta_client, payload.telefono)
                            # Ask auditor if they want the PDF too
                            await _ask_ficha_download(
                                meta_client, payload.telefono, session, ficha_url
                            )
                        else:
                            # Ficha generation failed — release session so user can start new audit
                            delete_session(payload.telefono)
                            await meta_client.send_text(
                                payload.telefono, "La ficha de auditoría fue guardada en el sistema."
                            )

                        return "responsable_saved"

            # Antes se caía acá en silencio y la sesión quedaba viva: el bot no
            # contestaba nada y el auditor no tenía forma de salir del estado.
            await meta_client.send_text(
                payload.telefono,
                "Esta auditoría ya está cerrada.\n\n"
                "Escribí *ficha* si querés el PDF, *auditoria* para arrancar una nueva, "
                "o *cancelar* para salir."
            )
            return "audit_already_completed"

        await meta_client.send_text(
            payload.telefono,
            "No entendí en qué punto quedamos. Escribí *cancelar* para empezar de cero."
        )
        return "unknown_state"

    @staticmethod
    async def _send_scoring_list(meta_client: MetaClient, telefono: str, session: AuditSession, intro: str = "") -> None:
        """Send the 1-5 scoring list message for the current bloque."""
        bloque = session.get_current_bloque()
        label = BLOQUE_LABELS.get(bloque, bloque)
        desc = BLOQUE_DESCRIPTIONS.get(bloque, "")
        body = f"{intro}{desc}\n\n¿Cuál es tu puntuación?"

        await meta_client.send_list_message(
            telefono,
            header=f"Paso {session.current_bloque_index + 1} de 4: {label}",
            body=body,
            footer="",
            button_text="Selecciona una opción",
            options=SCORE_OPTIONS,
        )

    @staticmethod
    def _queue_from_gestiones(gestiones: list) -> list:
        """Build the in-session verification queue from gestion rows."""
        return [
            {
                "id_gestion": g.get("id_gestion"),
                "desvio": g.get("desvio") or "",
                "severidad": g.get("severidad") or "Media",
                "estado": g.get("estado") or "Abierta",
                "plazo_fecha": g.get("plazo_fecha") or "",
                "bloque": g.get("bloque"),
            }
            for g in gestiones
        ]

    @staticmethod
    async def start_desvio_management(payload: WhatsAppPayload, meta_client: MetaClient, auditor_nombre: str = "") -> str:
        """Standalone WhatsApp flow: verify active desvíos without running an audit."""
        telefono = payload.telefono

        try:
            db = SupabaseManager()
            sucursales = db.get_sucursales_con_pendientes()
        except Exception as e:
            logger.error(f"Error fetching sucursales con pendientes: {e}")
            await meta_client.send_text(telefono, "❌ No pude consultar los desvíos activos. Intentá de nuevo.")
            return "desvio_management_error"

        if not sucursales:
            await meta_client.send_text(telefono, "🎉 No hay desvíos activos en ninguna sucursal.")
            return "no_active_desvios"

        delete_session(telefono)
        session = create_session(telefono, "", auditor_nombre or "Auditor")
        session.verification_only = True
        session.verification_menu = sucursales
        session.estado = AuditState.VERIFY_SELECT_SUCURSAL
        save_session(session)

        await AuditConversationHandler._send_sucursal_menu(meta_client, session)
        return "desvio_management_menu_sent"

    @staticmethod
    async def start_revision_bandeja(payload: WhatsAppPayload, meta_client: MetaClient, auditor_nombre: str = "") -> str:
        """Standalone WhatsApp flow: bandeja de revisión — aprobar/rechazar
        las correcciones que el encargado ya mandó para desvíos en
        En_revision, filtrado solo a las gestiones de auditorías de ESTE
        auditor (gestion.ficha_id -> audit_fiches.auditor_telefono)."""
        telefono = payload.telefono
        telefono_norm = normalize_phone(telefono)

        try:
            db = SupabaseManager()
            gestion_resp = (
                db.client.table("gestion")
                .select(
                    "id_gestion, id_sucursal, sucursal, desvio, severidad, plazo_fecha, "
                    "plazo_fecha_original, veces_rechazado, tel_responsable, ficha_id"
                )
                .eq("estado", "En_revision")
                .execute()
            )
            en_revision = gestion_resp.data or []
        except Exception as e:
            logger.error(f"Error fetching gestiones en revision: {e}")
            await meta_client.send_text(telefono, "❌ No pude consultar tus correcciones pendientes. Intentá de nuevo.")
            return "revision_bandeja_error"

        if not en_revision:
            await meta_client.send_text(telefono, "No tenés correcciones pendientes de revisar. 🎉")
            return "no_pending_revision"

        # Resolver en lote gestion.ficha_id -> audit_fiches.auditor_telefono
        # (mismo patron que informes_respuesta.py) para quedarse solo con las
        # gestiones de ESTE auditor — no las de todos.
        ficha_ids = sorted({g["ficha_id"] for g in en_revision if g.get("ficha_id")})
        auditor_tel_by_ficha: Dict[str, Optional[str]] = {}
        if ficha_ids:
            fichas_resp = db.client.table("audit_fiches").select("id, auditor_telefono").in_("id", ficha_ids).execute()
            auditor_tel_by_ficha = {f["id"]: f.get("auditor_telefono") for f in (fichas_resp.data or [])}

        mias = [
            g for g in en_revision
            if g.get("ficha_id") and normalize_phone(auditor_tel_by_ficha.get(g["ficha_id"])) == telefono_norm
        ]

        if not mias:
            await meta_client.send_text(telefono, "No tenés correcciones pendientes de revisar. 🎉")
            return "no_pending_revision"

        # Respuesta del encargado por gestion (mismo patron que
        # informes_respuesta.py: eventos con metadata.origen='sucursal').
        gestion_ids = [g["id_gestion"] for g in mias]
        eventos_por_gestion: Dict[str, List[Dict[str, Any]]] = {}
        try:
            eventos_resp = (
                db.client.table("desvio_eventos")
                .select("id, id_gestion, tipo, comentario, metadata, created_at")
                .in_("id_gestion", gestion_ids)
                .in_("tipo", ["mensaje", "evidencia"])
                .order("created_at")
                .execute()
            )
            for e in (eventos_resp.data or []):
                if (e.get("metadata") or {}).get("origen") == "sucursal":
                    eventos_por_gestion.setdefault(e["id_gestion"], []).append(e)
        except Exception as e:
            logger.warning(f"No se pudo traer la respuesta del encargado para la bandeja de revision: {e}")

        cola: List[Dict[str, Any]] = []
        for g in mias:
            eventos = eventos_por_gestion.get(g["id_gestion"], [])
            respuesta = _consolidar_respuesta(eventos) if eventos else {"comentario": None, "foto_path": None}
            cola.append({
                "id_gestion": g["id_gestion"],
                "id_sucursal": g.get("id_sucursal"),
                "desvio": g.get("desvio") or "",
                "sucursal": g.get("sucursal") or g.get("id_sucursal") or "",
                "severidad": g.get("severidad") or "Media",
                "plazo_fecha": g.get("plazo_fecha") or "",
                "plazo_fecha_original": g.get("plazo_fecha_original"),
                "veces_rechazado": g.get("veces_rechazado") or 0,
                "tel_responsable": g.get("tel_responsable"),
                "comentario_encargado": respuesta.get("comentario"),
                "foto_path_encargado": respuesta.get("foto_path"),
            })

        delete_session(telefono)
        session = create_session(telefono, "", auditor_nombre or "Auditor")
        session.pending_verifications = cola
        session.current_verification_index = 0
        session.estado = AuditState.REVISION_BANDEJA
        save_session(session)

        await meta_client.send_text(
            telefono,
            f"📋 Tenés {len(cola)} corrección(es) para revisar. Vamos una por una."
        )
        await AuditConversationHandler._send_item_revision_bandeja(meta_client, session)
        return "revision_bandeja_started"

    @staticmethod
    async def _send_item_revision_bandeja(meta_client: MetaClient, session: AuditSession) -> None:
        """Manda el item actual de la bandeja: desvío + respuesta del
        encargado (texto y, si hay, la foto) + botones de accion."""
        item = session.get_current_verification()
        if not item:
            return

        total = len(session.pending_verifications)
        idx = session.current_verification_index + 1

        texto = (
            f"{idx}/{total} · {item['sucursal']}\n"
            f"Desvío: {(item['desvio'] or '')[:200]}\n"
            f"Severidad: {item['severidad']}"
        )
        if item.get("veces_rechazado"):
            texto += f" · Ya rechazado {item['veces_rechazado']} vez(es)"
        texto += "\n\n"
        if item.get("comentario_encargado"):
            texto += f"Respuesta del encargado:\n{item['comentario_encargado']}"
        else:
            texto += "El encargado no dejó comentario, solo evidencia."

        await meta_client.send_text(session.telefono, texto)

        foto_path = item.get("foto_path_encargado")
        if foto_path:
            try:
                db = SupabaseManager()
                signed = db.create_signed_evidencia_url(foto_path)
                if signed:
                    ok = await meta_client.send_image_by_url(session.telefono, signed, caption="📸 Evidencia del encargado")
                    if not ok:
                        logger.warning(f"No se pudo reenviar la foto de evidencia {foto_path} en la bandeja de revision")
            except Exception as e:
                logger.warning(f"Error resolviendo/mandando la foto de evidencia en la bandeja de revision: {e}")

        await meta_client.send_quick_reply(
            session.telefono,
            "¿Qué hacemos con esta corrección?",
            [
                {"id": "rev_aprobar", "title": "✅ Aprobar"},
                {"id": "rev_rechazar", "title": "❌ Rechazar"},
                {"id": "rev_omitir", "title": "⏭️ Más tarde"},
            ],
        )

    @staticmethod
    async def _send_sucursal_menu(meta_client: MetaClient, session: AuditSession) -> None:
        """Send sucursal picker: native list message (≤10) or numbered text fallback."""
        telefono = session.telefono
        sucursales = session.verification_menu

        if len(sucursales) <= 10:
            options = [
                {
                    "id": f"verif_suc_{i}",
                    "title": s["sucursal"][:24],
                    "description": f"{s['count']} desvío(s) activo(s)",
                }
                for i, s in enumerate(sucursales, 1)
            ]
            sent = await meta_client.send_list_message(
                telefono,
                "📋 Gestión de desvíos",
                "Elegí la sucursal cuyos desvíos querés verificar.",
                "Escribí 'cancelar' para salir",
                "Ver sucursales",
                options,
            )
            if sent:
                return

        menu = "📋 Gestión de desvíos activos\n\nSucursales con desvíos pendientes:\n\n"
        for i, s in enumerate(sucursales, 1):
            menu += f"{i}. {s['sucursal']} ({s['count']})\n"
        menu += "\nResponde con el número de la sucursal, o 'cancelar' para salir."
        await meta_client.send_text(telefono, menu)

    @staticmethod
    async def handle_verify_sucursal_selection(payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession) -> str:
        """Handle sucursal choice in standalone desvío management."""
        telefono = payload.telefono
        texto = (payload.contenido or "").strip().lower() if payload.tipo == "text" else ""

        if texto in {"cancelar", "salir", "cancel"}:
            delete_session(telefono)
            await meta_client.send_text(telefono, "Gestión de desvíos cancelada. Escribí 'hola' para volver al menú.")
            return "desvio_management_cancelled"

        if texto.startswith("verif_suc_"):
            texto = texto.removeprefix("verif_suc_")

        if not texto.isdigit() or not (1 <= int(texto) <= len(session.verification_menu)):
            await meta_client.send_text(telefono, "⚠️ Elegí una sucursal de la lista, o escribí 'cancelar' para salir.")
            await AuditConversationHandler._send_sucursal_menu(meta_client, session)
            return "verify_sucursal_invalid_input"

        elegida = session.verification_menu[int(texto) - 1]
        session.sucursal_id = elegida["id_sucursal"]

        try:
            db = SupabaseManager()
            pendientes = db.get_gestiones_pendientes_sucursal(session.sucursal_id)
        except Exception as e:
            logger.error(f"Error fetching pendientes for {session.sucursal_id}: {e}")
            pendientes = []

        if not pendientes:
            delete_session(telefono)
            await meta_client.send_text(telefono, f"🎉 {elegida['sucursal']} ya no tiene desvíos activos.")
            return "no_active_desvios"

        # Urgency order: vencidos first, then severity Alta→Baja, then oldest plazo
        sev_order = {"Alta": 0, "Media": 1, "Baja": 2}
        pendientes.sort(key=lambda g: (
            0 if g.get("estado") == "Vencida" else 1,
            sev_order.get(g.get("severidad"), 1),
            g.get("plazo_fecha") or "9999-12-31",
        ))

        session.pending_verifications = AuditConversationHandler._queue_from_gestiones(pendientes)
        session.current_verification_index = 0
        session.awaiting_verification_photo = False
        session.verification_menu = []
        session.estado = AuditState.VERIFY_PREVIOUS
        save_session(session)

        await meta_client.send_text(
            telefono,
            f"📋 {elegida['sucursal']}: {len(pendientes)} desvío(s) activo(s).\n"
            f"Vamos uno por uno (primero los más urgentes)."
        )
        await AuditConversationHandler._send_current_verification(meta_client, session)
        return "verification_started"

    @staticmethod
    async def enter_bloque(meta_client: MetaClient, session: AuditSession, intro_msg: str = "") -> str:
        """Enter current bloque: score directly. Ya no verifica desvíos
        pendientes de auditorías anteriores acá (se sacó a pedido del dueño,
        interrumpia el flujo) — esos desvíos se siguen gestionando por otro
        lado: el encargado respondiendo por WhatsApp, o el comando standalone
        'desvios' (ver handle_verify_sucursal_selection), que sigue intacto."""
        telefono = session.telefono

        # Corre una vez por bloque, antes de que arranque el puntaje — limpia
        # la foto ancla del bloque anterior para que un hallazgo de un bloque
        # nuevo nunca quede ligado a una foto de otro bloque.
        session.current_foto_id = None

        if intro_msg:
            await meta_client.send_text(telefono, intro_msg)

        session.estado = AuditState.SCORING
        save_session(session)
        await AuditConversationHandler._send_scoring_list(meta_client, telefono, session)
        return "scoring_started"

    @staticmethod
    async def _send_current_verification(meta_client: MetaClient, session: AuditSession) -> None:
        """Send quick reply buttons for the gestion currently being verified."""
        verif = session.get_current_verification()
        if not verif:
            return

        total = len(session.pending_verifications)
        idx = session.current_verification_index + 1
        desvio_txt = (verif.get("desvio") or "")[:300]
        plazo = verif.get("plazo_fecha") or "sin plazo"
        vencido = " ⏰ vencido" if verif.get("estado") == "Vencida" else ""
        bloque_line = ""
        if session.verification_only and verif.get("bloque"):
            bloque_line = f"Bloque: {BLOQUE_LABELS.get(verif['bloque'], verif['bloque'])}\n"

        await meta_client.send_quick_reply(
            session.telefono,
            f"{idx}/{total} · {desvio_txt}\n"
            f"{bloque_line}"
            f"Severidad: {verif.get('severidad')} · Plazo: {plazo}{vencido}\n\n"
            f"¿Cómo está hoy?\n\n"
            f"(Si no depende del encargado — falta de droguería, obra, etc. — "
            f"escribí 'depende de terceros')",
            [
                {"id": "verif_resuelto", "title": "✅ Resuelto"},
                {"id": "verif_persiste", "title": "⚠️ Persiste"},
                {"id": "verif_omitir", "title": "⏭️ Omitir"},
            ],
        )

    @staticmethod
    async def handle_verification(payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession) -> str:
        """Handle auditor responses while verifying previous desvíos."""
        telefono = payload.telefono
        verif = session.get_current_verification()

        if not verif:
            return await AuditConversationHandler._finish_verifications(meta_client, session)

        # Waiting for resolution photo after "Resuelto"
        if session.awaiting_verification_photo:
            if payload.tipo == "image" and payload.media_id:
                try:
                    media_bytes, mime_type = await meta_client.download_media_with_metadata(payload.media_id)
                    validation = PhotoValidator.validate_media_bytes(media_bytes, mime_type)
                    if not validation.is_valid:
                        await meta_client.send_quick_reply(
                            telefono,
                            validation.message + "\n\nIntentá con otra foto.",
                            [{"id": "verif_sin_foto", "title": "Continuar sin foto"}],
                        )
                        return "verification_photo_invalid"
                except Exception as e:
                    logger.error(f"Error downloading verification photo: {e}")
                    await meta_client.send_quick_reply(
                        telefono,
                        "❌ Error procesando la foto. Intentá de nuevo.",
                        [{"id": "verif_sin_foto", "title": "Continuar sin foto"}],
                    )
                    return "verification_photo_error"

                evidencia = None
                try:
                    db = SupabaseManager()
                    evidencia = db.upload_desvio_evidencia(verif["id_gestion"], media_bytes, mime_type)
                except Exception as e:
                    logger.warning(f"Could not upload verification evidence: {e}")

                return await AuditConversationHandler._mark_resuelto(meta_client, session, verif, evidencia)

            if payload.tipo == "text":
                contenido_up = (payload.contenido or "").upper()
                if "OMITIR" in contenido_up or contenido_up.strip() == "VERIF_SIN_FOTO":
                    return await AuditConversationHandler._mark_resuelto(meta_client, session, verif, None)

            await meta_client.send_quick_reply(
                telefono,
                "📷 Enviá una foto de la resolución.",
                [{"id": "verif_sin_foto", "title": "Continuar sin foto"}],
            )
            return "awaiting_verification_photo"

        # Waiting for the mandatory motivo after "depende de terceros"
        if session.awaiting_verification_motivo:
            motivo = (payload.contenido or "").strip() if payload.tipo == "text" else ""
            if not motivo:
                await meta_client.send_text(
                    telefono,
                    "Necesito el motivo en texto (por qué depende de un tercero) para poder marcarlo."
                )
                return "terceros_motivo_invalid"
            session.awaiting_verification_motivo = False
            return await AuditConversationHandler._mark_terceros(meta_client, session, verif, motivo)

        # Expect a button reply (or its typed equivalent)
        respuesta = (payload.contenido or "").lower().strip() if payload.tipo == "text" else ""

        if session.verification_only and respuesta in {"cancelar", "salir", "cancel"}:
            delete_session(telefono)
            await meta_client.send_text(telefono, "Gestión de desvíos cancelada. Escribí 'hola' para volver al menú.")
            return "desvio_management_cancelled"

        if respuesta == "verif_resuelto" or "resuelto" in respuesta:
            session.awaiting_verification_photo = True
            save_session(session)
            await meta_client.send_quick_reply(
                telefono,
                "📷 Enviá una foto de evidencia de la resolución.",
                [{"id": "verif_sin_foto", "title": "Continuar sin foto"}],
            )
            return "verification_resuelto_awaiting_photo"

        if respuesta == "verif_persiste" or "persiste" in respuesta:
            return await AuditConversationHandler._mark_persiste(meta_client, session, verif)

        if respuesta == "verif_omitir" or "omitir" in respuesta:
            verif["resultado"] = "omitido"
            return await AuditConversationHandler._advance_verification(meta_client, session)

        # No es un boton de Meta (limite de 3, ya ocupados por Resuelto/
        # Persiste/Omitir) — se ofrece como comando de texto, ver el hint en
        # _send_current_verification.
        if "tercero" in respuesta or respuesta == "trabar":
            session.awaiting_verification_motivo = True
            save_session(session)
            await meta_client.send_text(
                telefono,
                "Escribí el motivo (por qué depende de un tercero — falta de droguería, obra, etc.). "
                "Mientras esté en este estado no escala ni cuenta como incumplimiento del encargado."
            )
            return "awaiting_terceros_motivo"

        await meta_client.send_text(telefono, "Por favor usá los botones 👇")
        await AuditConversationHandler._send_current_verification(meta_client, session)
        return "verification_invalid_input"

    @staticmethod
    async def _mark_resuelto(meta_client: MetaClient, session: AuditSession, verif: dict, evidencia: Optional[dict]) -> str:
        """Mark gestion as Resuelta with verification event (+ optional photo evidence)."""
        actor = session.auditor_nombre or "Auditor"
        bloque = verif.get("bloque") if session.verification_only else session.get_current_bloque()

        try:
            db = SupabaseManager()
            metadata = {
                "origen": "gestion_desvios_wsp" if session.verification_only else "auditoria_v2",
                "bloque": bloque,
                "id_sesion": session.id_sesion,
                "canal": "whatsapp",
            }
            if evidencia:
                metadata["foto_path"] = evidencia.get("path")
                metadata["thumb_path"] = evidencia.get("thumb_path")
                metadata["bucket"] = evidencia.get("bucket")
                signed = db.create_signed_evidencia_url(evidencia.get("path", ""))
                if signed:
                    metadata["foto_url_signed"] = signed

            db.save_encargado_evento(
                id_gestion=verif["id_gestion"],
                tipo="verificacion_auditoria",
                contenido="Desvío verificado como resuelto durante auditoría en piso.",
                actor_nombre=actor,
                metadata=metadata,
            )
            db.update_gestion_fields(verif["id_gestion"], {"estado": "Resuelta"})

            verif["resultado"] = "resuelto"
            session.verified_resueltos += 1
        except Exception as e:
            logger.error(f"Error marking gestion {verif.get('id_gestion')} resuelta: {e}")
            await meta_client.send_text(
                session.telefono,
                "⚠️ No pude registrar la resolución en el sistema, seguimos con la auditoría."
            )
            return await AuditConversationHandler._advance_verification(meta_client, session)

        await meta_client.send_text(session.telefono, "✅ Registrado como resuelto.")
        return await AuditConversationHandler._advance_verification(meta_client, session)

    @staticmethod
    async def _mark_persiste(meta_client: MetaClient, session: AuditSession, verif: dict) -> str:
        """Record recurrence event and escalate severity one level."""
        actor = session.auditor_nombre or "Auditor"
        bloque = verif.get("bloque") if session.verification_only else session.get_current_bloque()
        severidad_actual = verif.get("severidad") or "Media"
        nueva_severidad = SEVERITY_ESCALATION.get(severidad_actual, severidad_actual)

        try:
            db = SupabaseManager()
            db.save_encargado_evento(
                id_gestion=verif["id_gestion"],
                tipo="reincidencia",
                contenido=(
                    f"El desvío persiste según verificación en piso. "
                    f"Severidad: {severidad_actual} → {nueva_severidad}."
                ),
                actor_nombre=actor,
                metadata={
                    "origen": "gestion_desvios_wsp" if session.verification_only else "auditoria_v2",
                    "bloque": bloque,
                    "id_sesion": session.id_sesion,
                    "severidad_anterior": severidad_actual,
                    "severidad_nueva": nueva_severidad,
                    "canal": "whatsapp",
                },
            )
            if nueva_severidad != severidad_actual:
                db.update_gestion_fields(verif["id_gestion"], {"severidad": nueva_severidad})

            verif["resultado"] = "persiste"
            session.verified_persisten += 1
        except Exception as e:
            logger.error(f"Error marking gestion {verif.get('id_gestion')} persiste: {e}")
            await meta_client.send_text(
                session.telefono,
                "⚠️ No pude registrar la reincidencia en el sistema, seguimos con la auditoría."
            )
            return await AuditConversationHandler._advance_verification(meta_client, session)

        await meta_client.send_text(
            session.telefono,
            f"⚠️ Reincidencia registrada (severidad: {nueva_severidad})."
        )
        return await AuditConversationHandler._advance_verification(meta_client, session)

    @staticmethod
    async def _mark_terceros(meta_client: MetaClient, session: AuditSession, verif: dict, motivo: str) -> str:
        """Marca el desvío como dependiente de un tercero (falta de droguería,
        obra, personal — algo que el encargado no puede resolver solo).
        Mientras esté en GestionState.EN_GESTION_TERCEROS no escala, no cuenta
        como incumplimiento del encargado, y no vence — ver arquitectura,
        ARQUITECTURA_DESVIOS_CAMPANIAS.md §1.2 punto 8. Motivo obligatorio,
        ya validado por el caller antes de llegar acá."""
        actor = session.auditor_nombre or "Auditor"
        bloque = verif.get("bloque") if session.verification_only else session.get_current_bloque()

        try:
            db = SupabaseManager()
            db.save_encargado_evento(
                id_gestion=verif["id_gestion"],
                tipo="nota",
                contenido=f"Marcado como dependiente de terceros: {motivo}",
                actor_nombre=actor,
                metadata={
                    "origen": "gestion_desvios_wsp" if session.verification_only else "auditoria_v2",
                    "bloque": bloque,
                    "id_sesion": session.id_sesion,
                    "canal": "whatsapp",
                    "motivo_terceros": motivo,
                },
            )
            db.update_gestion_fields(verif["id_gestion"], {"estado": "En_gestion_terceros"})
            verif["resultado"] = "terceros"
        except Exception as e:
            logger.error(f"Error marking gestion {verif.get('id_gestion')} en_gestion_terceros: {e}")
            await meta_client.send_text(
                session.telefono,
                "⚠️ No pude registrar el estado en el sistema, seguimos con la auditoría."
            )
            return await AuditConversationHandler._advance_verification(meta_client, session)

        await meta_client.send_text(session.telefono, "🔧 Marcado como dependiente de terceros.")
        return await AuditConversationHandler._advance_verification(meta_client, session)

    @staticmethod
    async def _advance_verification(meta_client: MetaClient, session: AuditSession) -> str:
        """Move to next pending verification, or finish and start scoring."""
        if session.move_to_next_verification():
            save_session(session)
            await AuditConversationHandler._send_current_verification(meta_client, session)
            return "next_verification"
        return await AuditConversationHandler._finish_verifications(meta_client, session)

    @staticmethod
    async def _finish_verifications(meta_client: MetaClient, session: AuditSession) -> str:
        """Close verification queue: back to scoring (audit) or end (standalone)."""
        resumen = ""
        if session.pending_verifications:
            resueltos = sum(1 for v in session.pending_verifications if v.get("resultado") == "resuelto")
            persisten = sum(1 for v in session.pending_verifications if v.get("resultado") == "persiste")
            omitidos = len(session.pending_verifications) - resueltos - persisten
            partes = [f"✅ {resueltos} resuelto(s)", f"⚠️ {persisten} persiste(n)"]
            if omitidos:
                partes.append(f"⏭️ {omitidos} omitido(s)")
            resumen = "✓ Verificación completada: " + " · ".join(partes)

        if session.verification_only:
            delete_session(session.telefono)
            if resumen:
                await meta_client.send_text(session.telefono, resumen)
            await meta_client.send_text(
                session.telefono,
                "Listo 👍 Escribí 'desvios' para gestionar otra sucursal u 'hola' para el menú."
            )
            return "verification_management_done"

        session.pending_verifications = []
        session.current_verification_index = 0
        session.awaiting_verification_photo = False
        session.estado = AuditState.SCORING
        save_session(session)

        if resumen:
            await meta_client.send_text(session.telefono, resumen)
        await AuditConversationHandler._send_scoring_list(meta_client, session.telefono, session)
        return "scoring_started"

    @staticmethod
    async def handle_revision_bandeja(payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession) -> str:
        """Handle auditor responses in the standalone revision inbox (aprobar/
        rechazar/omitir correcciones que el encargado ya mandó)."""
        telefono = payload.telefono
        item = session.get_current_verification()

        if not item:
            return await AuditConversationHandler._advance_revision_bandeja(meta_client, session)

        # Esperando el motivo obligatorio de un rechazo
        if session.awaiting_revision_motivo:
            motivo = (payload.contenido or "").strip() if payload.tipo == "text" else ""
            if not motivo:
                await meta_client.send_text(
                    telefono, "Necesito el motivo del rechazo en texto para poder registrarlo."
                )
                return "revision_motivo_invalid"

            session.awaiting_revision_motivo = False
            save_session(session)
            try:
                db = SupabaseManager()
                await aplicar_revision_gestion(
                    db=db, meta_client=meta_client, gestion=item, accion="rechazar",
                    actor_nombre=session.auditor_nombre or "Auditor", actor_id=None, motivo=motivo,
                )
                await meta_client.send_text(telefono, "❌ Corrección rechazada, el encargado ya fue avisado.")
            except Exception as e:
                logger.error(f"Error rechazando gestion {item.get('id_gestion')} desde la bandeja: {e}")
                await meta_client.send_text(telefono, "⚠️ No pude registrar el rechazo, seguimos con la siguiente.")
            return await AuditConversationHandler._advance_revision_bandeja(meta_client, session)

        respuesta = (payload.contenido or "").lower().strip() if payload.tipo == "text" else ""

        if respuesta in {"cancelar", "salir", "cancel"}:
            delete_session(telefono)
            await meta_client.send_text(telefono, "Bandeja de revisión cerrada. Escribí 'pendientes' para volver.")
            return "revision_bandeja_cancelled"

        if respuesta == "rev_aprobar" or "aprobar" in respuesta:
            try:
                db = SupabaseManager()
                await aplicar_revision_gestion(
                    db=db, meta_client=meta_client, gestion=item, accion="aprobar",
                    actor_nombre=session.auditor_nombre or "Auditor", actor_id=None, motivo=None,
                )
                await meta_client.send_text(telefono, "✅ Corrección aprobada.")
            except Exception as e:
                logger.error(f"Error aprobando gestion {item.get('id_gestion')} desde la bandeja: {e}")
                await meta_client.send_text(telefono, "⚠️ No pude registrar la aprobación, seguimos con la siguiente.")
            return await AuditConversationHandler._advance_revision_bandeja(meta_client, session)

        if respuesta == "rev_rechazar" or "rechazar" in respuesta:
            session.awaiting_revision_motivo = True
            save_session(session)
            await meta_client.send_text(telefono, "Escribí el motivo del rechazo (se lo mandamos al encargado).")
            return "awaiting_revision_motivo"

        if respuesta == "rev_omitir" or "omitir" in respuesta or "mas tarde" in respuesta or "más tarde" in respuesta:
            return await AuditConversationHandler._advance_revision_bandeja(meta_client, session)

        await meta_client.send_text(telefono, "Por favor usá los botones 👇")
        await AuditConversationHandler._send_item_revision_bandeja(meta_client, session)
        return "revision_bandeja_invalid_input"

    @staticmethod
    async def _advance_revision_bandeja(meta_client: MetaClient, session: AuditSession) -> str:
        """Move to next pending review, or finish and close the session."""
        if session.move_to_next_verification():
            save_session(session)
            await AuditConversationHandler._send_item_revision_bandeja(meta_client, session)
            return "next_revision_item"

        delete_session(session.telefono)
        await meta_client.send_text(
            session.telefono,
            "✅ Revisaste todas tus correcciones pendientes. Escribí 'pendientes' cuando haya nuevas."
        )
        return "revision_bandeja_done"

    @staticmethod
    async def _send_audit_sucursal_menu(
        meta_client: MetaClient,
        telefono: str,
        sucursales: list,
    ) -> None:
        """Send sucursal picker for starting a new audit.

        Las listas interactivas de WhatsApp topean en MAX_LIST_ROWS_TOTAL filas
        EN TOTAL (no por sección), así que con ~25 sucursales no entran y
        send_list_message directamente se niega a mandarlas. Cuando no entran va
        texto numerado, que es el mismo criterio que ya usa el flujo v1.
        """
        if len(sucursales) <= MetaClient.MAX_LIST_ROWS_TOTAL:
            options = [
                {"id": f"audit_suc_{i}", "title": s["nombre"][:24]}
                for i, s in enumerate(sucursales, 1)
            ]
            sent = await meta_client.send_list_message(
                telefono,
                "🏪 Seleccioná la sucursal",
                "¿En qué sucursal vas a auditar?",
                "Escribí 'cancelar' para salir",
                "Ver sucursales",
                options,
            )
            if sent:
                return

        menu = "🏪 ¿En qué sucursal vas a auditar?\n\n"
        for i, s in enumerate(sucursales, 1):
            menu += f"{i}. {s['nombre']}\n"
        menu += "\nRespondé con el número, o escribí parte del nombre."
        menu += "\nEscribí 'cancelar' para salir."
        await meta_client.send_text(telefono, menu)

    @staticmethod
    async def handle_init(payload: WhatsAppPayload, meta_client: MetaClient) -> str:
        """Initialize new audit session: load sucursales and ask user to pick one."""
        telefono = payload.telefono

        try:
            db = SupabaseManager()
            res = db.client.table("sucursales").select("id, nombre").eq("activo", True).order("nombre").execute()
            sucursales = res.data or []
        except Exception as e:
            logger.error(f"Error loading sucursales for audit init: {e}")
            sucursales = []

        if not sucursales:
            await meta_client.send_text(
                telefono,
                "❌ No pude cargar la lista de sucursales. Intentá de nuevo."
            )
            return "sucursales_load_error"

        # Resolve auditor name from DB (best-effort)
        auditor_nombre: Optional[str] = None
        try:
            auditor_obj = SupabaseManager().get_auditor(telefono)
            if auditor_obj:
                auditor_nombre = auditor_obj.nombre
        except Exception:
            pass

        # Create a placeholder session in SELECT_SUCURSAL state
        session = create_session(telefono=telefono, sucursal_id="", auditor_nombre=auditor_nombre)
        session.estado = AuditState.SELECT_SUCURSAL
        session.verification_menu = [{"id": s["id"], "nombre": s["nombre"]} for s in sucursales]
        save_session(session)

        await AuditConversationHandler._send_audit_sucursal_menu(
            meta_client, telefono, session.verification_menu
        )
        return "sucursal_menu_sent"

    @staticmethod
    async def _send_ficha_llegada(meta_client: MetaClient, session: AuditSession, telefono: str) -> None:
        """Contexto rapido al elegir sucursal: ultima auditoria, desvios
        abiertos/vencidos, y quien es el encargado. Best-effort — si falla
        cualquier consulta no bloquea el arranque de la auditoria, solo se
        pierde el contexto (mismo criterio que el resto de los avisos
        best-effort de este archivo)."""
        try:
            db = SupabaseManager()

            ficha_resp = (
                db.client.table("audit_fiches")
                .select("fecha_auditoria, puntuacion_promedio")
                .eq("sucursal_id", session.sucursal_id)
                .order("fecha_auditoria", desc=True)
                .limit(1)
                .execute()
            )
            ultima_ficha = (ficha_resp.data or [None])[0]

            gestion_resp = (
                db.client.table("gestion")
                .select("estado")
                .eq("id_sucursal", session.sucursal_id)
                .not_.in_("estado", ["Resuelta", "Cerrada"])
                .execute()
            )
            filas = gestion_resp.data or []
            abiertos = len(filas)
            vencidos = sum(1 for f in filas if f.get("estado") == "Vencida")

            responsable = resolve_responsable_by_sucursal(session.sucursal_id)

            lineas = []
            if ultima_ficha and ultima_ficha.get("fecha_auditoria"):
                try:
                    fecha = datetime.fromisoformat(str(ultima_ficha["fecha_auditoria"]).replace("Z", "+00:00"))
                    fecha_txt = fecha.strftime("%d/%m/%Y")
                except Exception:
                    fecha_txt = str(ultima_ficha["fecha_auditoria"])[:10]
                promedio = ultima_ficha.get("puntuacion_promedio")
                promedio_txt = f"{promedio}/5" if promedio is not None else "—"
                lineas.append(f"📅 Última auditoría: {fecha_txt} — {promedio_txt}")
            else:
                lineas.append("📅 No hay auditorías previas registradas.")

            if abiertos:
                extra = f" ({vencidos} vencido{'s' if vencidos != 1 else ''})" if vencidos else ""
                lineas.append(f"⚠️ Desvíos abiertos: {abiertos}{extra}")
            else:
                lineas.append("✅ Sin desvíos abiertos.")

            if responsable and responsable.telefono:
                lineas.append(f"👤 Encargado/a: {responsable.nombre or 'sin nombre'}")
            else:
                lineas.append("👤 Sin encargado cargado para esta sucursal.")

            await meta_client.send_text(telefono, "\n".join(lineas))
        except Exception as e:
            logger.warning(f"No se pudo armar la ficha de llegada para {session.sucursal_id}: {e}")

    @staticmethod
    async def handle_select_sucursal(
        payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession
    ) -> str:
        """Handle sucursal selection to start a new audit."""
        telefono = payload.telefono
        texto = (payload.contenido or "").strip().lower() if payload.tipo == "text" else ""

        if texto in {"cancelar", "salir", "cancel"}:
            delete_session(telefono)
            await meta_client.send_text(telefono, "Auditoría cancelada. Escribí *auditoria* para empezar.")
            return "audit_cancelled"

        sucursales = session.verification_menu

        # Sin texto utilizable (sticker, ubicación, foto suelta) no se puede
        # elegir nada. Antes esto arrancaba una auditoría sobre la primera
        # sucursal de la lista, porque "" está contenido en cualquier nombre.
        if not texto:
            await meta_client.send_text(
                telefono,
                "Necesito que elijas una sucursal para arrancar.\n\n"
                "Respondé con el número de la lista, o escribí parte del nombre."
            )
            await AuditConversationHandler._send_audit_sucursal_menu(
                meta_client, telefono, sucursales
            )
            return "invalid_sucursal_selection"

        # Accept "audit_suc_N" (list button) or plain digit
        if texto.startswith("audit_suc_"):
            texto = texto.removeprefix("audit_suc_")

        if texto.isdigit():
            indice = int(texto)
            if not 1 <= indice <= len(sucursales):
                await meta_client.send_text(
                    telefono,
                    f"⚠️ El número tiene que estar entre 1 y {len(sucursales)}."
                )
                await AuditConversationHandler._send_audit_sucursal_menu(
                    meta_client, telefono, sucursales
                )
                return "invalid_sucursal_selection"
            elegida = sucursales[indice - 1]
        else:
            # Match por nombre. Se piden 3 letras mínimo para que una letra
            # suelta no matchee media lista, y si hay varias coincidencias se
            # muestran en vez de quedarse con la primera.
            if len(texto) < 3:
                await meta_client.send_text(
                    telefono,
                    "Escribí al menos 3 letras del nombre, o el número de la lista."
                )
                return "invalid_sucursal_selection"

            coincidencias = [s for s in sucursales if texto in s["nombre"].lower()]

            if not coincidencias:
                await meta_client.send_text(
                    telefono, "⚠️ No encontré esa sucursal. Elegí una de la lista, o escribí 'cancelar'."
                )
                await AuditConversationHandler._send_audit_sucursal_menu(
                    meta_client, telefono, sucursales
                )
                return "invalid_sucursal_selection"

            if len(coincidencias) > 1:
                detalle = "\n".join(
                    f"{sucursales.index(s) + 1}. {s['nombre']}" for s in coincidencias
                )
                await meta_client.send_text(
                    telefono,
                    f"Hay {len(coincidencias)} sucursales que coinciden:\n\n{detalle}\n\n"
                    "Respondé con el número."
                )
                return "ambiguous_sucursal_selection"

            elegida = coincidencias[0]

        # Commit the selected sucursal and start audit
        session.sucursal_id = elegida["id"]
        session.started_at = datetime.now(timezone.utc).isoformat()
        session.verification_menu = []
        save_session(session)

        # Contexto rapido antes de arrancar a puntuar — antes el auditor
        # llegaba a ciegas, sin saber que paso la ultima vez ni con quien
        # coordinar en el piso.
        await AuditConversationHandler._send_ficha_llegada(meta_client, session, telefono)

        await AuditConversationHandler.enter_bloque(
            meta_client, session,
            intro_msg=f"✓ Auditoría iniciada: {elegida['nombre']}"
        )
        return "audit_started"

    @staticmethod
    async def handle_score(payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession) -> str:
        """Handle bloque score input and transition to evidence collection."""

        if payload.tipo != "text":
            await meta_client.send_text(
                payload.telefono,
                "Por favor, responde con un número del 1 al 5"
            )
            return "invalid_input"

        texto = payload.contenido.strip()

        # Validate input is 1-5
        if not texto.isdigit() or not (1 <= int(texto) <= 5):
            await meta_client.send_text(
                payload.telefono,
                "❌ Por favor responde 1, 2, 3, 4 o 5"
            )
            return "invalid_score"

        score = int(texto)
        current_bloque = session.get_current_bloque()
        bloque_label = BLOQUE_LABELS.get(current_bloque, current_bloque)

        # Save score
        session.set_bloque_score(current_bloque, score)

        # Check if it's OFERTAS → move to SCORING_BRANDS (evidencia por marca)
        if current_bloque == BloqueType.OFERTAS.value:
            session.estado = AuditState.SCORING_BRANDS
            session.current_foto_id = None
            session.pending_marca = None
            save_session(session)

            marcas_sugeridas = ", ".join(
                BRAND_LABELS.get(b, b) for b in BRAND_ORDER
            )

            await meta_client.send_text(
                payload.telefono,
                f"✓ Ofertas: {score}/5\n\n"
                f"📸 Ahora registremos Ofertas y Exhibición por marca.\n\n"
                f"Marcas de referencia: {marcas_sugeridas} — pero podés reportar "
                f"cualquier otra marca que veas.\n\n"
                f"Mandá una foto de la marca que quieras reportar. Te voy a preguntar "
                f"cuál es y después contame cómo está (texto o audio). Repetí para "
                f"tantas marcas como quieras.\n\n"
                f"Escribí 'SIGUIENTE' cuando termines con Ofertas."
            )

            return "moved_to_brand_evidence"

        # For non-OFERTAS bloques: move to evidence collection for this bloque
        session.estado = AuditState.BLOQUE_EVIDENCE_COLLECTION
        save_session(session)

        # Get description of what to look for
        bloque_desc = BLOQUE_DESCRIPTIONS.get(current_bloque, "")

        # Get historical comparison
        prev_scores = await get_previous_audit(session.sucursal_id)
        prev_score = prev_scores.get(current_bloque) if prev_scores else None

        # Build comparison message
        comparison = ""
        if prev_score:
            diff = score - prev_score
            if diff > 0:
                trend = f"⬆️ +{diff} (antes: {prev_score}/5)"
            elif diff < 0:
                trend = f"⬇️ {diff} (antes: {prev_score}/5)"
            else:
                trend = f"➡️ igual que antes ({prev_score}/5)"
            comparison = f"\n{trend}"

        await meta_client.send_text(
            payload.telefono,
            f"✓ {bloque_label}: {score}/5{comparison}\n\n"
            f"📸 Enviá al menos UNA foto de este punto (esté bien o mal — la foto es obligatoria).\n"
            f"También podés sumar audios y notas 🎙️📝\n\n"
            f"{bloque_desc}\n\n"
            f"Escribe 'SIGUIENTE' cuando termines este bloque"
        )

        return "evidence_collection_started"

    @staticmethod
    async def _send_estado_parcial(meta_client: MetaClient, session: AuditSession, telefono: str) -> None:
        """Resumen de lo cargado hasta ahora en la auditoria en curso. Antes
        no habia forma de preguntar "que llevo" sin terminar la auditoria —
        cualquier texto (incluido "resumen") se guardaba como un hallazgo."""
        lineas = []
        for bloque in BLOQUE_ORDER:
            score = session.bloques.get(bloque)
            if score is None:
                continue
            label = BLOQUE_LABELS.get(bloque, bloque)
            fotos = len([f for f in session.fotos if f.bloque == bloque])
            audios = len([d for d in session.desvios if d.bloque == bloque and "[AUDIO]" in d.descripcion])
            notas = len([d for d in session.desvios if d.bloque == bloque and "[AUDIO]" not in d.descripcion])
            lineas.append(f"  {label}: {score}/5 — 📸{fotos} 🎙️{audios} 📝{notas}")

        bloques_txt = "\n".join(lineas) if lineas else "  (todavía no puntuaste ningún bloque)"

        hallazgos_txt = ""
        if session.desvios:
            items = "\n".join(
                f"  {i + 1}. [{BLOQUE_LABELS.get(d.bloque, d.bloque)}] {d.descripcion[:60]}"
                for i, d in enumerate(session.desvios)
            )
            hallazgos_txt = f"\n\nHallazgos hasta ahora ({len(session.desvios)}):\n{items}"

        await meta_client.send_text(
            telefono,
            f"📊 *Lo que llevás cargado:*\n\n{bloques_txt}{hallazgos_txt}\n\n"
            f"Escribí 'SIGUIENTE' para pasar al siguiente bloque, o seguí sumando evidencia."
        )

    @staticmethod
    async def _deshacer_ultimo_hallazgo(
        meta_client: MetaClient,
        session: AuditSession,
        bloque: str,
        bloque_label: str,
        telefono: str,
    ) -> None:
        """Saca el ultimo hallazgo cargado en ESTE bloque (no toca otros
        bloques). No deshace fotos — si una foto sale mal, alcanza con mandar
        una nueva; lo que faltaba era poder sacar una nota/audio mal cargado
        sin tener que terminar la auditoria para corregirlo desde 'No, editar'."""
        desvios_bloque = [d for d in session.desvios if d.bloque == bloque]
        if not desvios_bloque:
            await meta_client.send_text(
                telefono,
                f"No hay ningún hallazgo cargado en {bloque_label} todavía para deshacer."
            )
            return

        ultimo = desvios_bloque[-1]
        session.desvios.remove(ultimo)
        save_session(session)

        preview = ultimo.descripcion[:100] + ("…" if len(ultimo.descripcion) > 100 else "")
        await meta_client.send_text(
            telefono,
            f"🗑️ Borrado: \"{preview}\"\n\n¿Algo más? (foto, audio, texto, o 'SIGUIENTE')"
        )

    @staticmethod
    async def _finish_bloque_evidence(
        meta_client: MetaClient,
        session: AuditSession,
        telefono: str,
        current_bloque: str,
        bloque_label: str,
    ) -> str:
        """Cierra el bloque actual con 'SIGUIENTE': exige al menos una foto y
        avanza al proximo bloque (o a SUMMARY si era el ultimo). Compartido
        entre la evidencia generica por bloque y la evidencia por marca de
        OFERTAS — ambas usan la misma regla de cierre."""
        bloque_fotos = len([f for f in session.fotos if f.bloque == current_bloque])
        bloque_audios = len([a for a in session.desvios if a.bloque == current_bloque and "[AUDIO]" in a.descripcion])
        bloque_notas = len([d for d in session.desvios if d.bloque == current_bloque and "[AUDIO]" not in d.descripcion])

        # Photo is mandatory for every controlled point, good or bad
        if bloque_fotos == 0:
            await meta_client.send_text(
                telefono,
                f"📸 Falta la foto de {bloque_label}.\n\n"
                f"Enviá al menos una foto de este punto (esté bien o mal) "
                f"para poder continuar."
            )
            return "photo_required"

        summary_msg = f"✓ {bloque_label} completado!\n📸 {bloque_fotos} foto(s) · 🎙️ {bloque_audios} audio(s) · 📝 {bloque_notas} nota(s)\n\n"

        # Check if there are more bloques to score
        if session.move_to_next_bloque():
            save_session(session)

            # Enter next bloque: verify pending desvíos, then scoring
            await AuditConversationHandler.enter_bloque(
                meta_client, session, intro_msg=summary_msg.strip()
            )

            return "next_bloque"

        # All bloques completed → move to SUMMARY
        session.estado = AuditState.SUMMARY
        save_session(session)

        return await AuditConversationHandler.send_summary(telefono, meta_client, session)

    @staticmethod
    async def handle_bloque_evidence(payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession) -> str:
        """Handle evidence collection for current bloque (fotos, audios, textos)."""

        current_bloque = session.get_current_bloque()
        bloque_label = BLOQUE_LABELS.get(current_bloque, current_bloque)

        # Check for "SIGUIENTE" to move to next bloque
        if payload.tipo == "text":
            texto = payload.contenido.upper().strip()

            if "SIGUIENTE" in texto or "NEXT" in texto:
                return await AuditConversationHandler._finish_bloque_evidence(
                    meta_client, session, payload.telefono, current_bloque, bloque_label
                )

            # Texto sin "SIGUIENTE" — flujo libre: se guarda directo como nota,
            # ligada a la ultima foto recibida en este bloque (si hay una).
            raw_text = payload.contenido.strip()
            texto_comando = raw_text.lower()

            # "resumen"/"estado": antes CUALQUIER texto que no fuera SIGUIENTE
            # se guardaba como hallazgo — asi que ni siquiera se podia
            # preguntar "que llevo cargado" sin ensuciar la auditoria.
            if texto_comando in {"resumen", "estado", "status"}:
                await AuditConversationHandler._send_estado_parcial(meta_client, session, payload.telefono)
                return "estado_parcial_sent"

            # "deshacer": el ultimo hallazgo de ESTE bloque (no de toda la
            # auditoria) queda sin forma de sacarlo si un audio se transcribe
            # mal o un texto se manda antes de terminar de escribirlo.
            if texto_comando in {"deshacer", "undo", "borrar"}:
                await AuditConversationHandler._deshacer_ultimo_hallazgo(
                    meta_client, session, current_bloque, bloque_label, payload.telefono
                )
                return "undo_processed"

            # Un "ok" o un "gracias" no es un desvío — se filtra siempre, sin
            # excepcion, para que el auditor pueda escribir cosas casuales sin
            # que se cuelen como hallazgos falsos en `gestion`.
            if _es_asentimiento(raw_text):
                await meta_client.send_text(
                    payload.telefono,
                    f"👍 Anotado. ¿Algo más para {bloque_label}? "
                    "(foto, audio, texto, o 'SIGUIENTE')"
                )
                return "acknowledgement_ignored"

            session.add_desvio(
                bloque=current_bloque,
                descripcion=raw_text,
                fotos=[session.current_foto_id] if session.current_foto_id else None,
            )
            save_session(session)

            await meta_client.send_quick_reply(
                payload.telefono,
                f"✓ Nota guardada en {bloque_label}\n\n¿Algo más? (foto, audio, o texto)",
                [SIGUIENTE_BUTTON],
            )

            return "note_saved"

        if payload.tipo == "image":
            # Handle photo
            if not payload.media_id:
                await meta_client.send_text(
                    payload.telefono,
                    "❌ No puedo procesar esa imagen. Por favor intenta de nuevo."
                )
                return "no_media_id"

            try:
                # Download and validate photo
                media_bytes, mime_type = await meta_client.download_media_with_metadata(
                    payload.media_id
                )

                validation = PhotoValidator.validate_media_bytes(media_bytes, mime_type)

                if not validation.is_valid:
                    await meta_client.send_text(
                        payload.telefono,
                        validation.message + "\n\nIntenta de nuevo — necesito al menos una foto válida de este bloque para poder continuar."
                    )
                    return "photo_invalid"

                # Photo is valid - store it for this bloque
                foto = FotoEvidence(
                    id=f"foto_{int(datetime.now(timezone.utc).timestamp())}",
                    media_id=payload.media_id,
                    media_url=payload.media_url,
                    bloque=current_bloque,
                    descripcion=payload.contenido or "",
                    validated=True,
                )

                session.add_foto(foto)
                # Esta foto pasa a ser el ancla: todo audio/texto que llegue
                # despues (hasta la proxima foto) se liga a ella en Desvio.fotos.
                session.current_foto_id = foto.id
                save_session(session)

                await meta_client.send_quick_reply(
                    payload.telefono,
                    f"✓ Foto guardada en {bloque_label}\n\n¿Algo más? (audio, texto, u otra foto)",
                    [SIGUIENTE_BUTTON],
                )

                return "photo_received"

            except Exception as e:
                logger.error(f"Error downloading/validating photo: {e}")
                await meta_client.send_text(
                    payload.telefono,
                    "❌ Error procesando la foto. Por favor intenta de nuevo."
                )
                return "photo_download_error"

        elif payload.tipo == "audio":
            # Handle audio message
            if payload.media_id:
                # payload.contenido nunca trae la transcripcion real — el
                # webhook (main.py) lo deja en un placeholder "[Audio message
                # <id>]" a proposito (nunca descarga el audio ahi). Se
                # transcribe aca, con el mismo patron de descarga que ya usa
                # la foto de arriba. El prefijo "[AUDIO]" se preserva siempre
                # (transcriba bien o no) porque otro codigo de esta funcion ya
                # cuenta "audios vs notas" por bloque buscando ese prefijo.
                transcript = ""
                try:
                    media_bytes, mime_type = await meta_client.download_media_with_metadata(payload.media_id)
                    transcript = await AudioTranscriber().transcribe_bytes(media_bytes, mime_type)
                except Exception as e:
                    logger.warning(f"No se pudo transcribir audio {payload.media_id}: {e}")

                audio_description = f"[AUDIO] {transcript.strip() if transcript else 'Sin transcripción'}"
                session.add_desvio(
                    bloque=current_bloque,
                    descripcion=audio_description,
                    fotos=[session.current_foto_id] if session.current_foto_id else None,
                )
                save_session(session)

                await meta_client.send_quick_reply(
                    payload.telefono,
                    f"✓ Audio guardado en {bloque_label}\n\n¿Algo más? (foto, audio, o texto)",
                    [SIGUIENTE_BUTTON],
                )

                return "audio_received"

        # Documento, video, sticker, ubicación, contacto... Antes el bot se
        # quedaba mudo y el auditor no sabía si había pasado algo.
        await meta_client.send_text(
            payload.telefono,
            f"No puedo usar ese tipo de mensaje como evidencia de {bloque_label}.\n\n"
            "Mandame una *foto*, un *audio*, o escribí el problema en texto. "
            "Cuando termines con este punto, escribí 'SIGUIENTE'."
        )
        return "unsupported_media"

    @staticmethod
    async def handle_ofertas_marca_evidence(payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession) -> str:
        """Loop principal de evidencia por marca de OFERTAS: espera una foto
        para arrancar el registro de una marca, o 'SIGUIENTE' para cerrar el
        bloque. A diferencia de los demas bloques, texto/audio sueltos no se
        guardan como nota — acá se fuerza el orden foto → marca → comentario,
        que es lo que pidió la auditora (cada marca queda con su propia foto
        y su propio comentario, no una bolsa de evidencia genérica)."""
        current_bloque = BloqueType.OFERTAS.value
        bloque_label = BLOQUE_LABELS.get(current_bloque, current_bloque)

        if payload.tipo == "text":
            texto = payload.contenido.upper().strip()

            if "SIGUIENTE" in texto or "NEXT" in texto:
                return await AuditConversationHandler._finish_bloque_evidence(
                    meta_client, session, payload.telefono, current_bloque, bloque_label
                )

            raw_text = payload.contenido.strip()
            texto_comando = raw_text.lower()

            if texto_comando in {"resumen", "estado", "status"}:
                await AuditConversationHandler._send_estado_parcial(meta_client, session, payload.telefono)
                return "estado_parcial_sent"

            if texto_comando in {"deshacer", "undo", "borrar"}:
                await AuditConversationHandler._deshacer_ultimo_hallazgo(
                    meta_client, session, current_bloque, bloque_label, payload.telefono
                )
                return "undo_processed"

            if _es_asentimiento(raw_text):
                await meta_client.send_text(
                    payload.telefono,
                    "👍 Anotado. Mandame una foto para reportar una marca, o escribí 'SIGUIENTE'."
                )
                return "acknowledgement_ignored"

            await meta_client.send_text(
                payload.telefono,
                "Para reportar una marca, mandame primero una *foto*. "
                "Cuando termines con Ofertas, escribí 'SIGUIENTE'."
            )
            return "photo_expected"

        if payload.tipo == "image":
            if not payload.media_id:
                await meta_client.send_text(
                    payload.telefono,
                    "❌ No puedo procesar esa imagen. Por favor intenta de nuevo."
                )
                return "no_media_id"

            try:
                media_bytes, mime_type = await meta_client.download_media_with_metadata(
                    payload.media_id
                )

                validation = PhotoValidator.validate_media_bytes(media_bytes, mime_type)

                if not validation.is_valid:
                    await meta_client.send_text(
                        payload.telefono,
                        validation.message + "\n\nIntenta de nuevo — necesito una foto válida de la marca."
                    )
                    return "photo_invalid"

                foto = FotoEvidence(
                    id=f"foto_{int(datetime.now(timezone.utc).timestamp())}",
                    media_id=payload.media_id,
                    media_url=payload.media_url,
                    bloque=current_bloque,
                    descripcion=payload.contenido or "",
                    validated=True,
                )

                session.add_foto(foto)
                session.current_foto_id = foto.id
                session.pending_marca = None
                session.estado = AuditState.SCORING_BRANDS_TAG
                save_session(session)

                marca_options = [
                    {"id": brand_id, "title": BRAND_LABELS.get(brand_id, brand_id)}
                    for brand_id in BRAND_ORDER
                ]

                await meta_client.send_list_message(
                    payload.telefono,
                    header="¿Qué marca es?",
                    body="Decila en un audio o escribí el nombre — no hace falta buscarla en la lista.",
                    footer="",
                    button_text="Selecciona una opción",
                    options=marca_options,
                )

                return "photo_received_awaiting_marca"

            except Exception as e:
                logger.error(f"Error downloading/validating photo: {e}")
                await meta_client.send_text(
                    payload.telefono,
                    "❌ Error procesando la foto. Por favor intenta de nuevo."
                )
                return "photo_download_error"

        await meta_client.send_text(
            payload.telefono,
            "Para reportar una marca, mandame una *foto*. "
            "Cuando termines con Ofertas, escribí 'SIGUIENTE'."
        )
        return "unsupported_media"

    @staticmethod
    async def handle_ofertas_marca_tag(payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession) -> str:
        """Espera qué marca es la foto recién recibida: un tap de la lista
        (llega como texto con el id de BRAND_ORDER) o el nombre escrito a
        mano para una marca no contemplada — ambos casos se aceptan por
        igual, sin un paso extra de "otra marca"."""
        current_bloque = BloqueType.OFERTAS.value
        bloque_label = BLOQUE_LABELS.get(current_bloque, current_bloque)

        # La auditora puede DECIR la marca en un audio en vez de escribirla o
        # buscarla en la lista — es lo mas rapido con el celular en la mano.
        raw_text = ""
        if payload.tipo == "audio" and payload.media_id:
            try:
                media_bytes, mime_type = await meta_client.download_media_with_metadata(payload.media_id)
                raw_text = (await AudioTranscriber().transcribe_bytes(media_bytes, mime_type) or "").strip()
            except Exception as e:
                logger.warning(f"No se pudo transcribir la marca dictada {payload.media_id}: {e}")
            if not raw_text:
                await meta_client.send_text(
                    payload.telefono,
                    "No te llegué a entender. Decime la marca de nuevo, o escribila."
                )
                return "marca_audio_sin_transcripcion"
        elif payload.tipo == "text" and payload.contenido.strip():
            raw_text = payload.contenido.strip()
        else:
            await meta_client.send_text(
                payload.telefono,
                "Decime qué marca es: mandá un audio diciéndola, escribí el nombre, o elegí una de la lista."
            )
            return "invalid_input"

        # "siguiente" es una orden de avanzar, NO el nombre de una marca.
        if _es_comando_ofertas(raw_text):
            session.pending_marca = None
            session.current_foto_id = None
            save_session(session)
            await meta_client.send_text(
                payload.telefono,
                "Dale, cierro Ofertas. La última foto quedó sin marca asignada, así que no la registré."
            )
            return await AuditConversationHandler._finish_bloque_evidence(
                meta_client, session, payload.telefono, current_bloque, bloque_label
            )

        marca_id = raw_text.lower()

        if marca_id in BRAND_ORDER:
            marca_label = BRAND_LABELS.get(marca_id, marca_id)
        else:
            marca_label = raw_text[:60]
            marca_id = marca_label

        session.pending_marca = marca_id

        foto = next((f for f in session.fotos if f.id == session.current_foto_id), None)
        if foto:
            foto.marca = marca_id

        session.estado = AuditState.SCORING_BRANDS_COMMENT
        save_session(session)

        await meta_client.send_text(
            payload.telefono,
            f"📝 {marca_label}\n\nContame cómo está esta marca — mandá un audio o escribí un comentario."
        )

        return "marca_tagged"

    @staticmethod
    async def handle_ofertas_marca_comment(payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession) -> str:
        """Espera el comentario/audio que cierra el hallazgo de la marca
        recién etiquetada. Si en cambio llega una foto nueva, la auditora está
        arrancando el registro de otra marca — se re-enruta al branch de foto
        de handle_ofertas_marca_evidence, y la marca anterior queda con foto
        pero sin comentario (mismo comportamiento que ya existe hoy cuando una
        foto nueva reemplaza el ancla de un hallazgo sin cerrar)."""
        current_bloque = BloqueType.OFERTAS.value
        marca_label = BRAND_LABELS.get(session.pending_marca, session.pending_marca or "la marca")

        if payload.tipo == "image":
            return await AuditConversationHandler.handle_ofertas_marca_evidence(payload, meta_client, session)

        if payload.tipo == "text":
            raw_text = payload.contenido.strip()

            if _es_asentimiento(raw_text):
                await meta_client.send_text(
                    payload.telefono,
                    f"Contame algo sobre cómo está {marca_label} (texto o audio) para guardar el hallazgo."
                )
                return "acknowledgement_ignored"

            # "siguiente" acá es una orden de avanzar, no el comentario de la
            # marca: antes se guardaba literalmente como el hallazgo.
            if _es_comando_ofertas(raw_text):
                session.add_desvio(
                    bloque=current_bloque,
                    descripcion="Sin comentario",
                    fotos=[session.current_foto_id] if session.current_foto_id else None,
                    marca=session.pending_marca,
                )
                session.pending_marca = None
                session.current_foto_id = None
                save_session(session)
                await meta_client.send_text(
                    payload.telefono,
                    f"✓ {marca_label} registrada con foto, sin comentario. Cierro Ofertas."
                )
                return await AuditConversationHandler._finish_bloque_evidence(
                    meta_client, session, payload.telefono, current_bloque,
                    BLOQUE_LABELS.get(current_bloque, current_bloque),
                )

            session.add_desvio(
                bloque=current_bloque,
                descripcion=raw_text,
                fotos=[session.current_foto_id] if session.current_foto_id else None,
                marca=session.pending_marca,
            )
            session.pending_marca = None
            session.current_foto_id = None
            session.estado = AuditState.SCORING_BRANDS
            save_session(session)

            await meta_client.send_quick_reply(
                payload.telefono,
                f"✓ {marca_label} registrada con foto y comentario\n\n"
                f"¿Otra marca? Mandá otra foto, o escribí 'SIGUIENTE'.",
                [SIGUIENTE_BUTTON],
            )

            return "marca_comment_saved"

        if payload.tipo == "audio" and payload.media_id:
            transcript = ""
            try:
                media_bytes, mime_type = await meta_client.download_media_with_metadata(payload.media_id)
                transcript = await AudioTranscriber().transcribe_bytes(media_bytes, mime_type)
            except Exception as e:
                logger.warning(f"No se pudo transcribir audio {payload.media_id}: {e}")

            audio_description = f"[AUDIO] {transcript.strip() if transcript else 'Sin transcripción'}"
            session.add_desvio(
                bloque=current_bloque,
                descripcion=audio_description,
                fotos=[session.current_foto_id] if session.current_foto_id else None,
                marca=session.pending_marca,
            )
            session.pending_marca = None
            session.current_foto_id = None
            session.estado = AuditState.SCORING_BRANDS
            save_session(session)

            await meta_client.send_quick_reply(
                payload.telefono,
                f"✓ {marca_label} registrada con foto y audio\n\n"
                f"¿Otra marca? Mandá otra foto, o escribí 'SIGUIENTE'.",
                [SIGUIENTE_BUTTON],
            )

            return "marca_comment_saved"

        await meta_client.send_text(
            payload.telefono,
            f"Contame cómo está {marca_label}: mandá un audio o escribí un comentario."
        )
        return "unsupported_media"

    @staticmethod
    async def handle_evidence(payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession) -> str:
        """Handle evidence input (photos or 'Listo')."""

        if payload.tipo == "text":
            texto = payload.contenido.lower().strip()

            # Check for "Listo" (done with photos)
            if "listo" in texto or "listo" in texto or "done" in texto:
                session.estado = AuditState.SUMMARY
                save_session(session)

                # Generate summary
                return await AuditConversationHandler.send_summary(payload.telefono, meta_client, session)

            # Check if it's a bloque selection after photo
            bloque_match = None

            # Try to match by number (1-4)
            if texto.isdigit():
                bloque_num = int(texto)
                if 1 <= bloque_num <= 4:
                    bloque_match = BLOQUE_ORDER[bloque_num - 1]

            # If not matched by number, try by name
            if not bloque_match:
                for bloque in BLOQUE_ORDER:
                    if bloque.lower() in texto:
                        bloque_match = bloque
                        break

            if bloque_match and session.fotos:
                # User is specifying the bloque for the last photo
                last_foto = session.fotos[-1]
                last_foto.bloque = bloque_match
                save_session(session)

                bloque_label = BLOQUE_LABELS.get(bloque_match, bloque_match)
                await meta_client.send_text(
                    payload.telefono,
                    f"✓ Foto vinculada a {bloque_label}\n\n"
                    f"¿Cuál es el problema observado?\n"
                    f"(O envía 'Listo' si terminas)"
                )

                return "bloque_assigned"

            # Otherwise treat as desvio description for the bloque
            if session.fotos and session.fotos[-1].bloque:
                bloque = session.fotos[-1].bloque
                session.add_desvio(bloque=bloque, descripcion=texto)
            else:
                session.add_desvio(bloque="UNKNOWN", descripcion=texto)

            save_session(session)

            await meta_client.send_text(
                payload.telefono,
                f"✓ Guardado: {texto}\n\n"
                f"¿Otra foto o escribe 'Listo'?"
            )

            return "desvio_saved"

        elif payload.tipo == "image":
            # Handle photo with validation
            if not payload.media_id:
                await meta_client.send_text(
                    payload.telefono,
                    "❌ No puedo procesar esa imagen. Por favor intenta de nuevo."
                )
                return "no_media_id"

            try:
                # Download and validate photo
                media_bytes, mime_type = await meta_client.download_media_with_metadata(
                    payload.media_id
                )

                validation = PhotoValidator.validate_media_bytes(media_bytes, mime_type)

                if not validation.is_valid:
                    # Photo is invalid
                    await meta_client.send_text(
                        payload.telefono,
                        validation.message
                        + "\n\n"
                        + "Intenta de nuevo o escribe 'Listo' para continuar."
                    )
                    return "photo_invalid"

                # Photo is valid - store it
                foto = FotoEvidence(
                    id=f"foto_{int(datetime.now(timezone.utc).timestamp())}",
                    media_id=payload.media_id,
                    media_url=payload.media_url,
                    bloque=None,  # Will ask user
                    descripcion=payload.contenido or "",  # Photo caption
                    validated=True,
                )

                session.add_foto(foto)
                save_session(session)

                await meta_client.send_text(
                    payload.telefono,
                    f"✓ Foto guardada correctamente.\n\n"
                    f"¿De qué área es?\n\n"
                    f"1. Limpieza\n"
                    f"2. Stock\n"
                    f"3. Ofertas\n"
                    f"4. Burbujas"
                )

                return "photo_received"

            except Exception as e:
                logger.error(f"Error downloading/validating photo: {e}")
                await meta_client.send_text(
                    payload.telefono,
                    "❌ Error procesando la foto. Por favor intenta de nuevo."
                )
                return "photo_download_error"

        await meta_client.send_text(
            payload.telefono,
            "No puedo usar ese tipo de mensaje como evidencia.\n\n"
            "Mandame una *foto* o escribí el problema en texto."
        )
        return "unsupported_media"

    @staticmethod
    async def generate_and_send_ficha(
        payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession
    ) -> str:
        """Generate PDF ficha and send to user."""

        try:
            # Get sucursal name from somewhere (we have sucursal_id)
            # For now use sucursal_id as fallback
            sucursal_nombre = session.sucursal_id

            # Get responsable if exists
            responsable = session.desvios_responsable

            # Generate PDF
            pdf_bytes = generate_audit_pdf(
                session=session,
                sucursal_nombre=sucursal_nombre,
                auditor_nombre=session.auditor_nombre,
                responsable_desvios=responsable,
            )

            # Save PDF temporarily and send
            # Note: In production, upload to Google Drive or S3
            filename = f"Auditoria_{session.id_sesion}.pdf"

            await meta_client.send_text(
                payload.telefono,
                f"📄 Ficha de auditoría generada.\n\n"
                f"ID: {session.id_sesion}\n"
                f"Archivo: {filename}\n\n"
                f"✅ Auditoría completada. ¡Gracias!"
            )

            # TODO: Send PDF file using meta_client.send_file()
            # await meta_client.send_file(payload.telefono, pdf_url, caption="Ficha de auditoría")

            logger.info(f"Generated ficha PDF for session {session.id_sesion}")
            return "ficha_sent"

        except Exception as e:
            logger.error(f"Error generating ficha: {e}")
            await meta_client.send_text(
                payload.telefono,
                "❌ Error generando la ficha. Por favor contacta al soporte."
            )
            return "ficha_error"

    @staticmethod
    async def send_summary(telefono: str, meta_client: MetaClient, session: AuditSession) -> str:
        """Generate and send audit summary."""

        # Build summary message
        summary = f"📋 RESUMEN DE AUDITORÍA\n\n"
        summary += f"📍 Sucursal: {session.sucursal_id}\n"
        summary += f"⏰ {datetime.fromisoformat(session.started_at).strftime('%d/%m/%Y %H:%M')}\n\n"

        # Puntuaciones
        summary += "📊 PUNTUACIONES:\n"
        for bloque in BLOQUE_ORDER:
            score = session.bloques.get(bloque)
            label = BLOQUE_LABELS.get(bloque, bloque)
            summary += f"  {label}: {score}/5\n"

            if bloque == BloqueType.OFERTAS.value:
                marcas_reportadas = [d for d in session.desvios if d.bloque == bloque and d.marca]
                for desvio in marcas_reportadas:
                    marca_label = BRAND_LABELS.get(desvio.marca, desvio.marca)
                    preview = desvio.descripcion[:60] + ("…" if len(desvio.descripcion) > 60 else "")
                    summary += f"    • {marca_label}: {preview}\n"

        # Desvios
        if session.desvios:
            summary += f"\n⚠️ DESVÍOS ENCONTRADOS ({len(session.desvios)}):\n"
            for desvio in session.desvios:
                marca_prefix = f"[{BRAND_LABELS.get(desvio.marca, desvio.marca)}] " if desvio.marca else ""
                summary += f"  • {marca_prefix}{desvio.descripcion}\n"

        # Fotos
        if session.fotos:
            summary += f"\n📷 FOTOS: {len(session.fotos)}\n"

        # Verificaciones de desvíos previos
        if session.verified_resueltos or session.verified_persisten:
            summary += (
                f"\n🔁 VERIFICACIONES PREVIAS: "
                f"{session.verified_resueltos} resuelto(s) · {session.verified_persisten} persiste(n)\n"
            )

        summary += f"\n¿Confirmas envío?"

        # Send summary with quick reply buttons for confirmation
        await meta_client.send_text(telefono, summary)
        await meta_client.send_quick_reply(
            telefono,
            "¿Enviar auditoría?",
            [
                {"id": "si", "title": "✅ Sí, enviar"},
                {"id": "no", "title": "❌ No, editar"}
            ]
        )

        return "summary_sent"

    @staticmethod
    async def handle_confirmation(payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession) -> str:
        """Handle final confirmation (Sí/No)."""

        if payload.tipo != "text":
            await meta_client.send_text(
                payload.telefono,
                "Por favor responde:\n1. Sí, enviar\n2. No, editar"
            )
            return "invalid_input"

        texto = payload.contenido.lower().strip()

        # Acepta "si", "✅ sí, enviar", "1". Por token exacto y chequeando la
        # negativa primero: antes "no sirve" confirmaba la auditoría.
        if _es_afirmativo(texto):
            # Save to DB
            try:
                result = await save_audit_to_database(session, meta_client)
                logger.info(f"Audit session {session.id_sesion} saved to database")

                # Store reporte_id in session so ficha can be generated after responsable is collected
                reporte_id = result.get("id_reporte") if isinstance(result, dict) else None
                session.pending_ficha_reporte_id = reporte_id
                session.pending_ficha_gestion_ids = result.get("gestion_ids", []) if isinstance(result, dict) else []

                # Manager notification (non-blocking)
                try:
                    await send_manager_notification(
                        payload.telefono, session.sucursal_id, meta_client,
                        auditor_nombre=session.auditor_nombre,
                        desvio_count=len(session.desvios),
                    )
                except Exception as e:
                    logger.warning(f"Failed to send manager notification: {e}")

            except Exception as e:
                logger.error(f"Error saving audit to database: {e}")
                await meta_client.send_text(
                    payload.telefono,
                    "⚠️ Error guardando en BD, pero tu auditoría fue registrada.\n"
                    f"ID: {session.id_sesion}"
                )
                return "audit_saved_local_only"

            desvio_count = len(session.desvios)

            if desvio_count > 0:
                # Ask for responsable before generating ficha (so PDF includes the name)
                await meta_client.send_text(
                    payload.telefono,
                    f"✅ ¡Auditoría guardada!\n\n"
                    f"ID: {session.id_sesion}\n"
                    f"Fotos: {len(session.fotos)}\n"
                    f"Desvíos: {desvio_count}\n\n"
                    f"Gerente notificado de {desvio_count} hallazgo(s)\n\n"
                    f"¿A nombre de quién se registran los desvíos?\n"
                    f"(Escribe el nombre del responsable)"
                )
                session.estado = AuditState.DONE
                session.desvios_responsable = None
                save_session(session)
                return "awaiting_responsable_name"
            else:
                # No desvios — generate ficha immediately, then send link
                session.estado = AuditState.DONE
                save_session(session)

                ficha_url: Optional[str] = None
                reporte_id = session.pending_ficha_reporte_id
                if reporte_id:
                    try:
                        ficha_url = await AuditFichesManager.generate_and_save_ficha(
                            session=session,
                            reporte_id=reporte_id,
                            responsable_desvios=None,
                            meta_client=meta_client,
                        )
                    except Exception as ficha_exc:
                        logger.warning(f"Ficha generation failed (no desvios path): {ficha_exc}")

                await meta_client.send_text(
                    payload.telefono,
                    f"✅ ¡Auditoría guardada!\n\nID: {session.id_sesion}",
                )

                if ficha_url:
                    # No desvíos found — nothing for the manager to resolve or
                    # be notified about, just offer the auditor her PDF copy.
                    await _ask_ficha_download(
                        meta_client, payload.telefono, session, ficha_url
                    )
                else:
                    delete_session(payload.telefono)
                    await meta_client.send_text(
                        payload.telefono, "La ficha fue guardada en el sistema."
                    )

                return "audit_saved"

        elif _es_negativo(texto):
            # Antes esto preguntaba "¿que queres cambiar?" y no hacia nada
            # mas: la sesion se quedaba en SUMMARY, asi que el siguiente
            # mensaje del auditor (la respuesta a esa pregunta) volvia a caer
            # en este mismo handler, no matcheaba ni si ni no, y terminaba en
            # el "responde 1 o 2" de mas abajo. Loop muerto real, sin salida.
            #
            # Fix: reinicia el puntaje desde el primer bloque. Las fotos y
            # notas ya cargadas NO se pierden — si un bloque ya esta bien,
            # alcanza con puntuarlo de nuevo y escribir 'SIGUIENTE' sin
            # repetir evidencia.
            session.current_bloque_index = 0
            await AuditConversationHandler.enter_bloque(
                meta_client, session,
                intro_msg=(
                    "Dale, volvemos a puntuar desde el primer bloque. Las fotos y notas que ya "
                    "cargaste se mantienen — si un bloque ya está bien, puntualo de nuevo y "
                    "escribí 'SIGUIENTE' para pasar sin repetir nada."
                ),
            )

            return "audit_edit_restarted"

        else:
            await meta_client.send_text(
                payload.telefono,
                "Por favor responde:\n1. Sí, enviar\n2. No, editar"
            )
            return "invalid_input"

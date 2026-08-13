"""Message handlers for audit conversation states."""

import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import logging
from typing import Optional, Tuple
from audit_session import (
    AuditSession, AuditState, create_session, get_session, save_session,
    delete_session, BloqueType, BrandType, BLOQUE_ORDER, BRAND_ORDER,
    BLOQUE_LABELS, BRAND_LABELS, BLOQUE_DESCRIPTIONS, FotoEvidence,
)
from models import WhatsAppPayload
from meta_client import MetaClient
from photo_validator import PhotoValidator, PhotoValidationResult
from audio import AudioTranscriber
from audit_database import save_audit_to_database, send_manager_notification, get_previous_audit
from supabase_manager import SupabaseManager
from audit_pdf_generator import generate_audit_pdf
from audit_fiches_manager import AuditFichesManager
from config import get_settings
from datetime import datetime, timezone

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
        db = SupabaseManager()
        sucursal = db.get_sucursal(session.sucursal_id)
        tel = sucursal.tel_responsable if sucursal else None
        if not tel:
            logger.info(f"No tel_responsable for sucursal {session.sucursal_id} — skipping notice")
            return

        cantidad = len(session.desvios)
        texto = (
            f"🚨 Se detectaron {cantidad} desvío(s) en tu sucursal durante la auditoría de hoy.\n\n"
            f"Tu auditor/a te va a compartir el detalle con fotos y comentarios por WhatsApp. "
            f"Cuando resuelvas alguno, escribinos a este mismo número para actualizarlo."
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

        # Active session: route by state
        if session.estado == AuditState.IDLE:
            return await AuditConversationHandler.handle_init(payload, meta_client)

        elif session.estado == AuditState.SELECT_SUCURSAL:
            return await AuditConversationHandler.handle_select_sucursal(payload, meta_client, session)

        elif session.estado == AuditState.VERIFY_SELECT_SUCURSAL:
            return await AuditConversationHandler.handle_verify_sucursal_selection(payload, meta_client, session)

        elif session.estado == AuditState.VERIFY_PREVIOUS:
            return await AuditConversationHandler.handle_verification(payload, meta_client, session)

        elif session.estado == AuditState.SCORING:
            return await AuditConversationHandler.handle_score(payload, meta_client, session)

        elif session.estado == AuditState.BLOQUE_EVIDENCE_COLLECTION:
            return await AuditConversationHandler.handle_bloque_evidence(payload, meta_client, session)

        elif session.estado == AuditState.SCORING_BRANDS:
            return await AuditConversationHandler.handle_brand_score(payload, meta_client, session)

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
                            # Short heads-up to the manager (no PDF) — the detailed
                            # report is sent by the auditor personally, see below.
                            await _notify_responsable_desvios_pendientes(meta_client, session)
                            # Give the auditor a ready-to-forward invitation text
                            # (with the bot's number) to send along with the PDF.
                            await _send_forward_invitation_text(meta_client, session, payload.telefono)
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
            f"¿Cómo está hoy?",
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

        # Check if it's OFERTAS → move to SCORING_BRANDS
        if current_bloque == BloqueType.OFERTAS.value:
            session.estado = AuditState.SCORING_BRANDS
            session.current_brand_index = 0
            save_session(session)

            primer_brand = BRAND_ORDER[0]
            brand_label = BRAND_LABELS.get(primer_brand, primer_brand)

            score_options = [
                {"id": "1", "title": "Muy malo", "description": "Crítico"},
                {"id": "2", "title": "Malo", "description": "Problemas"},
                {"id": "3", "title": "Regular", "description": "Mejora necesaria"},
                {"id": "4", "title": "Bueno", "description": "Bien"},
                {"id": "5", "title": "Excelente", "description": "Perfecto"},
            ]

            await meta_client.send_list_message(
                payload.telefono,
                header="Marca 1/4: " + brand_label,
                body=f"✓ Ofertas: {score}/5\n\nDesglose por marca\n(Exhibición, disponibilidad, precios)\n\n¿Cuál es tu puntuación?",
                footer="Marca: " + brand_label,
                button_text="Selecciona una opción",
                options=score_options
            )

            return "moved_to_brands"

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
    async def handle_bloque_evidence(payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession) -> str:
        """Handle evidence collection for current bloque (fotos, audios, textos)."""

        current_bloque = session.get_current_bloque()
        bloque_label = BLOQUE_LABELS.get(current_bloque, current_bloque)

        # Check for "SIGUIENTE" to move to next bloque
        if payload.tipo == "text":
            texto = payload.contenido.upper().strip()

            if "SIGUIENTE" in texto or "NEXT" in texto:
                # Count evidence collected
                bloque_fotos = len([f for f in session.fotos if f.bloque == current_bloque])
                bloque_audios = len([a for a in session.desvios if a.bloque == current_bloque and "[AUDIO]" in a.descripcion])
                bloque_notas = len([d for d in session.desvios if d.bloque == current_bloque and "[AUDIO]" not in d.descripcion])

                # Photo is mandatory for every controlled point, good or bad
                if bloque_fotos == 0:
                    await meta_client.send_text(
                        payload.telefono,
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

                return await AuditConversationHandler.send_summary(payload.telefono, meta_client, session)

            # Texto sin "SIGUIENTE" — flujo libre: se guarda directo como nota,
            # ligada a la ultima foto recibida en este bloque (si hay una).
            raw_text = payload.contenido.strip()

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
    async def handle_brand_score(payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession) -> str:
        """Handle brand score input for OFERTAS."""

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
        current_brand = session.get_current_brand()

        # Save score
        session.set_brand_score(current_brand, score)

        # Move to next brand or back to SCORING
        if session.move_to_next_brand():
            next_brand = session.get_current_brand()
            next_label = BRAND_LABELS.get(next_brand, next_brand)
            brand_num = session.current_brand_index + 1

            save_session(session)

            score_options = [
                {"id": "1", "title": "Muy malo", "description": "Crítico"},
                {"id": "2", "title": "Malo", "description": "Problemas"},
                {"id": "3", "title": "Regular", "description": "Mejora necesaria"},
                {"id": "4", "title": "Bueno", "description": "Bien"},
                {"id": "5", "title": "Excelente", "description": "Perfecto"},
            ]

            await meta_client.send_list_message(
                payload.telefono,
                header=f"Marca {brand_num}/4: {next_label}",
                body=f"✓ {BRAND_LABELS.get(current_brand, current_brand)}: {score}/5\n\n¿Cuál es tu puntuación?",
                footer=f"Marca: {next_label}",
                button_text="Selecciona una opción",
                options=score_options
            )

            return "next_brand"

        # All brands scored → move to evidence collection for OFERTAS
        session.estado = AuditState.BLOQUE_EVIDENCE_COLLECTION
        save_session(session)

        bloque_desc = BLOQUE_DESCRIPTIONS.get(BloqueType.OFERTAS.value, "")

        await meta_client.send_text(
            payload.telefono,
            f"✓ {BRAND_LABELS.get(current_brand, current_brand)}: {score}/5\n\n"
            f"📸 Enviá al menos UNA foto de Ofertas (esté bien o mal — la foto es obligatoria).\n"
            f"También podés sumar audios y notas 🎙️📝\n\n"
            f"{bloque_desc}\n\n"
            f"Escribe 'SIGUIENTE' cuando termines este bloque"
        )

        return "ofertas_evidence_collection_started"

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

            if bloque == BloqueType.OFERTAS.value and BloqueType.OFERTAS.value in session.brands:
                brand_scores = session.brands[BloqueType.OFERTAS.value]
                if brand_scores:
                    summary += f"  {label}: {score}/5\n"
                    for brand_id in BRAND_ORDER:
                        if brand_id in brand_scores:
                            brand_label = BRAND_LABELS.get(brand_id, brand_id)
                            brand_score = brand_scores[brand_id]
                            summary += f"    • {brand_label}: {brand_score}/5\n"
                else:
                    summary += f"  {label}: {score}/5\n"
            else:
                summary += f"  {label}: {score}/5\n"

        # Desvios
        if session.desvios:
            summary += f"\n⚠️ DESVÍOS ENCONTRADOS ({len(session.desvios)}):\n"
            for desvio in session.desvios:
                summary += f"  • {desvio.descripcion}\n"

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
                        payload.telefono, session.sucursal_id, meta_client
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
            # Ask what to change
            await meta_client.send_text(
                payload.telefono,
                "¿Qué quieres cambiar?\n"
                "Puedo volver a las puntuaciones, agregar/quitar fotos, o editar descripciones."
            )

            return "audit_edit_requested"

        else:
            await meta_client.send_text(
                payload.telefono,
                "Por favor responde:\n1. Sí, enviar\n2. No, editar"
            )
            return "invalid_input"

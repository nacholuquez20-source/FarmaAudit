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
    BLOQUE_LABELS, BRAND_LABELS, BLOQUE_DESCRIPTIONS, FotoEvidence
)
from models import WhatsAppPayload
from meta_client import MetaClient
from photo_validator import PhotoValidator, PhotoValidationResult
from audit_database import save_audit_to_database, send_manager_notification, get_previous_audit
from supabase_manager import SupabaseManager
from audit_pdf_generator import generate_audit_pdf
from audit_fiches_manager import AuditFichesManager
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# Predefined notes templates by bloque
NOTES_TEMPLATES = {
    "LIMPIEZA": [
        {"id": "1", "title": "Góndolas desorganizadas"},
        {"id": "2", "title": "Polvo/suciedad en estantes"},
        {"id": "3", "title": "Falta de reposición"},
        {"id": "4", "title": "Desorden en piso"},
        {"id": "5", "title": "Señalización sucia/faltante"},
    ],
    "STOCK": [
        {"id": "1", "title": "Productos vencidos"},
        {"id": "2", "title": "Falta de stock"},
        {"id": "3", "title": "Exceso de inventario"},
        {"id": "4", "title": "Productos mal ubicados"},
        {"id": "5", "title": "Falta rotulación de precios"},
    ],
    "OFERTAS": [
        {"id": "1", "title": "Promociones incorrectas"},
        {"id": "2", "title": "Precios no actualizados"},
        {"id": "3", "title": "Exhibición desordenada"},
        {"id": "4", "title": "Falta de material promocional"},
        {"id": "5", "title": "Marcas no destacadas"},
    ],
    "BURBUJAS": [
        {"id": "1", "title": "Displays dañados"},
        {"id": "2", "title": "Señalización ilegible"},
        {"id": "3", "title": "Falta de displays"},
        {"id": "4", "title": "Material vencido/desgastado"},
        {"id": "5", "title": "Ubicación incorrecta"},
    ],
}


SCORE_OPTIONS = [
    {"id": "1", "title": "Muy malo", "description": "Crítico, acción inmediata"},
    {"id": "2", "title": "Malo", "description": "Problemas significativos"},
    {"id": "3", "title": "Regular", "description": "Necesita mejora"},
    {"id": "4", "title": "Bueno", "description": "Bien, algunos detalles"},
    {"id": "5", "title": "Excelente", "description": "Cumple perfectamente"},
]

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


async def _send_ficha_to_responsable(
    meta_client: MetaClient,
    session: AuditSession,
    ficha_url: str,
    id_sesion: str,
) -> None:
    """Send PDF ficha to the branch manager via WhatsApp (best-effort, never raises)."""
    try:
        db = SupabaseManager()
        sucursal = db.get_sucursal(session.sucursal_id)
        tel = sucursal.tel_responsable if sucursal else None
        if not tel:
            logger.info(f"No tel_responsable for sucursal {session.sucursal_id} — skipping PDF delivery")
            return

        filename = f"Auditoria_{id_sesion}.pdf"
        caption = (
            f"📋 Informe de auditoría — {sucursal.nombre if sucursal else session.sucursal_id}\n"
            f"Auditor: {session.auditor_nombre or '—'}"
        )

        download_url = await _ficha_download_url(ficha_url)
        ok = await meta_client.send_document(tel, download_url, filename, caption)
        if ok:
            logger.info(f"PDF ficha sent to manager at {tel}")
        else:
            logger.warning(f"Failed to send PDF ficha to manager at {tel}")
    except Exception as e:
        logger.warning(f"Could not send PDF to responsable: {e}")


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
            # Check if it's a command to start audit
            if payload.tipo == "text":
                texto = payload.contenido.lower().strip()
                # Check if mentions audit or sucursal
                if any(word in texto for word in ["auditoria", "audit", "perfumeria", "farmacia"]):
                    return await AuditConversationHandler.handle_init(payload, meta_client)

            # Otherwise ask to start
            await meta_client.send_text(
                telefono,
                "Hola 👋\n\n"
                "Para iniciar una auditoría de perfumería, por favor responde con el ID de la sucursal\n"
                "Ejemplo: SC-001"
            )
            return "awaiting_sucursal_id"

        # Active session: route by state
        if session.estado == AuditState.IDLE:
            return await AuditConversationHandler.handle_init(payload, meta_client)

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

                # Keyword fallback: ask for ficha explicitly
                if any(word in texto for word in ["ficha", "pdf", "documento", "descargar"]):
                    return await AuditConversationHandler.generate_and_send_ficha(
                        payload, meta_client, session
                    )

                # Check if user entered responsable name (when there are desvios)
                if session.desvios_responsable is None:
                    if len(session.desvios) > 0:
                        session.desvios_responsable = payload.contenido.strip()

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
                            # Send PDF to branch manager
                            await _send_ficha_to_responsable(
                                meta_client, session, ficha_url, session.id_sesion
                            )
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

            return "audit_already_completed"

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
        """Enter current bloque: verify pending desvíos from previous audits, then scoring."""
        telefono = session.telefono
        bloque = session.get_current_bloque()

        pendientes = []
        try:
            db = SupabaseManager()
            pendientes = db.get_gestiones_pendientes_bloque(session.sucursal_id, bloque)
        except Exception as e:
            logger.warning(f"Could not fetch pending gestiones for {session.sucursal_id}/{bloque}: {e}")

        if intro_msg:
            await meta_client.send_text(telefono, intro_msg)

        if not pendientes:
            session.estado = AuditState.SCORING
            save_session(session)
            await AuditConversationHandler._send_scoring_list(meta_client, telefono, session)
            return "scoring_started"

        session.pending_verifications = AuditConversationHandler._queue_from_gestiones(pendientes)
        session.current_verification_index = 0
        session.awaiting_verification_photo = False
        session.estado = AuditState.VERIFY_PREVIOUS
        save_session(session)

        label = BLOQUE_LABELS.get(bloque, bloque)
        await meta_client.send_text(
            telefono,
            f"📋 Hay {len(pendientes)} desvío(s) pendiente(s) de {label} en esta sucursal.\n"
            f"Verifiquemos antes de puntuar."
        )
        await AuditConversationHandler._send_current_verification(meta_client, session)
        return "verification_started"

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
    async def handle_init(payload: WhatsAppPayload, meta_client: MetaClient) -> str:
        """Initialize new audit session."""

        telefono = payload.telefono
        texto = payload.contenido.strip() if payload.tipo == "text" else ""

        # Extract sucursal_id from message or ask for it
        sucursal_id = texto.upper() if texto else None

        if not sucursal_id:
            await meta_client.send_text(
                telefono,
                "Por favor, indícame el ID de la sucursal\n"
                "Ejemplo: SC-001"
            )
            return "awaiting_sucursal_id"

        # TODO: Validate sucursal exists in DB
        # For now, assume it exists
        session = create_session(
            telefono=telefono,
            sucursal_id=sucursal_id,
            auditor_nombre=None  # Could get from Supabase if needed
        )

        session.started_at = datetime.now(timezone.utc).isoformat()
        save_session(session)

        # Enter first bloque: verify pending desvíos, then scoring
        await AuditConversationHandler.enter_bloque(
            meta_client, session, intro_msg=f"✓ Auditoría iniciada: {sucursal_id}"
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
            f"Documenta lo que observas 📸🎙️📝\n"
            f"Mandá al menos una foto de este bloque (obligatoria, haya o no desvío) "
            f"— también podés agregar audios o textos\n\n"
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

                # Al menos una foto es obligatoria por bloque, haya o no desvío, para
                # dejar registro de las condiciones del lugar (pedido de la auditora).
                if bloque_fotos == 0:
                    await meta_client.send_text(
                        payload.telefono,
                        f"📸 Falta la foto de {bloque_label}.\n\n"
                        f"Necesito al menos una foto de este bloque para dejar registro, "
                        f"aunque no hayas encontrado ningún desvío. Mandala y después "
                        f"escribí 'SIGUIENTE' para continuar."
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

            # Text without "SIGUIENTE" → save as note/desvio for this bloque
            texto = payload.contenido.strip()
            session.add_desvio(bloque=current_bloque, descripcion=texto)
            save_session(session)

            await meta_client.send_text(
                payload.telefono,
                f"✓ Nota guardada en {bloque_label}\n\n"
                f"¿Algo más? (foto, audio, texto, o 'SIGUIENTE')"
            )

            return "note_saved"

        # Check if user is selecting from predefined notes
        if payload.tipo == "text":
            texto_lower = payload.contenido.lower().strip()

            # Check if message is asking for note templates
            if any(word in texto_lower for word in ["problema", "nota", "problema", "template", "plantilla"]):
                templates = NOTES_TEMPLATES.get(current_bloque, [])
                if templates:
                    await meta_client.send_list_message(
                        payload.telefono,
                        header=f"Problemas comunes en {bloque_label}",
                        body=f"Selecciona un problema o escribe uno personalizado:\n\n{bloque_label}",
                        footer="O envía 'SIGUIENTE' para continuar",
                        button_text="Selecciona un problema",
                        options=templates
                    )
                    return "showing_templates"

        elif payload.tipo == "image":
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
                save_session(session)

                await meta_client.send_text(
                    payload.telefono,
                    f"✓ Foto guardada en {bloque_label}\n\n"
                    f"¿Algo más?"
                )

                # Offer predefined notes for this bloque
                templates = NOTES_TEMPLATES.get(current_bloque, [])
                if templates:
                    await meta_client.send_list_message(
                        payload.telefono,
                        header=f"Describe el problema",
                        body=f"Problemas comunes en {bloque_label}:",
                        footer="O envía tu propia descripción",
                        button_text="Selecciona o agrega",
                        options=templates + [{"id": "otro", "title": "Escribir otro..."}]
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
                # Create a note marking it as audio
                audio_description = f"[AUDIO] {payload.contenido or 'Sin transcripción'}"
                session.add_desvio(bloque=current_bloque, descripcion=audio_description)
                save_session(session)

                await meta_client.send_text(
                    payload.telefono,
                    f"✓ Audio guardado en {bloque_label}\n\n"
                    f"¿Algo más?"
                )

                # Offer predefined notes
                templates = NOTES_TEMPLATES.get(current_bloque, [])
                if templates:
                    await meta_client.send_list_message(
                        payload.telefono,
                        header=f"Describe el problema",
                        body=f"Problemas comunes en {bloque_label}:",
                        footer="O envía 'SIGUIENTE'",
                        button_text="Agregar problema",
                        options=templates[:4] + [{"id": "siguiente", "title": "Siguiente bloque"}]
                    )

                return "audio_received"

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
            f"Documenta lo que observas en Ofertas 📸🎙️📝\n"
            f"Mandá al menos una foto de este bloque (obligatoria, haya o no desvío) "
            f"— también podés agregar audios o textos\n\n"
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

        # Accept "si", "✅ sí, enviar", "1" or other affirmative words
        if any(word in texto for word in ["sí", "si", "yes", "confirmo", "ok", "✅"]):
            # Save to DB
            try:
                result = await save_audit_to_database(session, meta_client)
                logger.info(f"Audit session {session.id_sesion} saved to database")

                # Store reporte_id in session so ficha can be generated after responsable is collected
                reporte_id = result.get("id_reporte") if isinstance(result, dict) else None
                session.pending_ficha_reporte_id = reporte_id

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
                    await _send_ficha_to_responsable(
                        meta_client, session, ficha_url, session.id_sesion
                    )
                    await _ask_ficha_download(
                        meta_client, payload.telefono, session, ficha_url
                    )
                else:
                    delete_session(payload.telefono)
                    await meta_client.send_text(
                        payload.telefono, "La ficha fue guardada en el sistema."
                    )

                return "audit_saved"

        elif any(word in texto for word in ["no", "editar", "cambiar", "modificar", "❌"]):
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

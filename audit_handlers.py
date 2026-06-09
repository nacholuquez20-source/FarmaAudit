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
    BloqueType, BrandType, BLOQUE_ORDER, BRAND_ORDER, BLOQUE_LABELS,
    BRAND_LABELS, BLOQUE_DESCRIPTIONS, BRAND_ORDER, FotoEvidence
)
from models import WhatsAppPayload
from meta_client import MetaClient
from photo_validator import PhotoValidator, PhotoValidationResult
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


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

        elif session.estado == AuditState.SCORING:
            return await AuditConversationHandler.handle_score(payload, meta_client, session)

        elif session.estado == AuditState.SCORING_BRANDS:
            return await AuditConversationHandler.handle_brand_score(payload, meta_client, session)

        elif session.estado == AuditState.EVIDENCE:
            return await AuditConversationHandler.handle_evidence(payload, meta_client, session)

        elif session.estado == AuditState.SUMMARY:
            return await AuditConversationHandler.handle_confirmation(payload, meta_client, session)

        elif session.estado == AuditState.DONE:
            return "audit_already_completed"

        return "unknown_state"

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

        # Move to SCORING state
        session.estado = AuditState.SCORING
        session.started_at = datetime.now(timezone.utc).isoformat()
        save_session(session)

        # Send first scoring question
        primer_bloque = BLOQUE_ORDER[0]
        bloque_label = BLOQUE_LABELS.get(primer_bloque, primer_bloque)
        bloque_desc = BLOQUE_DESCRIPTIONS.get(primer_bloque, "")

        await meta_client.send_text(
            telefono,
            f"✓ Auditoría iniciada: {sucursal_id}\n\n"
            f"Paso 1 de 4: {bloque_label}\n"
            f"{bloque_desc}\n\n"
            f"Puntúa de 1 (Muy malo) a 5 (Excelente)\n"
            f"⏳ Responde: 1, 2, 3, 4 o 5"
        )

        return "audit_started"

    @staticmethod
    async def handle_score(payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession) -> str:
        """Handle bloque score input."""

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

        # Save score
        session.set_bloque_score(current_bloque, score)

        # Check if it's OFERTAS → move to SCORING_BRANDS
        if current_bloque == BloqueType.OFERTAS.value:
            session.estado = AuditState.SCORING_BRANDS
            session.current_brand_index = 0
            save_session(session)

            primer_brand = BRAND_ORDER[0]
            brand_label = BRAND_LABELS.get(primer_brand, primer_brand)

            await meta_client.send_text(
                payload.telefono,
                f"✓ Ofertas: {score}/5\n\n"
                f"Desglose por marca:\n"
                f"Marca 1/4: {brand_label}\n"
                f"(Exhibición, disponibilidad, precios)\n\n"
                f"Responde: 1-5"
            )

            return "moved_to_brands"

        # Move to next bloque
        if session.move_to_next_bloque():
            next_bloque = session.get_current_bloque()
            next_label = BLOQUE_LABELS.get(next_bloque, next_bloque)
            next_desc = BLOQUE_DESCRIPTIONS.get(next_bloque, "")

            save_session(session)

            await meta_client.send_text(
                payload.telefono,
                f"✓ {BLOQUE_LABELS.get(current_bloque, current_bloque)}: {score}/5\n\n"
                f"Paso {session.current_bloque_index + 1} de 4: {next_label}\n"
                f"{next_desc}\n\n"
                f"Responde: 1-5"
            )

            return "next_bloque"

        # All bloques scored → move to EVIDENCE
        session.estado = AuditState.EVIDENCE
        save_session(session)

        await meta_client.send_text(
            payload.telefono,
            f"✓ {BLOQUE_LABELS.get(current_bloque, current_bloque)}: {score}/5\n\n"
            f"✅ Auditoría de puntuaciones completada!\n\n"
            f"Ahora necesito fotos de los problemas encontrados.\n\n"
            f"Áreas con problemas (3-4):\n"
            + "\n".join([f"  • {BLOQUE_LABELS.get(b, b)} ({s}/5)"
                        for b, s in session.bloques.items() if s <= 3])
            + f"\n\nEnvía fotos o escribe 'Listo' cuando termines"
        )

        return "moved_to_evidence"

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

            await meta_client.send_text(
                payload.telefono,
                f"✓ {BRAND_LABELS.get(current_brand, current_brand)}: {score}/5\n\n"
                f"Marca {brand_num}/4: {next_label}\n"
                f"Responde: 1-5"
            )

            return "next_brand"

        # All brands scored → move to next bloque (BURBUJAS)
        session.estado = AuditState.SCORING
        session.move_to_next_bloque()
        next_bloque = session.get_current_bloque()
        next_label = BLOQUE_LABELS.get(next_bloque, next_bloque)
        next_desc = BLOQUE_DESCRIPTIONS.get(next_bloque, "")

        save_session(session)

        await meta_client.send_text(
            payload.telefono,
            f"✓ {BRAND_LABELS.get(current_brand, current_brand)}: {score}/5\n\n"
            f"Paso 4 de 4: {next_label}\n"
            f"{next_desc}\n\n"
            f"Responde: 1-5"
        )

        return "back_to_scoring"

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
                    f"¿De qué área es? (Limpieza, Stock, Ofertas, Burbujas)"
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

        summary += f"\n¿Confirmas envío? (Sí/No)"

        await meta_client.send_text(telefono, summary)

        return "summary_sent"

    @staticmethod
    async def handle_confirmation(payload: WhatsAppPayload, meta_client: MetaClient, session: AuditSession) -> str:
        """Handle final confirmation (Sí/No)."""

        if payload.tipo != "text":
            await meta_client.send_text(
                payload.telefono,
                "Por favor responde 'Sí' para confirmar o 'No' para editar"
            )
            return "invalid_input"

        texto = payload.contenido.lower().strip()

        if any(word in texto for word in ["sí", "si", "yes", "confirmo", "ok", "yes"]):
            # Save to DB
            session.estado = AuditState.DONE
            save_session(session)

            # TODO: Call create_audit_records(session) to save to BD
            await meta_client.send_text(
                payload.telefono,
                f"✅ ¡Auditoría guardada!\n\n"
                f"ID: {session.id_sesion}\n"
                f"Gerente notificado de {len(session.desvios)} desvío(s)"
            )

            return "audit_saved"

        elif any(word in texto for word in ["no", "editar", "cambiar", "modificar"]):
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
                "Por favor responde 'Sí' para confirmar o 'No' para editar"
            )
            return "invalid_input"

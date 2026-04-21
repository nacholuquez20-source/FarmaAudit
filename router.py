"""Conversation router - state machine logic for audit interactions."""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from models import (
    ConversationState, WAHAPayload, Auditor, Conversacion,
    ParserResponse, Reporte, Gestion, Severidad
)
from sheets import SheetsManager
from parser import AuditParser
from audio import AudioTranscriber
from drive import DriveManager
from waha import WAHAClient

logger = logging.getLogger(__name__)


class ConversationRouter:
    """Routes messages based on conversation state."""

    def __init__(self):
        """Initialize router with dependencies."""
        self.sheets = SheetsManager()
        self.parser = AuditParser()
        self.transcriber = AudioTranscriber()
        self.drive = DriveManager()

    async def handle_message(
        self,
        payload: WAHAPayload,
        waha_client: WAHAClient,
    ) -> str:
        """Route message based on conversation state."""
        try:
            # Validate auditor
            auditor = self.sheets.get_auditor(payload.telefono)
            if not auditor or not auditor.activo:
                await waha_client.send_text(
                    payload.telefono,
                    "❌ No estás registrado como auditor. Contacta al coordinador.",
                )
                return "auditor_not_found"

            # Get conversation state
            conv = self.sheets.get_conversacion(payload.telefono)
            if not conv:
                conv = Conversacion(
                    telefono=payload.telefono,
                    estado_actual=ConversationState.IDLE,
                )

            # Route based on state
            if conv.estado_actual == ConversationState.IDLE:
                return await self._handle_idle_state(payload, auditor, waha_client)
            elif conv.estado_actual == ConversationState.ESPERANDO_CONFIRMACION:
                return await self._handle_confirmation_state(payload, conv, waha_client)
            elif conv.estado_actual == ConversationState.ESPERANDO_EDICION:
                return await self._handle_edition_state(payload, conv, waha_client)
            else:
                await waha_client.send_text(payload.telefono, "⚠️ Estado desconocido")
                return "unknown_state"
        except Exception as e:
            logger.error(f"Error handling message from {payload.telefono}: {e}")
            await waha_client.send_text(
                payload.telefono,
                "❌ Error procesando tu mensaje. Intenta de nuevo.",
            )
            return "error"

    async def _handle_idle_state(
        self,
        payload: WAHAPayload,
        auditor: Auditor,
        waha_client: WAHAClient,
    ) -> str:
        """Handle message in idle state."""
        # Check for special commands
        if payload.contenido and payload.contenido.startswith("/"):
            return await self._handle_command(payload, auditor, waha_client)

        # Process audit finding
        message_to_parse = payload.contenido or ""

        # If audio, transcribe first
        if payload.tipo == "audio" and payload.media_url:
            try:
                message_to_parse = await self.transcriber.transcribe_from_url(
                    payload.media_url
                )
            except Exception as e:
                logger.error(f"Failed to transcribe audio: {e}")
                await waha_client.send_text(
                    payload.telefono,
                    "❌ Error transcribiendo audio. Intenta de nuevo.",
                )
                return "transcription_error"

        # If image without text, ask for context
        if payload.tipo == "image" and not payload.contenido:
            await waha_client.send_text(
                payload.telefono,
                "📸 Recibí la foto. ¿Qué hallazgo describe? Enviame texto con el contexto.",
            )
            return "image_without_context"

        # If image with text, upload to Drive
        photo_url = None
        if payload.tipo == "image" and payload.media_url:
            try:
                import uuid
                filename = f"audit_{uuid.uuid4().hex[:8]}.jpg"
                photo_url = await self.drive.upload_photo_from_url(
                    payload.media_url,
                    filename,
                )
            except Exception as e:
                logger.warning(f"Failed to upload photo: {e}")
                # Continue without photo

        # Parse message
        parse_result = await self.parser.parse_message(message_to_parse)
        if not parse_result or not parse_result.hallazgos:
            await waha_client.send_text(
                payload.telefono,
                "⚠️ No entendí el hallazgo. Por favor, sé más específico:\n"
                "• Sucursal\n• Área (Perfumería, Farmacia, etc)\n• Sub-item\n• Descripción",
            )
            return "parse_error"

        # Store pending confirmation
        pending_data = {
            "auditor": auditor.nombre,
            "cuadrilla": auditor.cuadrilla,
            "parse": json.loads(json.dumps(
                {
                    "hallazgos": [
                        {
                            "sucursal_id": h.sucursal_id,
                            "sucursal_nombre": h.sucursal_nombre,
                            "area": h.area,
                            "subitem": h.subitem,
                            "descripcion": h.descripcion,
                            "severidad": h.severidad.value,
                            "confianza": h.confianza,
                        }
                        for h in parse_result.hallazgos
                    ],
                    "photo_url": photo_url,
                    "original_message": parse_result.mensaje_original_limpio,
                },
                ensure_ascii=False,
            ))
        }

        id_pendiente = self.sheets.create_pendiente(
            telefono_auditor=payload.telefono,
            estado="esperando_confirmacion",
            datos_json=json.dumps(pending_data, ensure_ascii=False),
        )

        # Update conversation state
        self.sheets.update_conversacion(
            telefono=payload.telefono,
            estado=ConversationState.ESPERANDO_CONFIRMACION,
            id_pendiente=id_pendiente,
        )

        # Show draft for confirmation
        await self._show_draft(parse_result, photo_url, payload.telefono, waha_client)
        return "parse_success"

    async def _handle_confirmation_state(
        self,
        payload: WAHAPayload,
        conv: Conversacion,
        waha_client: WAHAClient,
    ) -> str:
        """Handle response in confirmation state."""
        if not payload.contenido:
            return "invalid_input"

        answer = payload.contenido.upper().strip()

        if answer == "SI":
            # Confirm and create reports/gestiones
            return await self._confirm_and_create(conv, waha_client)
        elif answer == "NO":
            # Discard
            await waha_client.send_text(
                payload.telefono,
                "❌ Descartado. Envíame otro hallazgo cuando estés listo.",
            )
            self.sheets.delete_pendiente(conv.id_pendiente)
            self.sheets.update_conversacion(
                telefono=payload.telefono,
                estado=ConversationState.IDLE,
            )
            return "discarded"
        elif answer == "EDITAR":
            # Move to edition state
            self.sheets.update_conversacion(
                telefono=payload.telefono,
                estado=ConversationState.ESPERANDO_EDICION,
                id_pendiente=conv.id_pendiente,
            )
            await waha_client.send_text(
                payload.telefono,
                "✏️ ¿Qué necesitas editar? Enviame la corrección.",
            )
            return "edit_requested"
        else:
            await waha_client.send_text(
                payload.telefono,
                "⚠️ Responde con SI, NO o EDITAR.",
            )
            return "invalid_response"

    async def _handle_edition_state(
        self,
        payload: WAHAPayload,
        conv: Conversacion,
        waha_client: WAHAClient,
    ) -> str:
        """Handle correction in edition state."""
        if not payload.contenido:
            return "invalid_input"

        # Get pending data
        pendiente = self.sheets.get_pendiente(conv.id_pendiente)
        if not pendiente:
            await waha_client.send_text(
                payload.telefono,
                "❌ Error: No encontré el pendiente. Intenta de nuevo.",
            )
            return "pendiente_not_found"

        try:
            pending_data = json.loads(pendiente.datos_json)
            original_message = pending_data["parse"]["original_message"]
            previous_response = pending_data["parse"]

            # Build previous response
            prev_response = ParserResponse(
                hallazgos=[],  # Will be reparsed
                datos_faltantes=previous_response.get("datos_faltantes", []),
                mensaje_original_limpio=original_message,
            )

            # Apply correction
            corrected = await self.parser.apply_correction(
                original_message=original_message,
                correction=payload.contenido,
                previous_response=prev_response,
            )

            if not corrected or not corrected.hallazgos:
                await waha_client.send_text(
                    payload.telefono,
                    "⚠️ No pude aplicar la corrección. Intenta de nuevo.",
                )
                return "correction_error"

            # Update pending data
            photo_url = pending_data["parse"].get("photo_url")
            new_pending_data = {
                "auditor": pending_data["auditor"],
                "cuadrilla": pending_data["cuadrilla"],
                "parse": json.loads(json.dumps(
                    {
                        "hallazgos": [
                            {
                                "sucursal_id": h.sucursal_id,
                                "sucursal_nombre": h.sucursal_nombre,
                                "area": h.area,
                                "subitem": h.subitem,
                                "descripcion": h.descripcion,
                                "severidad": h.severidad.value,
                                "confianza": h.confianza,
                            }
                            for h in corrected.hallazgos
                        ],
                        "photo_url": photo_url,
                        "original_message": corrected.mensaje_original_limpio,
                    },
                    ensure_ascii=False,
                ))
            }

            # Store corrected pending
            self.sheets.delete_pendiente(conv.id_pendiente)
            new_id = self.sheets.create_pendiente(
                telefono_auditor=payload.telefono,
                estado="esperando_confirmacion",
                datos_json=json.dumps(new_pending_data, ensure_ascii=False),
            )

            # Update conversation
            self.sheets.update_conversacion(
                telefono=payload.telefono,
                estado=ConversationState.ESPERANDO_CONFIRMACION,
                id_pendiente=new_id,
            )

            # Show corrected draft
            await self._show_draft(corrected, photo_url, payload.telefono, waha_client)
            return "correction_applied"
        except Exception as e:
            logger.error(f"Error applying correction: {e}")
            await waha_client.send_text(
                payload.telefono,
                "❌ Error procesando la corrección.",
            )
            return "error"

    async def _handle_command(
        self,
        payload: WAHAPayload,
        auditor: Auditor,
        waha_client: WAHAClient,
    ) -> str:
        """Handle special commands."""
        cmd = payload.contenido.lower().strip()

        if cmd == "/ayuda":
            await waha_client.send_text(
                payload.telefono,
                """📋 **AYUDA AuditBot**

Envíame hallazgos de auditoría:
📝 **Texto**: Descripción del hallazgo
🎤 **Audio**: Grabación con el hallazgo
📸 **Foto**: Imagen + descripción

Comandos:
/ayuda → Esta ayuda
/resumen → Resumen del día
/mis → Mis reportes hoy

Responde a la confirmación con:
SI → Confirmar hallazgo
NO → Descartar
EDITAR → Hacer cambios""",
            )
            return "help_sent"
        elif cmd == "/resumen":
            # TODO: Implement daily summary
            await waha_client.send_text(
                payload.telefono,
                "📊 Resumen del día:\n(Pronto disponible)",
            )
            return "summary_requested"
        elif cmd == "/mis":
            # TODO: Implement user's reports today
            await waha_client.send_text(
                payload.telefono,
                "📄 Tus reportes de hoy:\n(Pronto disponible)",
            )
            return "my_reports_requested"
        else:
            return "unknown_command"

    async def _show_draft(
        self,
        parse_result: ParserResponse,
        photo_url: Optional[str],
        phone: str,
        waha_client: WAHAClient,
    ) -> None:
        """Show draft for confirmation."""
        draft = "📋 **Borrador de Hallazgos**:\n\n"
        for i, h in enumerate(parse_result.hallazgos, 1):
            draft += f"{i}. **{h.sucursal_nombre}** - {h.area}\n"
            draft += f"   Sub-item: {h.subitem}\n"
            draft += f"   Descripción: {h.descripcion}\n"
            draft += f"   Severidad: {h.severidad.value}\n"
            draft += f"   Confianza: {int(h.confianza*100)}%\n\n"

        draft += "¿Confirmo? (SI/NO/EDITAR)"

        if photo_url:
            await waha_client.send_file(phone, photo_url, draft)
        else:
            await waha_client.send_text(phone, draft)

    async def _confirm_and_create(
        self,
        conv: Conversacion,
        waha_client: WAHAClient,
    ) -> str:
        """Create reports and gestiones after confirmation."""
        try:
            pendiente = self.sheets.get_pendiente(conv.id_pendiente)
            if not pendiente:
                return "pendiente_not_found"

            pending_data = json.loads(pendiente.datos_json)
            parse_data = pending_data["parse"]
            auditor_name = pending_data["auditor"]
            cuadrilla = pending_data["cuadrilla"]

            # Create reports and gestiones
            for hallazgo_data in parse_data["hallazgos"]:
                # Create report
                reporte = Reporte(
                    id="",  # Will be generated
                    fecha=datetime.now().strftime("%Y-%m-%d"),
                    hora=datetime.now().strftime("%H:%M:%S"),
                    cuadrilla=cuadrilla,
                    auditor=auditor_name,
                    id_sucursal=hallazgo_data["sucursal_id"],
                    sucursal=hallazgo_data["sucursal_nombre"],
                    area=hallazgo_data["area"],
                    subitem=hallazgo_data["subitem"],
                    descripcion=hallazgo_data["descripcion"],
                    severidad=Severidad(hallazgo_data["severidad"]),
                    foto_url=parse_data.get("photo_url"),
                    creado_por_audio=False,
                )

                reporte_id = self.sheets.create_reporte(reporte)

                # Get facility for responsable
                sucursal = self.sheets.get_sucursal(hallazgo_data["sucursal_id"])
                if not sucursal:
                    logger.warning(f"Sucursal {hallazgo_data['sucursal_id']} not found")
                    continue

                # Calculate deadline
                from config import get_settings
                settings = get_settings()
                hours = settings.severity_deadlines.get(
                    hallazgo_data["severidad"], 168
                )
                plazo_fecha = datetime.now() + timedelta(hours=hours)

                # Create gestión
                gestion = Gestion(
                    id_gestion="",  # Will be generated
                    id_reporte=reporte_id,
                    id_sucursal=sucursal.id,
                    sucursal=sucursal.nombre,
                    desvio=hallazgo_data["descripcion"],
                    severidad=Severidad(hallazgo_data["severidad"]),
                    responsable=sucursal.responsable,
                    tel_responsable=sucursal.tel_responsable,
                    plazo_fecha=plazo_fecha,
                    plan_accion="[Por definir por el responsable]",
                )

                gestion_id = self.sheets.create_gestion(gestion)

                # Notify responsible
                msg = (
                    f"🚨 **Nuevo Hallazgo de Auditoría**\n\n"
                    f"Sucursal: {sucursal.nombre}\n"
                    f"Área: {hallazgo_data['area']}\n"
                    f"Desvío: {hallazgo_data['descripcion']}\n"
                    f"Severidad: {hallazgo_data['severidad']}\n"
                    f"Plazo: {plazo_fecha.strftime('%Y-%m-%d %H:%M')}\n\n"
                    f"ID Gestión: {gestion_id}"
                )
                await waha_client.send_text(sucursal.tel_responsable, msg)

            # Clean up
            self.sheets.delete_pendiente(conv.id_pendiente)
            self.sheets.update_conversacion(
                telefono=conv.telefono,
                estado=ConversationState.IDLE,
            )

            await waha_client.send_text(
                conv.telefono,
                "✅ Hallazgos guardados. Notificaciones enviadas a responsables.",
            )
            return "confirmed"
        except Exception as e:
            logger.error(f"Error confirming and creating: {e}")
            await waha_client.send_text(
                conv.telefono,
                "❌ Error guardando hallazgos.",
            )
            return "error"

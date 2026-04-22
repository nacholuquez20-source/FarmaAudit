"""Conversation router - state machine logic for audit interactions."""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple

from models import (
    ConversationState, WAHAPayload, Auditor, Conversacion,
    ParserResponse, Reporte, Gestion, Severidad, ChecklistPunto, SesionAuditoria, PuntoEvalResult
)
from sheets import SheetsManager
from parser import AuditParser
from audio import AudioTranscriber
from drive import DriveManager
from waha import TwilioClient

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
        twilio_client: TwilioClient,
    ) -> str:
        """Route message based on conversation state."""
        try:
            # Validate auditor
            auditor = self.sheets.get_auditor(payload.telefono)
            if not auditor or not auditor.activo:
                await twilio_client.send_text(
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

            logger.debug(f"Message from {payload.telefono}: state={conv.estado_actual.value}, content={payload.contenido[:50] if payload.contenido else 'N/A'}")

            # Route based on state
            if conv.estado_actual == ConversationState.IDLE:
                return await self._handle_idle_state(payload, auditor, conv, twilio_client)
            elif conv.estado_actual == ConversationState.SELECCIONANDO_SUCURSAL:
                return await self._handle_seleccionando_sucursal(payload, conv, twilio_client)
            elif conv.estado_actual == ConversationState.EN_AUDITORIA:
                return await self._handle_en_auditoria(payload, conv, twilio_client)
            elif conv.estado_actual == ConversationState.AUDITORIA_PAUSADA:
                return await self._handle_auditoria_pausada(payload, conv, twilio_client)
            elif conv.estado_actual == ConversationState.ESPERANDO_CONFIRMACION:
                return await self._handle_confirmation_state(payload, conv, twilio_client)
            elif conv.estado_actual == ConversationState.ESPERANDO_EDICION:
                return await self._handle_edition_state(payload, conv, twilio_client)
            else:
                await twilio_client.send_text(payload.telefono, "⚠️ Estado desconocido")
                return "unknown_state"
        except Exception as e:
            logger.error(f"Error handling message from {payload.telefono}: {e}", exc_info=True)
            await twilio_client.send_text(
                payload.telefono,
                "❌ Error procesando tu mensaje. Intenta de nuevo.",
            )
            return "error"

    async def _handle_idle_state(
        self,
        payload: WAHAPayload,
        auditor: Auditor,
        conv: Conversacion,
        twilio_client: TwilioClient,
    ) -> str:
        """Handle message in idle state."""
        # Check for special commands
        if payload.contenido and payload.contenido.startswith("/"):
            return await self._handle_command(payload, auditor, twilio_client)

        # Check for guided audit trigger ("inicio", "empezar", "comenzar", "start")
        if payload.tipo == "text" and payload.contenido:
            trigger = payload.contenido.lower().strip()
            if trigger in {"inicio", "empezar", "comenzar", "start"}:
                return await self._iniciar_seleccion_sucursal(payload, twilio_client)

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
                await twilio_client.send_text(
                    payload.telefono,
                    "❌ Error transcribiendo audio. Intenta de nuevo.",
                )
                return "transcription_error"

        # If image without text, ask for context
        if payload.tipo == "image" and not payload.contenido:
            await twilio_client.send_text(
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
            await twilio_client.send_text(
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

        logger.info(f"Created pendiente {id_pendiente} for {payload.telefono}")

        # Update conversation state
        self.sheets.update_conversacion(
            telefono=payload.telefono,
            estado=ConversationState.ESPERANDO_CONFIRMACION,
            id_pendiente=id_pendiente,
        )

        logger.info(f"Updated state to ESPERANDO_CONFIRMACION for {payload.telefono}, pendiente={id_pendiente}")

        # Show draft for confirmation
        await self._show_draft(parse_result, photo_url, payload.telefono, twilio_client)
        return "parse_success"

    async def _handle_confirmation_state(
        self,
        payload: WAHAPayload,
        conv: Conversacion,
        twilio_client: TwilioClient,
    ) -> str:
        """Handle response in confirmation state."""
        if not payload.contenido:
            return "invalid_input"

        answer = payload.contenido.strip().upper()
        logger.info(f"Confirmation response from {payload.telefono}: '{answer}'")

        # Check for yes responses (with or without accent)
        if answer in {"SI", "SÍ", "YES", "Y"}:
            logger.info(f"Confirmed finding for {payload.telefono}")
            return await self._confirm_and_create(conv, twilio_client)
        elif answer in {"NO", "N"}:
            # Discard
            logger.info(f"Discarded finding for {payload.telefono}")
            await twilio_client.send_text(
                payload.telefono,
                "❌ Descartado. Envíame otro hallazgo cuando estés listo.",
            )
            self.sheets.delete_pendiente(conv.id_pendiente)
            self.sheets.update_conversacion(
                telefono=payload.telefono,
                estado=ConversationState.IDLE,
            )
            return "discarded"
        elif answer in {"EDITAR", "EDIT", "CORREGIR"}:
            # Move to edition state
            logger.info(f"Edit requested for {payload.telefono}")
            self.sheets.update_conversacion(
                telefono=payload.telefono,
                estado=ConversationState.ESPERANDO_EDICION,
                id_pendiente=conv.id_pendiente,
            )
            await twilio_client.send_text(
                payload.telefono,
                "✏️ ¿Qué necesitas editar? Enviame la corrección.",
            )
            return "edit_requested"
        else:
            logger.warning(f"Invalid confirmation response from {payload.telefono}: '{answer}'")
            await twilio_client.send_text(
                payload.telefono,
                "⚠️ Por favor responde con:\nSI - para confirmar\nNO - para descartar\nEDITAR - para hacer cambios",
            )
            return "invalid_response"

    async def _handle_edition_state(
        self,
        payload: WAHAPayload,
        conv: Conversacion,
        twilio_client: TwilioClient,
    ) -> str:
        """Handle correction in edition state."""
        if not payload.contenido:
            return "invalid_input"

        # Get pending data
        pendiente = self.sheets.get_pendiente(conv.id_pendiente)
        if not pendiente:
            await twilio_client.send_text(
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
                await twilio_client.send_text(
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
            await self._show_draft(corrected, photo_url, payload.telefono, twilio_client)
            return "correction_applied"
        except Exception as e:
            logger.error(f"Error applying correction: {e}")
            await twilio_client.send_text(
                payload.telefono,
                "❌ Error procesando la corrección.",
            )
            return "error"

    async def _handle_command(
        self,
        payload: WAHAPayload,
        auditor: Auditor,
        twilio_client: TwilioClient,
    ) -> str:
        """Handle special commands."""
        cmd = payload.contenido.lower().strip()

        if cmd == "/ayuda":
            await twilio_client.send_text(
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
            await twilio_client.send_text(
                payload.telefono,
                "📊 Resumen del día:\n(Pronto disponible)",
            )
            return "summary_requested"
        elif cmd == "/mis":
            # TODO: Implement user's reports today
            await twilio_client.send_text(
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
        twilio_client: TwilioClient,
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
            await twilio_client.send_file(phone, photo_url, draft)
        else:
            await twilio_client.send_text(phone, draft)

    async def _confirm_and_create(
        self,
        conv: Conversacion,
        twilio_client: TwilioClient,
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
                await twilio_client.send_text(sucursal.tel_responsable, msg)

            # Clean up
            self.sheets.delete_pendiente(conv.id_pendiente)
            self.sheets.update_conversacion(
                telefono=conv.telefono,
                estado=ConversationState.IDLE,
            )

            await twilio_client.send_text(
                conv.telefono,
                "✅ Hallazgos guardados. Notificaciones enviadas a responsables.",
            )
            return "confirmed"
        except Exception as e:
            logger.error(f"Error confirming and creating: {e}")
            await twilio_client.send_text(
                conv.telefono,
                "❌ Error guardando hallazgos.",
            )
            return "error"

    async def _iniciar_seleccion_sucursal(
        self,
        payload: WAHAPayload,
        twilio_client: TwilioClient,
    ) -> str:
        """Start guided audit flow: send sucursal list."""
        try:
            sucursales = self.sheets.get_all_sucursales()
            if not sucursales:
                await twilio_client.send_text(
                    payload.telefono,
                    "❌ No hay sucursales disponibles.",
                )
                return "no_sucursales"

            # Build menu
            menu = "🏪 Selecciona tu sucursal:\n\n"
            for i, s in enumerate(sucursales, 1):
                menu += f"{i}. {s.nombre} ({s.zona})\n"

            menu += "\nResponde con el número de la sucursal."

            await twilio_client.send_text(payload.telefono, menu)

            # Update conversation state
            self.sheets.update_conversacion(
                telefono=payload.telefono,
                estado=ConversationState.SELECCIONANDO_SUCURSAL,
            )

            return "sucursal_menu_sent"
        except Exception as e:
            logger.error(f"Error initiating sucursal selection: {e}")
            await twilio_client.send_text(
                payload.telefono,
                "❌ Error iniciando auditoría.",
            )
            return "error"

    async def _handle_seleccionando_sucursal(
        self,
        payload: WAHAPayload,
        conv: Conversacion,
        twilio_client: TwilioClient,
    ) -> str:
        """Handle sucursal selection."""
        try:
            if not payload.contenido:
                await twilio_client.send_text(
                    payload.telefono,
                    "⚠️ Por favor responde con un número.",
                )
                return "invalid_input"

            # Parse selection
            try:
                choice = int(payload.contenido.strip())
            except ValueError:
                await twilio_client.send_text(
                    payload.telefono,
                    "⚠️ Responde con un número válido.",
                )
                return "invalid_number"

            sucursales = self.sheets.get_all_sucursales()
            if choice < 1 or choice > len(sucursales):
                await twilio_client.send_text(
                    payload.telefono,
                    f"⚠️ Número fuera de rango. Elige entre 1 y {len(sucursales)}.",
                )
                return "out_of_range"

            sucursal = sucursales[choice - 1]

            # Get checklist
            checklist = self.sheets.get_checklist()
            if not checklist:
                await twilio_client.send_text(
                    payload.telefono,
                    "❌ No hay checklist disponible.",
                )
                return "no_checklist"

            # Create session
            id_sesion = f"ses_{uuid.uuid4().hex[:8]}"
            sesion = SesionAuditoria(
                id_sesion=id_sesion,
                telefono_auditor=payload.telefono,
                sucursal_id=sucursal.id,
                punto_actual=0,
                total_puntos=len(checklist),
                hallazgos_json="[]",
                omitidos_json="[]",
                estado="en_curso",
                timestamp_inicio=datetime.now().isoformat(),
                timestamp_ultimo_punto=datetime.now().isoformat(),
            )

            self.sheets.create_sesion(sesion)

            # Update conversation
            self.sheets.update_conversacion(
                telefono=payload.telefono,
                estado=ConversationState.EN_AUDITORIA,
                id_pendiente=id_sesion,
            )

            # Send first point
            await twilio_client.send_text(
                payload.telefono,
                f"✅ Iniciando auditoría en {sucursal.nombre}",
            )
            await self._enviar_siguiente_punto(sesion, checklist, twilio_client, payload.telefono)

            return "auditoria_started"
        except Exception as e:
            logger.error(f"Error handling sucursal selection: {e}")
            await twilio_client.send_text(
                payload.telefono,
                "❌ Error seleccionando sucursal.",
            )
            return "error"

    async def _handle_en_auditoria(
        self,
        payload: WAHAPayload,
        conv: Conversacion,
        twilio_client: TwilioClient,
    ) -> str:
        """Handle response during audit."""
        try:
            # Get active session
            sesion = self.sheets.get_sesion(conv.id_pendiente)
            if not sesion:
                await twilio_client.send_text(
                    payload.telefono,
                    "❌ Sesión no encontrada.",
                )
                return "sesion_not_found"

            # Check for special commands
            if payload.contenido:
                cmd = payload.contenido.lower().strip()
                if cmd in {"saltar", "skip"}:
                    # Mark as omitted
                    omitidos = json.loads(sesion.omitidos_json)
                    omitidos.append(sesion.punto_actual)
                    sesion.omitidos_json = json.dumps(omitidos)
                    sesion.punto_actual += 1
                    sesion.timestamp_ultimo_punto = datetime.now().isoformat()
                    self.sheets.update_sesion(
                        sesion.id_sesion,
                        sesion.punto_actual,
                        sesion.hallazgos_json,
                        sesion.omitidos_json,
                        sesion.estado,
                        sesion.timestamp_ultimo_punto,
                    )

                    # Check if finished
                    if sesion.punto_actual >= sesion.total_puntos:
                        return await self._cerrar_auditoria(sesion, twilio_client, payload.telefono)

                    # Send next point
                    checklist = await self.sheets.get_checklist()
                    await self._enviar_siguiente_punto(sesion, checklist, twilio_client, payload.telefono)
                    return "punto_omitido"

                if cmd == "pausar":
                    sesion.estado = "pausada"
                    self.sheets.update_sesion(
                        sesion.id_sesion,
                        sesion.punto_actual,
                        sesion.hallazgos_json,
                        sesion.omitidos_json,
                        sesion.estado,
                        sesion.timestamp_ultimo_punto,
                    )
                    self.sheets.update_conversacion(
                        telefono=payload.telefono,
                        estado=ConversationState.AUDITORIA_PAUSADA,
                        id_pendiente=conv.id_pendiente,
                    )
                    await twilio_client.send_text(
                        payload.telefono,
                        "⏸️ Auditoría pausada. Escribe 'continuar' cuando quieras retomar.",
                    )
                    return "auditoria_pausada"

            # Get respuesta (transcribe audio if needed)
            respuesta = payload.contenido or ""
            if payload.tipo == "audio" and payload.media_url:
                try:
                    respuesta = await self.transcriber.transcribe_from_url(payload.media_url)
                except Exception as e:
                    logger.error(f"Failed to transcribe audio: {e}")
                    await twilio_client.send_text(
                        payload.telefono,
                        "❌ Error transcribiendo audio. Intenta de nuevo.",
                    )
                    return "transcription_error"

            if not respuesta:
                await twilio_client.send_text(
                    payload.telefono,
                    "⚠️ Por favor envía audio, foto o texto con tu observación.",
                )
                return "empty_response"

            # Upload photo if present
            photo_url = None
            if payload.tipo == "image" and payload.media_url:
                try:
                    fecha = datetime.now().strftime("%Y%m%d")
                    checklist = await self.sheets.get_checklist()
                    punto = checklist[sesion.punto_actual]
                    filename = f"{fecha}_{sesion.sucursal_id}_{punto.area.replace(' ','_')}_{punto.punto_orden}.jpg"
                    photo_url = await self.drive.upload_photo_from_url(
                        payload.media_url,
                        filename,
                    )
                except Exception as e:
                    logger.warning(f"Failed to upload photo: {e}")

            # Evaluate response
            checklist = await self.sheets.get_checklist()
            punto = checklist[sesion.punto_actual]
            eval_result = await self.parser.evaluate_punto_respuesta(punto, respuesta)

            if not eval_result:
                await twilio_client.send_text(
                    payload.telefono,
                    "❌ Error evaluando respuesta. Intenta de nuevo.",
                )
                return "eval_error"

            # If desvío, create reporte and gestión automatically
            if eval_result.tiene_desvio:
                # Create reporte
                reporte = Reporte(
                    id="",
                    fecha=datetime.now().strftime("%Y-%m-%d"),
                    hora=datetime.now().strftime("%H:%M:%S"),
                    cuadrilla="",  # Will be filled from auditor
                    auditor="",  # Will be filled from auditor
                    id_sucursal=sesion.sucursal_id,
                    sucursal="",  # Will be filled below
                    area=punto.area,
                    subitem=punto.descripcion,
                    descripcion=eval_result.descripcion_desvio,
                    severidad=Severidad(eval_result.severidad),
                    foto_url=photo_url,
                    creado_por_audio=(payload.tipo == "audio"),
                )

                auditor = self.sheets.get_auditor(payload.telefono)
                if auditor:
                    reporte.cuadrilla = auditor.cuadrilla
                    reporte.auditor = auditor.nombre

                sucursal = self.sheets.get_sucursal(sesion.sucursal_id)
                if sucursal:
                    reporte.sucursal = sucursal.nombre

                reporte_id = self.sheets.create_reporte(reporte)

                # Create gestión
                if sucursal:
                    from config import get_settings
                    settings = get_settings()
                    hours = settings.severity_deadlines.get(eval_result.severidad, 168)
                    plazo_fecha = datetime.now() + timedelta(hours=hours)

                    gestion = Gestion(
                        id_gestion="",
                        id_reporte=reporte_id,
                        id_sucursal=sucursal.id,
                        sucursal=sucursal.nombre,
                        desvio=eval_result.descripcion_desvio,
                        severidad=Severidad(eval_result.severidad),
                        responsable=sucursal.responsable,
                        tel_responsable=sucursal.tel_responsable,
                        plazo_fecha=plazo_fecha,
                        plan_accion="[Por definir por el responsable]",
                    )

                    gestion_id = self.sheets.create_gestion(gestion)

                    # Notify responsible
                    msg = (
                        f"🚨 **Hallazgo de Auditoría Guiada**\n\n"
                        f"Sucursal: {sucursal.nombre}\n"
                        f"Área: {punto.area}\n"
                        f"Desvío: {eval_result.descripcion_desvio}\n"
                        f"Severidad: {eval_result.severidad}\n"
                        f"Plazo: {plazo_fecha.strftime('%Y-%m-%d %H:%M')}\n\n"
                        f"ID Gestión: {gestion_id}"
                    )
                    await twilio_client.send_text(sucursal.tel_responsable, msg)

                # Store in session
                hallazgos = json.loads(sesion.hallazgos_json)
                hallazgos.append({
                    "punto": punto.punto_orden,
                    "area": punto.area,
                    "descripcion": eval_result.descripcion_desvio,
                    "severidad": eval_result.severidad,
                })
                sesion.hallazgos_json = json.dumps(hallazgos)

            # Confirm to auditor
            await twilio_client.send_text(payload.telefono, eval_result.ok_message)

            # Advance to next point
            sesion.punto_actual += 1
            sesion.timestamp_ultimo_punto = datetime.now().isoformat()
            self.sheets.update_sesion(
                sesion.id_sesion,
                sesion.punto_actual,
                sesion.hallazgos_json,
                sesion.omitidos_json,
                sesion.estado,
                sesion.timestamp_ultimo_punto,
            )

            # Check if finished
            if sesion.punto_actual >= sesion.total_puntos:
                return await self._cerrar_auditoria(sesion, twilio_client, payload.telefono)

            # Send next point
            checklist = await self.sheets.get_checklist()
            await self._enviar_siguiente_punto(sesion, checklist, twilio_client, payload.telefono)
            return "punto_evaluado"
        except Exception as e:
            logger.error(f"Error handling en_auditoria: {e}")
            await twilio_client.send_text(
                payload.telefono,
                "❌ Error procesando respuesta.",
            )
            return "error"

    async def _handle_auditoria_pausada(
        self,
        payload: WAHAPayload,
        conv: Conversacion,
        twilio_client: TwilioClient,
    ) -> str:
        """Handle response in paused audit state."""
        try:
            if not payload.contenido:
                return "invalid_input"

            cmd = payload.contenido.lower().strip()
            if cmd == "continuar":
                # Resume audit
                sesion = self.sheets.get_sesion(conv.id_pendiente)
                if not sesion:
                    await twilio_client.send_text(
                        payload.telefono,
                        "❌ Sesión no encontrada.",
                    )
                    return "sesion_not_found"

                sesion.estado = "en_curso"
                sesion.timestamp_ultimo_punto = datetime.now().isoformat()
                self.sheets.update_sesion(
                    sesion.id_sesion,
                    sesion.punto_actual,
                    sesion.hallazgos_json,
                    sesion.omitidos_json,
                    sesion.estado,
                    sesion.timestamp_ultimo_punto,
                )

                self.sheets.update_conversacion(
                    telefono=payload.telefono,
                    estado=ConversationState.EN_AUDITORIA,
                    id_pendiente=conv.id_pendiente,
                )

                checklist = await self.sheets.get_checklist()
                await self._enviar_siguiente_punto(sesion, checklist, twilio_client, payload.telefono)
                return "auditoria_resumed"
            else:
                await twilio_client.send_text(
                    payload.telefono,
                    "⚠️ Escribe 'continuar' para retomar la auditoría.",
                )
                return "invalid_command"
        except Exception as e:
            logger.error(f"Error handling auditoria_pausada: {e}")
            return "error"

    async def _enviar_siguiente_punto(
        self,
        sesion: SesionAuditoria,
        checklist: list,
        twilio_client: TwilioClient,
        phone: str,
    ) -> None:
        """Send next checklist point."""
        if sesion.punto_actual < len(checklist):
            punto = checklist[sesion.punto_actual]
            await twilio_client.send_punto(
                phone,
                punto.punto_orden,
                sesion.total_puntos,
                punto.area,
                punto.descripcion,
            )

    async def _cerrar_auditoria(
        self,
        sesion: SesionAuditoria,
        twilio_client: TwilioClient,
        phone: str,
    ) -> str:
        """Close audit session and send summary."""
        try:
            sesion.estado = "completa"
            self.sheets.update_sesion(
                sesion.id_sesion,
                sesion.punto_actual,
                sesion.hallazgos_json,
                sesion.omitidos_json,
                sesion.estado,
                sesion.timestamp_ultimo_punto,
            )

            # Parse results
            hallazgos = json.loads(sesion.hallazgos_json)
            omitidos = json.loads(sesion.omitidos_json)
            desvios = len(hallazgos)
            omitidos_count = len(omitidos)

            # Build detail
            detalle = "Desvíos encontrados:\n"
            for h in hallazgos:
                detalle += f"• {h['area']}: {h['descripcion']} ({h['severidad']})\n"

            if not hallazgos:
                detalle = "No se encontraron desvíos. ¡Excelente auditoría!"

            # Send summary to auditor
            sucursal = self.sheets.get_sucursal(sesion.sucursal_id)
            sucursal_nombre = sucursal.nombre if sucursal else "Sucursal"
            await twilio_client.send_resumen_auditoria(
                phone,
                sucursal_nombre,
                sesion.total_puntos,
                desvios,
                omitidos_count,
                detalle,
            )

            # Send summary to coordinator
            from config import get_settings
            settings = get_settings()
            if settings.coordinador_tel:
                auditor = self.sheets.get_auditor(phone)
                auditor_nombre = auditor.nombre if auditor else "Auditor"
                coord_msg = (
                    f"📊 **Auditoría Completada**\n\n"
                    f"Auditor: {auditor_nombre}\n"
                    f"Sucursal: {sucursal_nombre}\n"
                    f"Total de puntos: {sesion.total_puntos}\n"
                    f"Desvíos: {desvios}\n"
                    f"Omitidos: {omitidos_count}\n"
                    f"ID Sesión: {sesion.id_sesion}"
                )
                await twilio_client.send_text(settings.coordinador_tel, coord_msg)

            # Reset conversation
            self.sheets.update_conversacion(
                telefono=phone,
                estado=ConversationState.IDLE,
            )

            return "auditoria_cerrada"
        except Exception as e:
            logger.error(f"Error closing audit: {e}")
            return "error"

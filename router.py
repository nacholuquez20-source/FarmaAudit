"""Conversation router - state machine logic for audit interactions."""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple

from models import (
    ConversationState, WAHAPayload, Auditor, Conversacion,
    ParserResponse, Reporte, Gestion, Severidad, ChecklistPunto, SesionAuditoria, PuntoEvalResult,
    ItemBloque, ResultadoItem, StockItem, DesvioLibre
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
            elif conv.estado_actual == ConversationState.EN_BLOQUE:
                return await self._handle_en_bloque(payload, conv, twilio_client)
            elif conv.estado_actual == ConversationState.CONFIRMANDO_BLOQUE:
                return await self._handle_confirmando_bloque(payload, conv, twilio_client)
            elif conv.estado_actual == ConversationState.STOCK_LOOP:
                return await self._handle_stock_loop(payload, conv, twilio_client)
            elif conv.estado_actual == ConversationState.EN_STOCK_ITEM:
                return await self._handle_en_stock_item(payload, conv, twilio_client)
            elif conv.estado_actual == ConversationState.DESVIO_LIBRE:
                return await self._handle_desvio_libre(payload, conv, twilio_client)
            elif conv.estado_actual == ConversationState.COMPROMISOS:
                return await self._handle_compromisos(payload, conv, twilio_client)
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

        # Check for guided audit trigger ("hola", "inicio", "empezar", "comenzar", "start")
        if payload.tipo == "text" and payload.contenido:
            trigger = payload.contenido.lower().strip()
            if trigger in {"hola", "inicio", "empezar", "comenzar", "start"}:
                return await self._iniciar_seleccion_sucursal(payload, twilio_client)

            await twilio_client.send_text(
                payload.telefono,
                "Escribí INICIO para comenzar la auditoría guiada.\n"
                "Usá /ayuda para ver comandos.",
            )
            return "idle_waiting_start"

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

    # ========== Block-Based Audit Handlers ==========

    async def _handle_en_bloque(
        self,
        payload: WAHAPayload,
        conv: Conversacion,
        twilio_client: TwilioClient,
    ) -> str:
        """Handle auditor response in block evaluation state."""
        try:
            # Check for pause/continue commands
            if payload.tipo == "text" and payload.contenido:
                cmd = payload.contenido.upper().strip()
                if cmd == "PAUSAR":
                    self.sheets.update_conversacion(
                        telefono=payload.telefono,
                        estado=ConversationState.AUDITORIA_PAUSADA,
                    )
                    await twilio_client.send_text(
                        payload.telefono,
                        "⏸️ Auditoría pausada. Mandá 'continuar' cuando estés listo.",
                    )
                    return "auditoria_pausada"

            # Get session
            sesion = self.sheets.get_sesion(conv.id_pendiente or "")
            if not sesion:
                await twilio_client.send_text(payload.telefono, "❌ Sesión no encontrada")
                return "error"

            # Get block items
            bloques = self.sheets.get_checklist_bloques()
            bloque_id = sesion.bloque_actual
            if bloque_id not in bloques:
                await twilio_client.send_text(payload.telefono, "❌ Bloque no encontrado")
                return "error"

            items = bloques[bloque_id]

            # Transcribe audio if present
            respuesta_auditor = payload.contenido or ""
            if payload.tipo == "audio" and payload.media_url:
                transcripcion = await self.transcriber.transcribe(payload.media_url)
                if transcripcion:
                    respuesta_auditor = transcripcion
            elif payload.tipo == "image" and payload.media_url:
                respuesta_auditor = payload.contenido or "(foto enviada)"

            # Parse bloque response
            resultados = await self.parser.parse_bloque(
                bloque_id, f"Bloque {bloque_id}", items, respuesta_auditor
            )
            if not resultados:
                await twilio_client.send_text(
                    payload.telefono,
                    "❌ No pude evaluar la respuesta. Intenta de nuevo.",
                )
                return "parse_error"

            # Store resultados in session temporarily
            sesion_data = json.loads(sesion.resultados_json) if sesion.resultados_json else {}
            sesion_data[bloque_id] = [vars(r) for r in resultados]

            self.sheets.update_sesion(
                sesion.id_sesion,
                estado=ConversationState.CONFIRMANDO_BLOQUE.value,
                timestamp_ultimo_punto=datetime.utcnow().isoformat(),
                bloque_actual=bloque_id,
                resultados_json=json.dumps(sesion_data, ensure_ascii=False),
            )

            # Send confirmation
            bloque_nombre = items[0].descripcion.split(":")[0] if items else bloque_id
            await twilio_client.send_bloque_confirmacion(
                payload.telefono, bloque_id, f"Bloque {bloque_id}", items, resultados
            )

            return "bloque_respondido"
        except Exception as e:
            logger.error(f"Error in _handle_en_bloque: {e}", exc_info=True)
            return "error"

    async def _handle_confirmando_bloque(
        self,
        payload: WAHAPayload,
        conv: Conversacion,
        twilio_client: TwilioClient,
    ) -> str:
        """Handle block confirmation (SI/EDITAR/SALTAR)."""
        try:
            if payload.tipo != "text" or not payload.contenido:
                await twilio_client.send_text(
                    payload.telefono,
                    "⚠️ Respondé SI, EDITAR o SALTAR BLOQUE",
                )
                return "invalid_response"

            respuesta = payload.contenido.upper().strip()

            # Get session
            sesion = self.sheets.get_sesion(conv.id_pendiente or "")
            if not sesion:
                return "error"

            if respuesta == "SI":
                # Save bloque results
                sesion_data = json.loads(sesion.resultados_json) if sesion.resultados_json else {}
                bloques = self.sheets.get_checklist_bloques()
                bloque_id = sesion.bloque_actual

                if bloque_id in bloques and bloque_id in sesion_data:
                    resultados = []
                    for item_data in sesion_data[bloque_id]:
                        resultados.append(ResultadoItem(**item_data))

                    auditor = self.sheets.get_auditor(payload.telefono)
                    auditor_nombre = auditor.nombre if auditor else "Auditor"

                    # Save results and create Reportes/Gestiones
                    self.sheets.save_bloque_resultado(
                        sesion.id_sesion,
                        bloque_id,
                        sesion.sucursal_id,
                        auditor_nombre,
                        resultados,
                    )

                    # Check for ALTA severity and send immediate alerts
                    for resultado in resultados:
                        if resultado.tiene_desvio and resultado.severidad == "Alta":
                            sucursal = self.sheets.get_sucursal(sesion.sucursal_id)
                            sucursal_nombre = sucursal.nombre if sucursal else sesion.sucursal_id
                            from config import get_settings
                            settings = get_settings()
                            if settings.coordinador_tel:
                                await twilio_client.send_alerta_coordinador(
                                    settings.coordinador_tel,
                                    sucursal_nombre,
                                    f"Bloque {bloque_id}",
                                    resultado.descripcion_desvio or "",
                                    "Alta",
                                )

                # Advance to next bloque
                next_bloques = {"A": "B", "B": "C", "C": "D", "D": "STOCK_LOOP"}
                next_state = next_bloques.get(bloque_id)

                if next_state == "STOCK_LOOP":
                    self.sheets.update_conversacion(
                        telefono=payload.telefono,
                        estado=ConversationState.STOCK_LOOP,
                        id_pendiente=sesion.id_sesion,
                    )
                    await twilio_client.send_text(
                        payload.telefono,
                        "🔍 Verificación de Stock\n\n¿Cuántos productos querés verificar? (0 para saltar)",
                    )
                else:
                    sesion.bloque_actual = next_state
                    self.sheets.update_sesion(
                        sesion.id_sesion,
                        estado=ConversationState.EN_BLOQUE.value,
                        timestamp_ultimo_punto=datetime.utcnow().isoformat(),
                        bloque_actual=next_state,
                        resultados_json=json.dumps(sesion_data, ensure_ascii=False),
                    )

                    # Send next bloque
                    bloques = self.sheets.get_checklist_bloques()
                    if next_state in bloques:
                        await twilio_client.send_bloque_prompt(
                            payload.telefono, next_state, f"Bloque {next_state}",
                            bloques[next_state]
                        )

                return "bloque_confirmado"

            elif respuesta == "EDITAR":
                # Re-send current bloque
                self.sheets.update_conversacion(
                    telefono=payload.telefono,
                    estado=ConversationState.EN_BLOQUE,
                    id_pendiente=sesion.id_sesion,
                )
                bloques = self.sheets.get_checklist_bloques()
                bloque_id = sesion.bloque_actual
                if bloque_id in bloques:
                    await twilio_client.send_bloque_prompt(
                        payload.telefono, bloque_id, f"Bloque {bloque_id}", bloques[bloque_id]
                    )
                return "bloque_reditado"

            elif respuesta == "SALTAR BLOQUE" or respuesta == "SALTAR":
                # Skip to next bloque without saving
                next_bloques = {"A": "B", "B": "C", "C": "D", "D": "STOCK_LOOP"}
                next_state = next_bloques.get(sesion.bloque_actual)

                if next_state == "STOCK_LOOP":
                    self.sheets.update_conversacion(
                        telefono=payload.telefono,
                        estado=ConversationState.STOCK_LOOP,
                        id_pendiente=sesion.id_sesion,
                    )
                    await twilio_client.send_text(
                        payload.telefono,
                        "🔍 Verificación de Stock\n\n¿Cuántos productos querés verificar? (0 para saltar)",
                    )
                else:
                    self.sheets.update_conversacion(
                        telefono=payload.telefono,
                        estado=ConversationState.EN_BLOQUE,
                        id_pendiente=sesion.id_sesion,
                    )
                    sesion.bloque_actual = next_state
                    self.sheets.update_sesion(
                        sesion.id_sesion,
                        estado=ConversationState.EN_BLOQUE.value,
                        timestamp_ultimo_punto=datetime.utcnow().isoformat(),
                        bloque_actual=next_state,
                    )

                    bloques = self.sheets.get_checklist_bloques()
                    if next_state in bloques:
                        await twilio_client.send_bloque_prompt(
                            payload.telefono, next_state, f"Bloque {next_state}",
                            bloques[next_state]
                        )

                return "bloque_saltado"

            else:
                await twilio_client.send_text(
                    payload.telefono,
                    "⚠️ Respondé SI, EDITAR o SALTAR BLOQUE",
                )
                return "invalid_response"

        except Exception as e:
            logger.error(f"Error in _handle_confirmando_bloque: {e}", exc_info=True)
            return "error"

    async def _handle_stock_loop(
        self,
        payload: WAHAPayload,
        conv: Conversacion,
        twilio_client: TwilioClient,
    ) -> str:
        """Handle stock verification count input."""
        try:
            if payload.tipo != "text" or not payload.contenido:
                await twilio_client.send_text(
                    payload.telefono,
                    "⚠️ Mandá un número o 0 para saltar",
                )
                return "invalid_response"

            try:
                cantidad = int(payload.contenido.strip())
            except ValueError:
                await twilio_client.send_text(
                    payload.telefono,
                    "⚠️ Mandá un número válido",
                )
                return "invalid_response"

            sesion = self.sheets.get_sesion(conv.id_pendiente or "")
            if not sesion:
                return "error"

            if cantidad == 0:
                # Skip stock verification
                self.sheets.update_conversacion(
                    telefono=payload.telefono,
                    estado=ConversationState.DESVIO_LIBRE,
                    id_pendiente=sesion.id_sesion,
                )
                await twilio_client.send_text(
                    payload.telefono,
                    "📋 Desvíos Libres\n\nTiene algún desvío o hallazgo libre para reportar?\n\nMandá 'NO' si no hay más desvíos, o describí el problema.",
                )
                return "stock_skipped"
            else:
                # Start stock loop
                sesion_aux = {
                    "stock_count": cantidad,
                    "stock_items": [],
                    "stock_current": 0,
                }
                self.sheets.update_conversacion(
                    telefono=payload.telefono,
                    estado=ConversationState.EN_STOCK_ITEM,
                    id_pendiente=sesion.id_sesion,
                )
                await twilio_client.send_text(
                    payload.telefono,
                    f"📦 Producto 1/{cantidad}\n\nMandá: Nombre / Stock Físico / Stock Sistema\n\nEj: Ibuprofeno 400 / 23 / 18",
                )
                return "stock_started"

        except Exception as e:
            logger.error(f"Error in _handle_stock_loop: {e}", exc_info=True)
            return "error"

    async def _handle_en_stock_item(
        self,
        payload: WAHAPayload,
        conv: Conversacion,
        twilio_client: TwilioClient,
    ) -> str:
        """Handle stock item entry."""
        try:
            if payload.tipo != "text" or not payload.contenido:
                await twilio_client.send_text(
                    payload.telefono,
                    "⚠️ Mandá el formato: Nombre / Stock Físico / Stock Sistema",
                )
                return "invalid_response"

            # Parse stock item
            stock_item = await self.parser.parse_stock_item(payload.contenido)
            if not stock_item:
                await twilio_client.send_text(
                    payload.telefono,
                    "❌ No pude entender el formato. Intenta: Nombre / Físico / Sistema",
                )
                return "parse_error"

            sesion = self.sheets.get_sesion(conv.id_pendiente or "")
            if not sesion:
                return "error"

            # Save stock item
            auditor = self.sheets.get_auditor(payload.telefono)
            auditor_nombre = auditor.nombre if auditor else "Auditor"
            self.sheets.save_stock_item(
                sesion.id_sesion,
                sesion.sucursal_id,
                auditor_nombre,
                stock_item,
            )

            # Update stock_items_json
            stock_items = json.loads(sesion.stock_items_json) if sesion.stock_items_json else []
            stock_items.append(vars(stock_item))
            sesion.stock_items_json = json.dumps(stock_items, ensure_ascii=False)

            self.sheets.update_sesion(
                sesion.id_sesion,
                estado=ConversationState.EN_STOCK_ITEM.value,
                timestamp_ultimo_punto=datetime.utcnow().isoformat(),
                stock_items_json=sesion.stock_items_json,
            )

            # TODO: Track count and move to next or finish
            # For now, continue with stock loop
            await twilio_client.send_text(
                payload.telefono,
                f"✓ Registrado: {stock_item.nombre}\n\nMandá el próximo producto o 'listo'",
            )

            return "stock_item_guardado"

        except Exception as e:
            logger.error(f"Error in _handle_en_stock_item: {e}", exc_info=True)
            return "error"

    async def _handle_desvio_libre(
        self,
        payload: WAHAPayload,
        conv: Conversacion,
        twilio_client: TwilioClient,
    ) -> str:
        """Handle free-form deviations."""
        try:
            if payload.tipo != "text" or not payload.contenido:
                await twilio_client.send_text(
                    payload.telefono,
                    "⚠️ Mandá 'NO' o describí el desvío",
                )
                return "invalid_response"

            respuesta = payload.contenido.lower().strip()

            if respuesta == "no":
                # Move to compromisos
                sesion = self.sheets.get_sesion(conv.id_pendiente or "")
                if not sesion:
                    return "error"

                self.sheets.update_conversacion(
                    telefono=payload.telefono,
                    estado=ConversationState.COMPROMISOS,
                    id_pendiente=sesion.id_sesion,
                )
                await twilio_client.send_text(
                    payload.telefono,
                    "📝 Compromisos\n\n¿Firmaron compromisos de corrección?\n\nSI / NO / PENDIENTE",
                )
                return "sin_desvios"

            # Parse free deviation
            desvio = await self.parser.parse_desvio_libre(payload.contenido)
            if not desvio:
                await twilio_client.send_text(
                    payload.telefono,
                    "❌ No pude procesar el desvío. Intenta de nuevo.",
                )
                return "parse_error"

            sesion = self.sheets.get_sesion(conv.id_pendiente or "")
            if not sesion:
                return "error"

            # Save deviation
            auditor = self.sheets.get_auditor(payload.telefono)
            auditor_nombre = auditor.nombre if auditor else "Auditor"
            self.sheets.save_desvio_libre(
                sesion.id_sesion,
                sesion.sucursal_id,
                auditor_nombre,
                desvio,
            )

            # Update desvios_libres_json
            desvios_libres = json.loads(sesion.desvios_libres_json) if sesion.desvios_libres_json else []
            desvios_libres.append(vars(desvio))
            sesion.desvios_libres_json = json.dumps(desvios_libres, ensure_ascii=False)

            self.sheets.update_sesion(
                sesion.id_sesion,
                estado=ConversationState.DESVIO_LIBRE.value,
                timestamp_ultimo_punto=datetime.utcnow().isoformat(),
                desvios_libres_json=sesion.desvios_libres_json,
            )

            # Send alert if ALTA
            if desvio.severidad == "Alta":
                from config import get_settings
                settings = get_settings()
                if settings.coordinador_tel:
                    sucursal = self.sheets.get_sucursal(sesion.sucursal_id)
                    sucursal_nombre = sucursal.nombre if sucursal else sesion.sucursal_id
                    await twilio_client.send_alerta_coordinador(
                        settings.coordinador_tel,
                        sucursal_nombre,
                        desvio.area_estimada,
                        desvio.descripcion,
                        "Alta",
                    )

            await twilio_client.send_text(
                payload.telefono,
                f"✓ Registrado desvío en {desvio.area_estimada}\n\n¿Hay más desvíos? Describí o mandá 'NO'",
            )

            return "desvio_registrado"

        except Exception as e:
            logger.error(f"Error in _handle_desvio_libre: {e}", exc_info=True)
            return "error"

    async def _handle_compromisos(
        self,
        payload: WAHAPayload,
        conv: Conversacion,
        twilio_client: TwilioClient,
    ) -> str:
        """Handle compromise commitments (SI/NO/PENDIENTE)."""
        try:
            if payload.tipo != "text" or not payload.contenido:
                await twilio_client.send_text(
                    payload.telefono,
                    "⚠️ Respondé SI, NO o PENDIENTE",
                )
                return "invalid_response"

            respuesta = payload.contenido.upper().strip()
            if respuesta not in {"SI", "SÍ", "NO", "PENDIENTE"}:
                await twilio_client.send_text(
                    payload.telefono,
                    "⚠️ Respondé SI, NO o PENDIENTE",
                )
                return "invalid_response"

            sesion = self.sheets.get_sesion(conv.id_pendiente or "")
            if not sesion:
                return "error"

            # Save commitment status
            sesion.compromisos_firmados = respuesta
            self.sheets.update_sesion(
                sesion.id_sesion,
                estado="completa",
                timestamp_ultimo_punto=datetime.utcnow().isoformat(),
                compromisos_firmados=respuesta,
            )

            # Calculate final score and send summary
            await self._cerrar_auditoria_bloques(sesion, twilio_client, payload.telefono)

            return "compromisos_registrados"

        except Exception as e:
            logger.error(f"Error in _handle_compromisos: {e}", exc_info=True)
            return "error"

    async def _cerrar_auditoria_bloques(
        self,
        sesion: SesionAuditoria,
        twilio_client: TwilioClient,
        phone: str,
    ) -> None:
        """Close block-based audit and send summary."""
        try:
            # Calculate total score
            resultados_por_bloque: Dict[str, List[ResultadoItem]] = {}
            sesion_data = json.loads(sesion.resultados_json) if sesion.resultados_json else {}

            puntaje_total = 0.0
            puntaje_maximo = 0.0
            desvios_count = 0
            alta_count = 0
            media_count = 0
            baja_count = 0

            for bloque_id, items_data in sesion_data.items():
                resultados = [ResultadoItem(**item) for item in items_data]
                resultados_por_bloque[bloque_id] = resultados

                for resultado in resultados:
                    if resultado.puntaje:
                        puntaje_total += resultado.puntaje
                        puntaje_maximo += 5
                    if resultado.tiene_desvio:
                        desvios_count += 1
                        if resultado.severidad == "Alta":
                            alta_count += 1
                        elif resultado.severidad == "Media":
                            media_count += 1
                        else:
                            baja_count += 1

            stock_count = len(json.loads(sesion.stock_items_json) or [])

            # Send final summary
            from datetime import date
            sucursal = self.sheets.get_sucursal(sesion.sucursal_id)
            sucursal_nombre = sucursal.nombre if sucursal else sesion.sucursal_id

            await twilio_client.send_resumen_final(
                phone,
                sucursal_nombre,
                date.today().isoformat(),
                puntaje_total,
                puntaje_maximo,
                resultados_por_bloque,
                desvios_count,
                alta_count,
                media_count,
                baja_count,
                stock_count,
                sesion.compromisos_firmados or "Sin respuesta",
            )

            # Send summary to coordinator
            from config import get_settings
            settings = get_settings()
            if settings.coordinador_tel:
                auditor = self.sheets.get_auditor(phone)
                auditor_nombre = auditor.nombre if auditor else "Auditor"
                coord_msg = (
                    f"📊 **Auditoría Completada (Flujo Bloques)**\n\n"
                    f"Auditor: {auditor_nombre}\n"
                    f"Sucursal: {sucursal_nombre}\n"
                    f"Puntaje: {puntaje_total:.1f}/{puntaje_maximo:.1f}\n"
                    f"Desvíos: {desvios_count}\n"
                    f"  🔴 Críticos: {alta_count}\n"
                    f"  🟡 Importantes: {media_count}\n"
                    f"  🟢 Leves: {baja_count}\n"
                    f"Productos verificados: {stock_count}\n"
                    f"Compromisos: {sesion.compromisos_firmados}\n"
                    f"ID Sesión: {sesion.id_sesion}"
                )
                await twilio_client.send_text(settings.coordinador_tel, coord_msg)

            # Reset conversation
            self.sheets.update_conversacion(
                telefono=phone,
                estado=ConversationState.IDLE,
            )

        except Exception as e:
            logger.error(f"Error closing block audit: {e}", exc_info=True)

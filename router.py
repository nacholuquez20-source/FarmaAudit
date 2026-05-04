"""Conversation router - state machine logic for audit interactions."""



import json

import logging

import uuid

import asyncio

from datetime import datetime, timedelta, timezone

from typing import Any, List, Optional, Tuple, Dict



from models import (

    ConversationState, WhatsAppPayload, Auditor, Conversacion,

    ParserResponse, Reporte, Gestion, Severidad, ChecklistPunto, SesionAuditoria, PuntoEvalResult,

    ItemBloque, ResultadoItem, StockItem, DesvioLibre, ChecklistPerfumeriaPunto, TipoRespuesta,

    MensajeEnRespuesta, RespuestaPregunta, RespuestaPreguntaEstado, RESPUESTA_CONFIG, RESPUESTA_VALIDACION

)

from supabase_manager import SupabaseManager

from parser import AuditParser

from audio import AudioTranscriber

from drive import DriveManager

from meta_client import MetaClient



logger = logging.getLogger(__name__)





class ConversationRouter:

    """Routes messages based on conversation state."""



    # Class-level locks per phone number to prevent concurrent message processing

    _conversation_locks: Dict[str, asyncio.Lock] = {}

    _locks_lock = asyncio.Lock()

    @staticmethod
    def _utc_now_iso() -> str:
        """Return current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()



    def __init__(self):

        """Initialize router with dependencies."""

        self.sheets = SupabaseManager()

        self.parser = AuditParser()

        self.transcriber = AudioTranscriber()

        self.drive = DriveManager()



    @classmethod

    async def _get_conversation_lock(cls, phone: str) -> asyncio.Lock:

        """Get or create lock for a specific conversation."""

        async with cls._locks_lock:

            if phone not in cls._conversation_locks:

                cls._conversation_locks[phone] = asyncio.Lock()

            return cls._conversation_locks[phone]



    async def handle_message(

        self,

        payload: WhatsAppPayload,

        meta_client: MetaClient,

    ) -> str:

        """Route message based on conversation state."""

        # Acquire conversation lock to prevent concurrent processing for same auditor

        lock = await self._get_conversation_lock(payload.telefono)

        async with lock:

            return await self._handle_message_locked(payload, meta_client)



    async def _handle_message_locked(

        self,

        payload: WhatsAppPayload,

        meta_client: MetaClient,

    ) -> str:

        """Internal handler with lock acquired."""

        try:

            # Validate auditor

            auditor = self.sheets.get_auditor(payload.telefono)

            logger.info(f"DEBUG: Searching for auditor with phone={payload.telefono}, found={auditor is not None}, active={auditor.activo if auditor else 'N/A'}")

            if not auditor or not auditor.activo:

                encargado = self.sheets.get_encargado_by_phone(payload.telefono)

                if encargado:

                    return await self.handle_encargado_message(payload, meta_client, encargado)

                await meta_client.send_text(

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

            # Check for audit trigger regardless of current state (allows restarting audit)
            if payload.tipo == "text" and payload.contenido:
                trigger = payload.contenido.lower().strip()
                if trigger in {"hola", "inicio", "empezar", "comenzar", "start"}:
                    return await self._iniciar_seleccion_sucursal(payload, meta_client)

            # Route based on state

            if conv.estado_actual == ConversationState.IDLE:

                return await self._handle_idle_state(payload, auditor, conv, meta_client)

            elif conv.estado_actual == ConversationState.SELECCIONANDO_ESCUADRON:

                return await self._handle_seleccionando_escuadron(payload, auditor, conv, meta_client)

            elif conv.estado_actual == ConversationState.SELECCIONANDO_SUCURSAL_PERFUMERIA:

                return await self._handle_seleccionando_sucursal_perfumeria(payload, conv, meta_client)

            elif conv.estado_actual == ConversationState.SELECCIONANDO_SUCURSAL:

                return await self._handle_seleccionando_sucursal(payload, conv, meta_client)

            elif conv.estado_actual == ConversationState.SELECCIONANDO_TIPO_AUDITORIA:

                return await self._handle_seleccionando_tipo_auditoria(payload, conv, meta_client)

            elif conv.estado_actual == ConversationState.EN_BLOQUE:

                return await self._handle_en_bloque(payload, conv, meta_client)

            elif conv.estado_actual == ConversationState.EN_BLOQUE_PERFUMERIA:

                return await self._handle_en_bloque_perfumeria(payload, conv, meta_client)

            elif conv.estado_actual == ConversationState.CONFIRMANDO_BLOQUE:

                return await self._handle_confirmando_bloque(payload, conv, meta_client)

            elif conv.estado_actual == ConversationState.RECOLECTANDO_RESPUESTA:

                return await self._handle_recolectando_respuesta(payload, conv, meta_client)

            elif conv.estado_actual == ConversationState.STOCK_LOOP:

                return await self._handle_stock_loop(payload, conv, meta_client)

            elif conv.estado_actual == ConversationState.EN_STOCK_ITEM:

                return await self._handle_en_stock_item(payload, conv, meta_client)

            elif conv.estado_actual == ConversationState.DESVIO_LIBRE:

                return await self._handle_desvio_libre(payload, conv, meta_client)

            elif conv.estado_actual == ConversationState.COMPROMISOS:

                return await self._handle_compromisos(payload, conv, meta_client)

            elif conv.estado_actual == ConversationState.EN_AUDITORIA:

                return await self._handle_en_auditoria(payload, conv, meta_client)

            elif conv.estado_actual == ConversationState.AUDITORIA_PAUSADA:

                return await self._handle_auditoria_pausada(payload, conv, meta_client)

            elif conv.estado_actual == ConversationState.ESPERANDO_CONFIRMACION:

                return await self._handle_confirmation_state(payload, conv, meta_client)

            elif conv.estado_actual == ConversationState.ESPERANDO_EDICION:

                return await self._handle_edition_state(payload, conv, meta_client)

            else:

                await meta_client.send_text(payload.telefono, "⚠️ Estado desconocido")

                return "unknown_state"

        except Exception as e:

            logger.error(f"Error handling message from {payload.telefono}: {e}", exc_info=True)

            await meta_client.send_text(

                payload.telefono,

                "❌ Error procesando tu mensaje. Intenta de nuevo.",

            )

            return "error"


    @staticmethod
    def _safe_json_loads(value: str | None) -> Dict[str, Any]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _format_desvio_option(index: int, gestion: Dict[str, Any]) -> str:
        descripcion = str(gestion.get("desvio") or "Sin descripcion").strip()
        if len(descripcion) > 90:
            descripcion = f"{descripcion[:87]}..."
        return f"{index}) [{gestion.get('severidad', '-')}] {descripcion}"

    async def handle_encargado_message(
        self,
        payload: WhatsAppPayload,
        meta_client: MetaClient,
        encargado: Dict[str, Any],
    ) -> str:
        """Handle branch manager responses to open deviations."""
        conv = self.sheets.get_conversacion(payload.telefono)
        if not conv:
            conv = Conversacion(
                telefono=payload.telefono,
                estado_actual=ConversationState.IDLE,
            )

        if conv.estado_actual == ConversationState.ENCARGADO_SELECCIONANDO_DESVIO:
            return await self._handle_encargado_seleccion(payload, conv, meta_client, encargado)

        if conv.estado_actual == ConversationState.ENCARGADO_ESPERANDO_RESPUESTA:
            return await self._handle_encargado_respuesta(payload, conv, meta_client, encargado)

        return await self._start_encargado_flow(payload, meta_client, encargado)

    async def _start_encargado_flow(
        self,
        payload: WhatsAppPayload,
        meta_client: MetaClient,
        encargado: Dict[str, Any],
    ) -> str:
        gestiones = self.sheets.get_gestiones_pendientes_sucursal(str(encargado["id_sucursal"]))
        if not gestiones:
            await meta_client.send_text(
                payload.telefono,
                f"Hola {encargado.get('nombre') or ''}. No tenes desvios pendientes para responder.",
            )
            self.sheets.update_conversacion(payload.telefono, ConversationState.IDLE)
            return "encargado_sin_pendientes"

        opciones = gestiones[:9]
        lines = [
            f"Hola {encargado.get('nombre') or ''}. Tenes {len(gestiones)} desvio(s) pendiente(s):",
            "",
            *[self._format_desvio_option(index, gestion) for index, gestion in enumerate(opciones, start=1)],
            "",
            "Responde con el numero del desvio que queres corregir.",
        ]
        context = {
            "flujo": "encargado",
            "id_sucursal": encargado["id_sucursal"],
            "opciones": [gestion["id_gestion"] for gestion in opciones if gestion.get("id_gestion")],
        }
        self.sheets.update_conversacion(
            telefono=payload.telefono,
            estado=ConversationState.ENCARGADO_SELECCIONANDO_DESVIO,
            ultimo_mensaje=json.dumps(context),
        )
        await meta_client.send_text(payload.telefono, "\n".join(lines))
        return "encargado_menu_enviado"

    async def _handle_encargado_seleccion(
        self,
        payload: WhatsAppPayload,
        conv: Conversacion,
        meta_client: MetaClient,
        encargado: Dict[str, Any],
    ) -> str:
        context = self._safe_json_loads(conv.ultimo_mensaje)
        opciones_raw = context.get("opciones")
        opciones: List[str] = opciones_raw if isinstance(opciones_raw, list) else []
        try:
            selected_index = int((payload.contenido or "").strip()) - 1
        except ValueError:
            await meta_client.send_text(payload.telefono, "Responde solo con el numero del desvio.")
            return "encargado_seleccion_invalida"

        if selected_index < 0 or selected_index >= len(opciones):
            await meta_client.send_text(payload.telefono, "Ese numero no esta en la lista. Proba de nuevo.")
            return "encargado_seleccion_fuera_rango"

        id_gestion = opciones[selected_index]
        gestion = self.sheets.get_gestion_by_id(id_gestion)
        if not gestion or gestion.get("id_sucursal") != encargado.get("id_sucursal"):
            await meta_client.send_text(payload.telefono, "No pude encontrar ese desvio. Escribi cualquier mensaje para reiniciar.")
            self.sheets.update_conversacion(payload.telefono, ConversationState.IDLE)
            return "encargado_desvio_no_encontrado"

        context["id_gestion"] = id_gestion
        self.sheets.update_conversacion(
            telefono=payload.telefono,
            estado=ConversationState.ENCARGADO_ESPERANDO_RESPUESTA,
            id_pendiente=id_gestion,
            ultimo_mensaje=json.dumps(context),
        )
        await meta_client.send_text(
            payload.telefono,
            "Perfecto. Envia una foto de la correccion o escribi una descripcion de lo realizado.",
        )
        return "encargado_desvio_seleccionado"

    async def _handle_encargado_respuesta(
        self,
        payload: WhatsAppPayload,
        conv: Conversacion,
        meta_client: MetaClient,
        encargado: Dict[str, Any],
    ) -> str:
        id_gestion = conv.id_pendiente or self._safe_json_loads(conv.ultimo_mensaje).get("id_gestion")
        if not id_gestion:
            self.sheets.update_conversacion(payload.telefono, ConversationState.IDLE)
            return await self._start_encargado_flow(payload, meta_client, encargado)

        gestion = self.sheets.get_gestion_by_id(str(id_gestion))
        if not gestion or gestion.get("id_sucursal") != encargado.get("id_sucursal"):
            await meta_client.send_text(payload.telefono, "Ese desvio ya no esta disponible para tu sucursal.")
            self.sheets.update_conversacion(payload.telefono, ConversationState.IDLE)
            return "encargado_desvio_no_disponible"

        actor_nombre = str(encargado.get("nombre") or "Encargado")
        try:
            if payload.tipo == "image" and payload.media_id:
                content, mime_type = await meta_client.download_media_with_metadata(payload.media_id)
                path = self.sheets.upload_desvio_evidencia(str(id_gestion), content, mime_type)
                signed_url = self.sheets.create_signed_evidencia_url(path)
                comentario = (payload.contenido or "").strip() or "Foto de correccion enviada por WhatsApp."
                self.sheets.save_encargado_evento(
                    id_gestion=str(id_gestion),
                    tipo="evidencia",
                    contenido=comentario,
                    actor_nombre=actor_nombre,
                    metadata={
                        "origen": "sucursal",
                        "foto_path": path,
                        "foto_url_signed": signed_url,
                        "mime_type": mime_type,
                        "size_bytes": len(content),
                        "canal": "whatsapp",
                    },
                )
            elif payload.tipo == "text" and payload.contenido:
                self.sheets.save_encargado_evento(
                    id_gestion=str(id_gestion),
                    tipo="mensaje",
                    contenido=payload.contenido.strip(),
                    actor_nombre=actor_nombre,
                    metadata={
                        "origen": "sucursal",
                        "leido_por_sucursal": True,
                        "leido_por_auditor": False,
                        "canal": "whatsapp",
                    },
                )
            else:
                await meta_client.send_text(payload.telefono, "Envia una foto o un texto con la correccion.")
                return "encargado_respuesta_invalida"

            self.sheets.create_notifications_for_auditors(str(id_gestion))
            self.sheets.update_conversacion(payload.telefono, ConversationState.IDLE)
            await meta_client.send_text(payload.telefono, "Recibida tu respuesta. El auditor la revisara en FarmaAudit.")
            return "encargado_respuesta_guardada"
        except Exception as e:
            logger.error(f"Error saving encargado response for {id_gestion}: {e}", exc_info=True)
            await meta_client.send_text(payload.telefono, "No pude guardar la respuesta. Intenta nuevamente.")
            return "encargado_respuesta_error"

    def _build_respuesta_collection(
        self,
        payload: WhatsAppPayload,
        media_items: List[dict],
        estado_procesamiento: str,
        error_mensaje: Optional[str] = None,
    ) -> MensajeEnRespuesta:
        contenido = payload.contenido or ""
        if payload.tipo == "audio" and not contenido:
            contenido = "[Audio recibido]"
        if payload.tipo == "image" and not contenido:
            contenido = "[Foto recibida]"
        return MensajeEnRespuesta(
            tipo=payload.tipo,
            contenido=contenido,
            media_ids=media_items,
            timestamp=datetime.now(timezone.utc).isoformat(),
            estado_procesamiento=estado_procesamiento,
            error_mensaje=error_mensaje,
        )

    async def _try_start_respuesta_collection(
        self,
        payload: WhatsAppPayload,
        sesion: SesionAuditoria,
        bloque_id: str,
        return_state: ConversationState,
        meta_client: MetaClient,
    ) -> bool:
        """Start multi-message collection; return True when the message was handled."""
        if getattr(payload, "from_collector", False):
            return False
        if payload.tipo == "text" and (payload.contenido or "").strip().upper() in {"PAUSAR", "SALTAR", "SKIP"}:
            return False

        try:
            now = datetime.now(timezone.utc).isoformat()
            respuesta = self.sheets.create_respuesta_pregunta(RespuestaPregunta(
                id=str(uuid.uuid4()),
                id_sesion=sesion.id_sesion,
                telefono_auditor=payload.telefono,
                pregunta_numero=sesion.punto_actual + 1,
                bloque_id=bloque_id,
                estado=RespuestaPreguntaEstado.RECOLECTANDO,
                timestamp_inicio=now,
                timestamp_ultimo_mensaje=now,
                timeout_segundos=RESPUESTA_CONFIG["timeout_sin_actividad_segundos"],
            ))
            self.sheets.update_conversacion(
                telefono=payload.telefono,
                estado=ConversationState.RECOLECTANDO_RESPUESTA,
                id_pendiente=sesion.id_sesion,
                ultimo_mensaje=json.dumps({"return_state": return_state.value, "bloque_id": bloque_id}),
                id_respuesta_actual=respuesta.id,
            )
            await self._append_respuesta_message(payload, respuesta, meta_client)
            await meta_client.send_text(payload.telefono, "Registrado. Podes enviar mas texto, fotos o audios. Escribi LISTO cuando termines.")
            return True
        except Exception as e:
            logger.error(f"Collector unavailable; refusing to advance block with legacy flow: {e}", exc_info=True)
            await meta_client.send_text(
                payload.telefono,
                "No pude iniciar el registro multi-mensaje, entonces no voy a avanzar de bloque. "
                "Avisale al administrador que ejecute la migracion etapa 8 en Supabase y reintenta.",
            )
            return True

    async def _append_respuesta_message(
        self,
        payload: WhatsAppPayload,
        respuesta_activa: RespuestaPregunta,
        meta_client: MetaClient,
    ) -> MensajeEnRespuesta:
        media_items: List[dict] = []
        estado = "exitoso"
        error_mensaje = None

        try:
            if payload.media_id and payload.tipo in {"image", "audio"}:
                content, mime_type = await meta_client.download_media_with_metadata(payload.media_id)
                path = self.sheets.upload_auditoria_respuesta_media(respuesta_activa.id_sesion, respuesta_activa.id, content, mime_type)
                signed_url = self.sheets.create_signed_auditoria_respuesta_url(path)
                media_items.append({
                    "tipo": payload.tipo,
                    "url": signed_url,
                    "path": path,
                    "mime_type": mime_type,
                    "media_id": payload.media_id,
                })
                self.sheets.create_respuesta_audit_log(respuesta_activa.id, f"{payload.tipo}_subido", {"media_id": payload.media_id, "path": path})
            elif payload.media_url and payload.tipo in {"image", "audio"}:
                media_items.append({"tipo": payload.tipo, "url": payload.media_url, "mime_type": payload.mime_type or ""})
        except Exception as e:
            estado = "error"
            error_mensaje = str(e)
            logger.error(f"Error processing response media: {e}", exc_info=True)

        nuevo_mensaje = self._build_respuesta_collection(payload, media_items, estado, error_mensaje)
        mensajes = [vars(msg) for msg in respuesta_activa.get_mensajes()]
        mensajes.append(vars(nuevo_mensaje))
        media_ids = respuesta_activa.get_media_ids() + media_items

        self.sheets.update_respuesta_pregunta(
            respuesta_activa.id,
            mensajes_json=json.dumps(mensajes, ensure_ascii=False),
            media_ids_json=json.dumps(media_ids, ensure_ascii=False),
            timestamp_ultimo_mensaje=datetime.now(timezone.utc).isoformat(),
            timeout_prompt_enviado=False,
        )
        self.sheets.create_respuesta_audit_log(respuesta_activa.id, "mensaje_agregado", {"tipo": payload.tipo, "estado": estado})
        if estado == "error":
            await meta_client.send_text(payload.telefono, "No pude guardar ese medio. Podes reenviarlo o escribir LISTO.")
        return nuevo_mensaje

    async def _handle_recolectando_respuesta(
        self,
        payload: WhatsAppPayload,
        conv: Conversacion,
        meta_client: MetaClient,
    ) -> str:
        respuesta_activa = self.sheets.get_respuesta_pregunta_activa(payload.telefono)
        if not respuesta_activa:
            self.sheets.update_conversacion(payload.telefono, ConversationState.EN_BLOQUE, id_pendiente=conv.id_pendiente)
            await meta_client.send_text(payload.telefono, "No encontre una respuesta activa. Reintentemos con la pregunta actual.")
            return "respuesta_activa_missing"

        cleaned = (payload.contenido or "").strip().upper()
        if cleaned in {"LISTO", "SIGUIENTE", "TERMINAR", "DONE", "FINISH"}:
            return await self._complete_respuesta_collection(
                respuesta_activa,
                conv,
                payload,
                meta_client,
                auto_complete=False,
                force=respuesta_activa.razon_descarte == "validacion_fallida",
            )

        if len(respuesta_activa.get_mensajes()) >= RESPUESTA_CONFIG["mensaje_max_por_respuesta"]:
            await meta_client.send_text(payload.telefono, "Llegaste al maximo de mensajes para esta respuesta. Escribi LISTO para continuar.")
            return "max_mensajes_alcanzado"

        await self._append_respuesta_message(payload, respuesta_activa, meta_client)
        await meta_client.send_text(payload.telefono, "Registrado. Envia mas o escribi LISTO para continuar.")
        return "respuesta_mensaje_agregado"

    def _validate_respuesta_completitud(
        self,
        bloque_id: str,
        respuesta_consolidada: str,
        media_urls: list,
        mensajes: list,
        force: bool = False,
    ) -> dict:
        regla = RESPUESTA_VALIDACION.get(bloque_id, {"min_texto": 5, "requiere_foto": False, "requiere_audio": False})
        if force:
            return {"es_valida": True}
        if len(respuesta_consolidada.strip()) < regla["min_texto"]:
            return {"es_valida": False, "razon": f"Tu respuesta es muy corta. Minimo {regla['min_texto']} caracteres."}
        if regla["requiere_foto"] and not media_urls:
            return {"es_valida": False, "razon": "Este punto requiere una foto. Envia una imagen y despues escribi LISTO."}
        for msg in mensajes:
            if msg.get("estado_procesamiento") == "error":
                return {"es_valida": False, "razon": f"Hubo un problema con un medio: {msg.get('error_mensaje')}."}
        return {"es_valida": True}

    @staticmethod
    def _format_respuesta_collection_summary(
        mensajes: list,
        respuesta_consolidada: str,
    ) -> str:
        """Build a short WhatsApp summary before advancing to the next block."""
        text_count = 0
        image_count = 0
        audio_count = 0
        other_media_count = 0

        for msg in mensajes:
            tipo = str(msg.get("tipo", "text"))
            contenido = str(msg.get("contenido", "")).strip()
            if tipo == "text" and contenido and not contenido.startswith("["):
                text_count += 1
            for media in msg.get("media_ids", []) or []:
                media_tipo = str(media.get("tipo") or tipo)
                if media_tipo == "image":
                    image_count += 1
                elif media_tipo == "audio":
                    audio_count += 1
                else:
                    other_media_count += 1

        resumen_texto = respuesta_consolidada.strip()
        if len(resumen_texto) > 500:
            resumen_texto = f"{resumen_texto[:497]}..."

        adjuntos = []
        if image_count:
            adjuntos.append(f"{image_count} foto(s)")
        if audio_count:
            adjuntos.append(f"{audio_count} audio(s)")
        if other_media_count:
            adjuntos.append(f"{other_media_count} adjunto(s)")

        lines = [
            "Resumen de lo registrado:",
            f"- Mensajes de texto: {text_count}",
            f"- Adjuntos: {', '.join(adjuntos) if adjuntos else 'sin adjuntos'}",
        ]
        if resumen_texto:
            lines.extend(["", resumen_texto])
        lines.extend(["", "Continuamos con el siguiente bloque."])
        return "\n".join(lines)

    async def _complete_respuesta_collection(
        self,
        respuesta_activa: RespuestaPregunta,
        conv: Conversacion,
        payload: WhatsAppPayload,
        meta_client: MetaClient,
        auto_complete: bool,
        force: bool = False,
    ) -> str:
        fresh = self.sheets.get_respuesta_pregunta(respuesta_activa.id) or respuesta_activa
        mensajes = [vars(msg) for msg in fresh.get_mensajes()]
        textos = [
            str(msg.get("contenido", "")).strip()
            for msg in mensajes
            if str(msg.get("contenido", "")).strip() and not str(msg.get("contenido", "")).startswith("[")
        ]
        media_urls = [media.get("url") for msg in mensajes for media in msg.get("media_ids", []) if media.get("url")]
        respuesta_consolidada = "\n".join(textos).strip()
        if not respuesta_consolidada and media_urls:
            respuesta_consolidada = "Respuesta enviada con evidencia multimedia."
        respuesta_consolidada = respuesta_consolidada[:RESPUESTA_CONFIG["respuesta_max_caracteres"]]

        validacion = self._validate_respuesta_completitud(fresh.bloque_id, respuesta_consolidada, media_urls, mensajes, force=force)
        if not validacion["es_valida"]:
            self.sheets.create_respuesta_audit_log(fresh.id, "validacion_fallida", {"razon": validacion["razon"]})
            await meta_client.send_text(payload.telefono, f"{validacion['razon']}\n\nAgrega mas datos o escribi LISTO otra vez para continuar igual.")
            self.sheets.update_respuesta_pregunta(fresh.id, timeout_prompt_enviado=False, razon_descarte="validacion_fallida")
            return "respuesta_validation_failed"

        self.sheets.update_respuesta_pregunta(
            fresh.id,
            estado="completada",
            respuesta_consolidada=respuesta_consolidada,
            confirmado_por_auditor=not auto_complete,
            timestamp_ultimo_mensaje=datetime.now(timezone.utc).isoformat(),
        )
        self.sheets.create_respuesta_audit_log(fresh.id, "completada", {"auto_complete": auto_complete, "mensajes_count": len(mensajes), "media_count": len(media_urls)})

        if not auto_complete:
            await meta_client.send_text(
                payload.telefono,
                self._format_respuesta_collection_summary(mensajes, respuesta_consolidada),
            )

        context = self._safe_json_loads(conv.ultimo_mensaje)
        return_state = context.get("return_state", ConversationState.EN_BLOQUE.value)
        sesion = self.sheets.get_sesion(fresh.id_sesion)
        if not sesion:
            await meta_client.send_text(payload.telefono, "Respuesta registrada, pero no encontre la sesion para avanzar.")
            return "respuesta_completada_sin_sesion"

        self.sheets.update_conversacion(
            telefono=payload.telefono,
            estado=ConversationState(return_state),
            id_pendiente=sesion.id_sesion,
            id_respuesta_actual="",
        )

        synthetic_payload = WhatsAppPayload(telefono=payload.telefono, tipo="text", contenido=respuesta_consolidada)
        setattr(synthetic_payload, "from_collector", True)

        if return_state == ConversationState.EN_BLOQUE_PERFUMERIA.value:
            bloques_perfumeria = self.sheets.get_checklist_perfumeria()
            bloques_ordenados = sorted(bloques_perfumeria.keys())
            puntos_bloque = bloques_perfumeria.get(fresh.bloque_id, [])
            return await self._handle_perfumeria_respuesta_abierta(synthetic_payload, fresh.bloque_id, puntos_bloque, sesion, bloques_ordenados, meta_client)

        return await self._handle_en_bloque(
            synthetic_payload,
            Conversacion(telefono=payload.telefono, estado_actual=ConversationState.EN_BLOQUE, id_pendiente=sesion.id_sesion),
            meta_client,
        )



    async def _handle_idle_state(

        self,

        payload: WhatsAppPayload,

        auditor: Auditor,

        conv: Conversacion,

        meta_client: MetaClient,

    ) -> str:

        """Handle message in idle state."""

        # Check for special commands

        if payload.contenido and payload.contenido.startswith("/"):

            return await self._handle_command(payload, auditor, meta_client)



        # Check for guided audit trigger ("hola", "inicio", "empezar", "comenzar", "start")

        if payload.tipo == "text" and payload.contenido:

            trigger = payload.contenido.lower().strip()

            if trigger in {"hola", "inicio", "empezar", "comenzar", "start"}:

                return await self._iniciar_seleccion_sucursal(payload, meta_client)



            await meta_client.send_text(

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

                await meta_client.send_text(

                    payload.telefono,

                    "❌ Error transcribiendo audio. Intenta de nuevo.",

                )

                return "transcription_error"



        # If image without text, ask for context

        if payload.tipo == "image" and not payload.contenido:

            await meta_client.send_text(

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

            await meta_client.send_text(

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

        await self._show_draft(parse_result, photo_url, payload.telefono, meta_client)

        return "parse_success"



    async def _handle_confirmation_state(

        self,

        payload: WhatsAppPayload,

        conv: Conversacion,

        meta_client: MetaClient,

    ) -> str:

        """Handle response in confirmation state."""

        if not payload.contenido:

            return "invalid_input"



        answer = payload.contenido.strip().upper()

        logger.info(f"Confirmation response from {payload.telefono}: '{answer}'")



        # Check for yes responses (with or without accent)

        if answer in {"SI", "SÍ", "YES", "Y"}:

            logger.info(f"Confirmed finding for {payload.telefono}")

            return await self._confirm_and_create(conv, meta_client)

        elif answer in {"NO", "N"}:

            # Discard

            logger.info(f"Discarded finding for {payload.telefono}")

            await meta_client.send_text(

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

            await meta_client.send_text(

                payload.telefono,

                "✏️ ¿Qué necesitas editar? Enviame la corrección.",

            )

            return "edit_requested"

        else:

            logger.warning(f"Invalid confirmation response from {payload.telefono}: '{answer}'")

            await meta_client.send_text(

                payload.telefono,

                "⚠️ Por favor responde con:\nSI - para confirmar\nNO - para descartar\nEDITAR - para hacer cambios",

            )

            return "invalid_response"



    async def _handle_edition_state(

        self,

        payload: WhatsAppPayload,

        conv: Conversacion,

        meta_client: MetaClient,

    ) -> str:

        """Handle correction in edition state."""

        if not payload.contenido:

            return "invalid_input"



        # Get pending data

        pendiente = self.sheets.get_pendiente(conv.id_pendiente)

        if not pendiente:

            await meta_client.send_text(

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

                await meta_client.send_text(

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

            await self._show_draft(corrected, photo_url, payload.telefono, meta_client)

            return "correction_applied"

        except Exception as e:

            logger.error(f"Error applying correction: {e}")

            await meta_client.send_text(

                payload.telefono,

                "❌ Error procesando la corrección.",

            )

            return "error"


    async def _handle_seleccionando_escuadron(
        self,
        payload: WhatsAppPayload,
        auditor: Auditor,
        conv: Conversacion,
        meta_client: MetaClient,
    ) -> str:
        """Handle escuadrón selection."""
        try:
            if not payload.contenido:
                await meta_client.send_text(
                    payload.telefono,
                    "⚠️ Por favor, escribe: Perfumería o Medicamentos"
                )
                return "empty_escuadron"

            escuadron_input = payload.contenido.strip().lower()

            # Normalize auditor's escuadrón
            escuadron_auditor = auditor.cuadrilla.lower().strip()

            # Check if auditor belongs to this escuadrón
            if escuadron_input not in escuadron_auditor:
                await meta_client.send_text(
                    payload.telefono,
                    f"❌ No perteneces al escuadrón '{payload.contenido.strip()}'. Tu escuadrón es: {auditor.cuadrilla}"
                )
                return "escuadron_mismatch"

            # Get all sucursales
            sucursales = self.sheets.get_all_sucursales()
            if not sucursales:
                await meta_client.send_text(
                    payload.telefono,
                    "❌ No hay sucursales disponibles.",
                )
                return "no_sucursales"

            # Build sucursal menu
            menu = f"🏪 Auditoría {auditor.cuadrilla}\n\nSelecciona tu sucursal:\n\n"
            for i, s in enumerate(sucursales, 1):
                menu += f"{i}. {s.nombre} ({s.zona})\n"
            menu += "\nResponde con el número de la sucursal."

            await meta_client.send_text(payload.telefono, menu)

            # Update conversation state
            self.sheets.update_conversacion(
                telefono=payload.telefono,
                estado=ConversationState.SELECCIONANDO_SUCURSAL_PERFUMERIA,
                id_pendiente="",
            )

            return "sucursal_menu_sent"

        except Exception as e:
            logger.error(f"Error handling escuadrón selection: {e}")
            await meta_client.send_text(
                payload.telefono,
                "❌ Error procesando tu escuadrón.",
            )
            return "error"


    async def _handle_seleccionando_sucursal_perfumeria(
        self,
        payload: WhatsAppPayload,
        conv: Conversacion,
        meta_client: MetaClient,
    ) -> str:
        """Handle sucursal selection for perfumery audit."""
        try:
            if not payload.contenido:
                await meta_client.send_text(
                    payload.telefono,
                    "⚠️ Por favor, responde con el número de la sucursal."
                )
                return "empty_sucursal"

            try:
                choice = int(payload.contenido.strip())
            except ValueError:
                await meta_client.send_text(
                    payload.telefono,
                    "⚠️ Opción no válida. Elige un número entre 1 y 25."
                )
                return "invalid_number"

            sucursales = self.sheets.get_all_sucursales()
            if not sucursales or choice < 1 or choice > len(sucursales):
                await meta_client.send_text(
                    payload.telefono,
                    f"⚠️ Opción no válida. Elige un número entre 1 y {len(sucursales)}."
                )
                return "invalid_choice"

            sucursal = sucursales[choice - 1]

            # Get perfumery checklist
            bloques_perfumeria = self.sheets.get_checklist_perfumeria()
            if not bloques_perfumeria:
                await meta_client.send_text(
                    payload.telefono,
                    "❌ No hay checklist de perfumería disponible.",
                )
                return "no_checklist"

            # Create audit session
            import uuid
            sesion_id = str(uuid.uuid4())[:12]
            auditor = self.sheets.get_auditor(payload.telefono)

            # Get first block
            bloques_ordenados = sorted(bloques_perfumeria.keys())
            primer_bloque = bloques_ordenados[0] if bloques_ordenados else ""

            sesion = SesionAuditoria(
                id_sesion=sesion_id,
                telefono_auditor=payload.telefono,
                sucursal_id=sucursal.id,
                estado="en_curso",
                timestamp_inicio=self._utc_now_iso(),
                timestamp_ultimo_punto=self._utc_now_iso(),
                punto_actual=0,
                total_puntos=len(bloques_ordenados),
                hallazgos_json="[]",
                omitidos_json="[]",
                bloque_actual=primer_bloque,
                resultados_json="{}",
                stock_total=0,
                stock_actual=0,
                stock_items_json="[]",
                desvios_libres_json="[]",
                compromisos_firmados="",
            )

            self.sheets.create_sesion(sesion)

            # Update conversation state
            self.sheets.update_conversacion(
                telefono=payload.telefono,
                estado=ConversationState.EN_BLOQUE_PERFUMERIA,
                id_pendiente=sesion_id,
            )

            # Send welcome message
            await meta_client.send_text(
                payload.telefono,
                f"✅ Comenzando auditoría de perfumería en {sucursal.nombre}\n\nResponde las siguientes preguntas."
            )

            puntos_bloque = bloques_perfumeria.get(primer_bloque, [])
            bloque_nombre = puntos_bloque[0].bloque_nombre if puntos_bloque else primer_bloque
            pregunta = self._build_tema_pregunta(primer_bloque, bloque_nombre, puntos_bloque)
            await meta_client.send_text(
                payload.telefono,
                f"{pregunta}\n\nPodes enviar multiples mensajes. Escribi LISTO cuando termines.",
            )
            return "sesion_created"

        except Exception as e:
            logger.error(f"Error handling sucursal selection: {e}")
            await meta_client.send_text(
                payload.telefono,
                "❌ Error iniciando auditoría.",
            )
            return "error"


    async def _handle_command(

        self,

        payload: WhatsAppPayload,

        auditor: Auditor,

        meta_client: MetaClient,

    ) -> str:

        """Handle special commands."""

        cmd = payload.contenido.lower().strip()



        if cmd == "/ayuda":

            await meta_client.send_text(

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

            await meta_client.send_text(

                payload.telefono,

                "📊 Resumen del día:\n(Pronto disponible)",

            )

            return "summary_requested"

        elif cmd == "/mis":

            # TODO: Implement user's reports today

            await meta_client.send_text(

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

        meta_client: MetaClient,

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

            await meta_client.send_file(phone, photo_url, draft)

        else:

            await meta_client.send_text(phone, draft)



    async def _confirm_and_create(

        self,

        conv: Conversacion,

        meta_client: MetaClient,

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

                await meta_client.send_text(sucursal.tel_responsable, msg)



            # Clean up

            self.sheets.delete_pendiente(conv.id_pendiente)

            self.sheets.update_conversacion(

                telefono=conv.telefono,

                estado=ConversationState.IDLE,

            )



            await meta_client.send_text(

                conv.telefono,

                "✅ Hallazgos guardados. Notificaciones enviadas a responsables.",

            )

            return "confirmed"

        except Exception as e:

            logger.error(f"Error confirming and creating: {e}")

            await meta_client.send_text(

                conv.telefono,

                "❌ Error guardando hallazgos.",

            )

            return "error"



    async def _iniciar_seleccion_sucursal(

        self,

        payload: WhatsAppPayload,

        meta_client: MetaClient,

    ) -> str:

        """Start audit flow: show sucursal list based on auditor's escuadrón."""

        try:

            # Get auditor to check their cuadrilla
            auditor = self.sheets.get_auditor(payload.telefono)
            if not auditor or not auditor.activo:
                await meta_client.send_text(
                    payload.telefono,
                    "❌ No estás registrado como auditor. Contacta al coordinador.",
                )
                return "auditor_not_found"

            # Cancel any previous session
            conv_actual = self.sheets.get_conversacion(payload.telefono)
            if conv_actual and conv_actual.id_pendiente:
                sesion_previa = self.sheets.get_sesion(conv_actual.id_pendiente)
                if sesion_previa and sesion_previa.estado not in {"completa", "cancelada"}:
                    self.sheets.update_sesion(
                        id_sesion=sesion_previa.id_sesion,
                        estado="cancelada",
                        timestamp_ultimo_punto=self._utc_now_iso(),
                        punto_actual=sesion_previa.punto_actual,
                        hallazgos_json=sesion_previa.hallazgos_json,
                        omitidos_json=sesion_previa.omitidos_json,
                    )

            # Get all sucursales
            sucursales = self.sheets.get_all_sucursales()
            if not sucursales:
                await meta_client.send_text(
                    payload.telefono,
                    "❌ No hay sucursales disponibles.",
                )
                return "no_sucursales"

            # Build sucursal menu with auditor's escuadrón
            menu = f"👋 ¡Hola {auditor.nombre}! 🏪 Auditoría {auditor.cuadrilla}\n\n"
            menu += "Selecciona tu sucursal:\n\n"
            for i, s in enumerate(sucursales, 1):
                menu += f"{i}. {s.nombre} ({s.zona})\n"
            menu += "\nResponde con el número de la sucursal."

            await meta_client.send_text(payload.telefono, menu)

            # Update conversation state directly to sucursal selection
            self.sheets.update_conversacion(
                telefono=payload.telefono,
                estado=ConversationState.SELECCIONANDO_SUCURSAL_PERFUMERIA,
                id_pendiente="",
            )

            return "sucursal_menu_sent"

        except Exception as e:

            logger.error(f"Error initiating audit: {e}")

            await meta_client.send_text(

                payload.telefono,

                "❌ Error iniciando auditoría.",

            )

            return "error"



    async def _handle_seleccionando_sucursal(

        self,

        payload: WhatsAppPayload,

        conv: Conversacion,

        meta_client: MetaClient,

    ) -> str:

        """Handle sucursal selection."""

        try:

            if not payload.contenido:

                await meta_client.send_text(

                    payload.telefono,

                    "⚠️ Por favor responde con un número.",

                )

                return "invalid_input"



            # Parse selection

            try:

                choice = int(payload.contenido.strip())

            except ValueError:

                await meta_client.send_text(

                    payload.telefono,

                    "⚠️ Responde con un número válido.",

                )

                return "invalid_number"



            sucursales = self.sheets.get_all_sucursales()

            if choice < 1 or choice > len(sucursales):

                await meta_client.send_text(

                    payload.telefono,

                    f"⚠️ Número fuera de rango. Elige entre 1 y {len(sucursales)}.",

                )

                return "out_of_range"



            sucursal = sucursales[choice - 1]



            # Get checklist

            checklist = self.sheets.get_checklist()

            if not checklist:

                await meta_client.send_text(

                    payload.telefono,

                    "❌ No hay checklist disponible.",

                )

                return "no_checklist"



            # Create session

            bloques = self.sheets.get_checklist_bloques()

            if not bloques:

                await meta_client.send_text(

                    payload.telefono,

                    "❌ No hay bloques de checklist disponibles.",

                )

                return "no_checklist_blocks"



            bloque_inicial = sorted(bloques.keys())[0]

            id_sesion = f"ses_{uuid.uuid4().hex[:8]}"

            sesion = SesionAuditoria(

                id_sesion=id_sesion,

                telefono_auditor=payload.telefono,

                sucursal_id=sucursal.id,

                punto_actual=0,

                total_puntos=sum(len(items) for items in bloques.values()),

                hallazgos_json="[]",

                omitidos_json="[]",

                estado="en_curso",

                timestamp_inicio=self._utc_now_iso(),

                timestamp_ultimo_punto=self._utc_now_iso(),

                bloque_actual=bloque_inicial,

            )



            self.sheets.create_sesion(sesion)



            # Update conversation

            self.sheets.update_conversacion(

                telefono=payload.telefono,

                estado=ConversationState.EN_BLOQUE,

                id_pendiente=id_sesion,

            )



            # Send first block

            await meta_client.send_text(

                payload.telefono,

                f"✅ Iniciando auditoría en {sucursal.nombre}",

            )

            await meta_client.send_bloque_prompt(

                payload.telefono,

                bloque_inicial,

                f"Bloque {bloque_inicial}",

                bloques[bloque_inicial],

            )



            return "auditoria_started"

        except Exception as e:

            logger.error(f"Error handling sucursal selection: {e}")

            await meta_client.send_text(

                payload.telefono,

                "❌ Error seleccionando sucursal.",

            )

            return "error"


    async def _handle_seleccionando_tipo_auditoria(
        self,
        payload: WhatsAppPayload,
        conv: Conversacion,
        meta_client: MetaClient,
    ) -> str:
        """Handle audit type selection (general or perfumery)."""
        try:
            if not payload.contenido:
                await meta_client.send_text(
                    payload.telefono,
                    "⚠️ Por favor responde con un número.",
                )
                return "invalid_input"

            try:
                choice = int(payload.contenido.strip())
            except ValueError:
                await meta_client.send_text(
                    payload.telefono,
                    "⚠️ Responde con un número válido.",
                )
                return "invalid_number"

            # For now, only perfumery (option 1)
            if choice == 1:
                # Perfumery audit - continue with sucursal selection
                return await self._iniciar_seleccion_sucursal_perfumeria(payload, meta_client)
            else:
                await meta_client.send_text(
                    payload.telefono,
                    "⚠️ Opción no válida. Elige 1 para Perfumería.",
                )
                return "invalid_choice"

        except Exception as e:
            logger.error(f"Error handling audit type selection: {e}")
            await meta_client.send_text(
                payload.telefono,
                "❌ Error procesando tu selección.",
            )
            return "error"


    async def _iniciar_seleccion_sucursal_perfumeria(
        self,
        payload: WhatsAppPayload,
        meta_client: MetaClient,
    ) -> str:
        """Start perfumery audit flow: send sucursal list."""
        try:
            sucursales = self.sheets.get_all_sucursales()

            if not sucursales:
                await meta_client.send_text(
                    payload.telefono,
                    "❌ No hay sucursales disponibles.",
                )
                return "no_sucursales"

            # Build menu
            menu = "🏪 Auditoría Perfumería\n\nSelecciona tu sucursal:\n\n"
            for i, s in enumerate(sucursales, 1):
                menu += f"{i}. {s.nombre} ({s.zona})\n"

            menu += "\nResponde con el número de la sucursal."

            await meta_client.send_text(payload.telefono, menu)

            # Update conversation state
            self.sheets.update_conversacion(
                telefono=payload.telefono,
                estado=ConversationState.SELECCIONANDO_TIPO_AUDITORIA,
                id_pendiente="",
            )

            return "sucursal_menu_sent"

        except Exception as e:
            logger.error(f"Error initiating sucursal selection for perfumery: {e}")
            await meta_client.send_text(
                payload.telefono,
                "❌ Error iniciando auditoría.",
            )
            return "error"


    def _build_tema_pregunta(self, bloque_id: str, bloque_nombre: str, puntos: list) -> str:
        """Build thematic question with context of all points in block."""
        emoji_map = {
            "PRES": "🏪",
            "GOND": "📦",
            "STOCK": "📊",
            "REVISTA": "📰",
            "PERSONAL": "👔",
            "COND": "🏗️",
            "ATENCION": "👥",
            "EXTRAS": "📝",
        }
        emoji = emoji_map.get(bloque_id, "📋")

        msg = f"{emoji} {bloque_nombre.upper()}\n\n"
        msg += "Verifica:\n"
        for punto in puntos:
            msg += f"• {punto.pregunta}\n"
        msg += "\n¿Qué observas?"
        return msg

    async def _handle_en_bloque_perfumeria(
        self,
        payload: WhatsAppPayload,
        conv: Conversacion,
        meta_client: MetaClient,
    ) -> str:
        """Handle perfumery audit flow - thematic questions grouped by block."""
        try:
            # Get active session
            sesion = self.sheets.get_sesion(conv.id_pendiente)

            if not sesion:
                await meta_client.send_text(
                    payload.telefono,
                    "❌ Sesión no encontrada.",
                )
                return "sesion_not_found"

            # Get perfumery checklist grouped by block
            bloques_perfumeria = self.sheets.get_checklist_perfumeria()

            if not bloques_perfumeria:
                await meta_client.send_text(
                    payload.telefono,
                    "❌ No hay checklist de perfumería disponible.",
                )
                return "no_checklist"

            # Get ordered list of block IDs
            bloques_ordenados = sorted(bloques_perfumeria.keys())

            # Check if audit is complete
            if sesion.bloque_actual not in bloques_ordenados:
                # Audit complete
                await meta_client.send_text(
                    payload.telefono,
                    "✅ ¡Auditoría completada!",
                )

                self.sheets.update_sesion(
                    id_sesion=sesion.id_sesion,
                    estado="completa",
                    timestamp_ultimo_punto=self._utc_now_iso(),
                    punto_actual=sesion.punto_actual,
                    hallazgos_json=sesion.hallazgos_json,
                    omitidos_json=sesion.omitidos_json,
                )

                self.sheets.update_conversacion(
                    telefono=payload.telefono,
                    estado=ConversationState.IDLE,
                    id_pendiente="",
                )

                return "auditoria_completa"

            # Get current block
            bloque_actual_id = sesion.bloque_actual
            puntos_bloque = bloques_perfumeria.get(bloque_actual_id, [])

            if not puntos_bloque:
                logger.warning(f"No puntos found for bloque {bloque_actual_id}")
                return "bloque_not_found"

            if await self._try_start_respuesta_collection(
                payload,
                sesion,
                bloque_actual_id,
                ConversationState.EN_BLOQUE_PERFUMERIA,
                meta_client,
            ):
                return "respuesta_collection_started"

            # Handle response (text/photo)
            return await self._handle_perfumeria_respuesta_abierta(
                payload, bloque_actual_id, puntos_bloque, sesion, bloques_ordenados, meta_client
            )

        except Exception as e:
            logger.error(f"Error in _handle_en_bloque_perfumeria: {e}", exc_info=True)
            await meta_client.send_text(
                payload.telefono,
                "❌ Error procesando tu respuesta.",
            )
            return "error"

    async def _handle_perfumeria_respuesta_abierta(
        self,
        payload: WhatsAppPayload,
        bloque_id: str,
        puntos_bloque: list,
        sesion: SesionAuditoria,
        bloques_ordenados: list,
        meta_client: MetaClient,
    ) -> str:
        """Handle open-ended responses for perfumery audit blocks."""
        try:
            # Handle photo first
            if payload.tipo == "image" and payload.media_url:
                try:
                    photo_url = await self.drive.upload_photo_from_url(
                        payload.media_url,
                        f"perf_audit_{sesion.id_sesion}_{bloque_id}_{uuid.uuid4().hex[:4]}.jpg"
                    )
                    resultados = json.loads(sesion.resultados_json) if sesion.resultados_json else {}
                    if f"bloque_{bloque_id}_fotos" not in resultados:
                        resultados[f"bloque_{bloque_id}_fotos"] = []
                    resultados[f"bloque_{bloque_id}_fotos"].append(photo_url)

                    self.sheets.update_sesion(
                        id_sesion=sesion.id_sesion,
                        estado=sesion.estado,
                        timestamp_ultimo_punto=self._utc_now_iso(),
                        punto_actual=sesion.punto_actual,
                        hallazgos_json=sesion.hallazgos_json,
                        omitidos_json=sesion.omitidos_json,
                        resultados_json=json.dumps(resultados, ensure_ascii=False),
                    )

                    # Ask for text observation
                    bloque_nombre = puntos_bloque[0].bloque_nombre if puntos_bloque else bloque_id
                    await meta_client.send_text(
                        payload.telefono,
                        f"📸 Foto guardada.\n\nAhora, describe: ¿Qué observas en {bloque_nombre}?"
                    )
                    return "waiting_text"

                except Exception as e:
                    logger.error(f"Error uploading photo: {e}")
                    await meta_client.send_text(
                        payload.telefono,
                        "❌ Error subiendo foto. Intenta de nuevo."
                    )
                    return "upload_error"

            # Handle text response
            elif payload.contenido:
                respuesta = payload.contenido.strip()

                if not respuesta or len(respuesta) < 2:
                    await meta_client.send_text(
                        payload.telefono,
                        "⚠️ Por favor describe con más detalle lo que observas."
                    )
                    return "invalid_response"

                # Store response and extract deviations with Claude
                resultados = json.loads(sesion.resultados_json) if sesion.resultados_json else {}
                bloque_nombre = puntos_bloque[0].bloque_nombre if puntos_bloque else bloque_id

                # Build context for Claude
                contexto_puntos = "\n".join([f"- {p.pregunta}" for p in puntos_bloque])

                resultados[f"bloque_{bloque_id}"] = {
                    "bloque_nombre": bloque_nombre,
                    "respuesta": respuesta,
                    "timestamp": self._utc_now_iso()
                }

                # Parse deviations with Claude
                desvios = await self._extract_perfumeria_deviations(
                    bloque_nombre, contexto_puntos, respuesta
                )

                auditor = self.sheets.get_auditor(payload.telefono)
                auditor_nombre = auditor.nombre if auditor else "Auditor"

                # Persist each extracted deviation in the same tables used by the web UI.
                hallazgos = json.loads(sesion.hallazgos_json) if sesion.hallazgos_json else []
                for desvio in desvios:
                    persisted = self.sheets.save_perfumeria_desvio(
                        auditoria_id=sesion.id_sesion,
                        sucursal_id=sesion.sucursal_id,
                        auditor_nombre=auditor_nombre,
                        bloque_nombre=bloque_nombre,
                        descripcion=str(desvio.get("desvio", "")),
                        severidad=str(desvio.get("severidad", "Media")),
                    )
                    desvio.update(persisted)
                    hallazgos.append(desvio)

                # Move to next block
                current_index = bloques_ordenados.index(bloque_id)
                siguiente_bloque = bloques_ordenados[current_index + 1] if current_index + 1 < len(bloques_ordenados) else None

                self.sheets.update_sesion(
                    id_sesion=sesion.id_sesion,
                    estado=sesion.estado,
                    timestamp_ultimo_punto=self._utc_now_iso(),
                    punto_actual=sesion.punto_actual + 1,
                    hallazgos_json=json.dumps(hallazgos, ensure_ascii=False),
                    omitidos_json=sesion.omitidos_json,
                    resultados_json=json.dumps(resultados, ensure_ascii=False),
                    bloque_actual=siguiente_bloque or "",
                )

                # Show next question or completion
                if siguiente_bloque:
                    bloques_perfumeria = self.sheets.get_checklist_perfumeria()
                    puntos_siguiente = bloques_perfumeria.get(siguiente_bloque, [])
                    siguiente_nombre = puntos_siguiente[0].bloque_nombre if puntos_siguiente else siguiente_bloque
                    pregunta = self._build_tema_pregunta(siguiente_bloque, siguiente_nombre, puntos_siguiente)
                    await meta_client.send_text(payload.telefono, f"✅ Registrado.\n\n{pregunta}")
                else:
                    await meta_client.send_text(
                        payload.telefono,
                        "✅ ¡Auditoría completada!"
                    )

                return "respuesta_procesada"

            else:
                # Initial question display
                bloque_nombre = puntos_bloque[0].bloque_nombre if puntos_bloque else bloque_id
                pregunta = self._build_tema_pregunta(bloque_id, bloque_nombre, puntos_bloque)
                await meta_client.send_text(payload.telefono, pregunta)
                return "waiting_input"

        except Exception as e:
            logger.error(f"Error in _handle_perfumeria_respuesta_abierta: {e}", exc_info=True)
            await meta_client.send_text(
                payload.telefono,
                "❌ Error procesando tu respuesta.",
            )
            return "error"

    async def _extract_perfumeria_deviations(
        self,
        bloque_nombre: str,
        contexto_puntos: str,
        respuesta_auditor: str,
    ) -> list:
        """Extract deviations from auditor's open-ended response using Claude."""
        try:
            prompt = f"""Analiza la respuesta del auditor y extrae SOLO los desvios o problemas observados.

BLOQUE: {bloque_nombre}
PUNTOS A VERIFICAR:
{contexto_puntos}

RESPUESTA DEL AUDITOR:
"{respuesta_auditor}"

TAREA:
1. Si la respuesta indica que TODO está bien/correcto, retorna: []
2. Si hay desvios/problemas, retorna un JSON array con desvios. Cada desvio debe tener:
   - "desvio": descripción clara del problema
   - "severidad": "Alta" si es crítico/urgente, "Media" si es importante, "Baja" si es menor

Retorna SOLO el JSON array, sin explicaciones.

EJEMPLO SI TODO ESTÁ BIEN:
[]

EJEMPLO SI HAY DESVIOS:
[
  {{"desvio": "Vidriera desordenada", "severidad": "Media"}},
  {{"desvio": "Falta stock en gondolas", "severidad": "Alta"}}
]"""

            response = self.parser.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            respuesta_texto = response.content[0].text.strip()

            # Parse JSON response
            desvios_data = json.loads(respuesta_texto)

            # Convert to hallazgo format
            desvios = []
            for dev in desvios_data:
                desvios.append({
                    "bloque": bloque_nombre,
                    "desvio": dev.get("desvio", ""),
                    "severidad": dev.get("severidad", "Media"),
                    "timestamp": self._utc_now_iso()
                })

            return desvios

        except json.JSONDecodeError:
            logger.warning(f"Could not parse Claude response as JSON: {respuesta_texto}")
            return []
        except Exception as e:
            logger.error(f"Error extracting deviations: {e}")
            return []

    async def _handle_perfumeria_foto_si_no(
        self,
        payload: WhatsAppPayload,
        punto: ChecklistPerfumeriaPunto,
        sesion: SesionAuditoria,
        todos_puntos: list,
        meta_client: MetaClient,
    ) -> str:
        """Handle photo + yes/no response for perfumery audit."""
        try:
            # If image received, ask for confirmation
            if payload.tipo == "image" and payload.media_url:
                try:
                    photo_url = await self.drive.upload_photo_from_url(
                        payload.media_url,
                        f"perf_audit_{sesion.id_sesion}_{punto.bloque_id}_{uuid.uuid4().hex[:4]}.jpg"
                    )

                    # Store photo URL temporarily in session
                    resultados = json.loads(sesion.resultados_json) if sesion.resultados_json else {}
                    resultados[f"punto_{sesion.punto_actual}_foto"] = photo_url

                    self.sheets.update_sesion(
                        id_sesion=sesion.id_sesion,
                        estado=sesion.estado,
                        timestamp_ultimo_punto=self._utc_now_iso(),
                        punto_actual=sesion.punto_actual,
                        hallazgos_json=sesion.hallazgos_json,
                        omitidos_json=sesion.omitidos_json,
                        resultados_json=json.dumps(resultados, ensure_ascii=False),
                    )

                    await meta_client.send_text(
                        payload.telefono,
                        f"📸 Foto recibida.\n\n{punto.pregunta}\n\nResponde: sí / no / problemas"
                    )

                    return "waiting_confirmation"

                except Exception as e:
                    logger.error(f"Error uploading photo: {e}")
                    await meta_client.send_text(
                        payload.telefono,
                        "❌ Error subiendo foto. Intenta de nuevo."
                    )
                    return "upload_error"

            # If confirmation received
            elif payload.contenido:
                respuesta = payload.contenido.lower().strip()

                if respuesta not in {"sí", "si", "no", "problemas"}:
                    await meta_client.send_text(
                        payload.telefono,
                        "⚠️ Responde: sí / no / problemas"
                    )
                    return "invalid_response"

                # Store result
                resultados = json.loads(sesion.resultados_json) if sesion.resultados_json else {}
                resultados[f"punto_{sesion.punto_actual}"] = {
                    "pregunta": punto.pregunta,
                    "respuesta": respuesta,
                    "tipo": punto.tipo_respuesta,
                    "bloque": punto.bloque_id,
                    "timestamp": self._utc_now_iso()
                }

                # Move to next point
                siguiente_punto = sesion.punto_actual + 1

                self.sheets.update_sesion(
                    id_sesion=sesion.id_sesion,
                    estado=sesion.estado,
                    timestamp_ultimo_punto=self._utc_now_iso(),
                    punto_actual=siguiente_punto,
                    hallazgos_json=sesion.hallazgos_json,
                    omitidos_json=sesion.omitidos_json,
                    resultados_json=json.dumps(resultados, ensure_ascii=False),
                )

                # Show next point or completion
                if siguiente_punto < len(todos_puntos):
                    siguiente = todos_puntos[siguiente_punto]
                    await meta_client.send_text(
                        payload.telefono,
                        f"✅ Registrado.\n\n{siguiente.pregunta}"
                    )
                else:
                    await meta_client.send_text(
                        payload.telefono,
                        "✅ ¡Auditoría completada!"
                    )

                return "response_stored"

            else:
                await meta_client.send_text(
                    payload.telefono,
                    f"📸 {punto.pregunta}\n\nEnvía una foto o responde: sí / no / problemas"
                )
                return "waiting_input"

        except Exception as e:
            logger.error(f"Error handling foto_si_no: {e}", exc_info=True)
            return "error"


    async def _handle_perfumeria_numero_audio(
        self,
        payload: WhatsAppPayload,
        punto: ChecklistPerfumeriaPunto,
        sesion: SesionAuditoria,
        todos_puntos: list,
        meta_client: MetaClient,
    ) -> str:
        """Handle stock quantities (number/audio) for perfumery audit."""
        try:
            contenido = ""

            # If audio, transcribe
            if payload.tipo == "audio" and payload.media_url:
                try:
                    contenido = await self.transcriber.transcribe_from_url(payload.media_url)
                except Exception as e:
                    logger.error(f"Error transcribing audio: {e}")
                    await meta_client.send_text(
                        payload.telefono,
                        "❌ Error transcribiendo audio. Intenta de nuevo."
                    )
                    return "transcription_error"
            elif payload.contenido:
                contenido = payload.contenido
            else:
                await meta_client.send_text(
                    payload.telefono,
                    f"🎤 {punto.pregunta}\n\nEnvía números, texto o un audio con las cantidades."
                )
                return "waiting_input"

            # Store result
            resultados = json.loads(sesion.resultados_json) if sesion.resultados_json else {}
            resultados[f"punto_{sesion.punto_actual}"] = {
                "pregunta": punto.pregunta,
                "respuesta": contenido,
                "tipo": punto.tipo_respuesta,
                "bloque": punto.bloque_id,
                "timestamp": self._utc_now_iso()
            }

            # Move to next point
            siguiente_punto = sesion.punto_actual + 1

            self.sheets.update_sesion(
                id_sesion=sesion.id_sesion,
                estado=sesion.estado,
                timestamp_ultimo_punto=self._utc_now_iso(),
                punto_actual=siguiente_punto,
                hallazgos_json=sesion.hallazgos_json,
                omitidos_json=sesion.omitidos_json,
                resultados_json=json.dumps(resultados, ensure_ascii=False),
            )

            # Show next point or completion
            if siguiente_punto < len(todos_puntos):
                siguiente = todos_puntos[siguiente_punto]
                await meta_client.send_text(
                    payload.telefono,
                    f"✅ Registrado.\n\n{siguiente.pregunta}"
                )
            else:
                await meta_client.send_text(
                    payload.telefono,
                    "✅ ¡Auditoría completada!"
                )

            return "response_stored"

        except Exception as e:
            logger.error(f"Error handling numero_audio: {e}", exc_info=True)
            return "error"


    async def _handle_perfumeria_lista_texto(
        self,
        payload: WhatsAppPayload,
        punto: ChecklistPerfumeriaPunto,
        sesion: SesionAuditoria,
        todos_puntos: list,
        meta_client: MetaClient,
    ) -> str:
        """Handle product list for perfumery audit."""
        try:
            contenido = ""

            # If image, try to extract text via OCR (simplified for now)
            if payload.tipo == "image" and payload.media_url:
                # TODO: Implement OCR for image-based lists
                await meta_client.send_text(
                    payload.telefono,
                    "📋 Recibí la foto. Por favor, envía una lista de texto con los productos separados por comas."
                )
                return "image_received_need_text"

            elif payload.contenido:
                contenido = payload.contenido
            else:
                await meta_client.send_text(
                    payload.telefono,
                    f"📋 {punto.pregunta}\n\nEnvía la lista separada por comas o líneas."
                )
                return "waiting_input"

            # Store result
            resultados = json.loads(sesion.resultados_json) if sesion.resultados_json else {}
            resultados[f"punto_{sesion.punto_actual}"] = {
                "pregunta": punto.pregunta,
                "respuesta": contenido,
                "tipo": punto.tipo_respuesta,
                "bloque": punto.bloque_id,
                "timestamp": self._utc_now_iso()
            }

            # Move to next point
            siguiente_punto = sesion.punto_actual + 1

            self.sheets.update_sesion(
                id_sesion=sesion.id_sesion,
                estado=sesion.estado,
                timestamp_ultimo_punto=self._utc_now_iso(),
                punto_actual=siguiente_punto,
                hallazgos_json=sesion.hallazgos_json,
                omitidos_json=sesion.omitidos_json,
                resultados_json=json.dumps(resultados, ensure_ascii=False),
            )

            # Show next point or completion
            if siguiente_punto < len(todos_puntos):
                siguiente = todos_puntos[siguiente_punto]
                await meta_client.send_text(
                    payload.telefono,
                    f"✅ Registrado.\n\n{siguiente.pregunta}"
                )
            else:
                await meta_client.send_text(
                    payload.telefono,
                    "✅ ¡Auditoría completada!"
                )

            return "response_stored"

        except Exception as e:
            logger.error(f"Error handling lista_texto: {e}", exc_info=True)
            return "error"


    async def _handle_perfumeria_si_no(
        self,
        payload: WhatsAppPayload,
        punto: ChecklistPerfumeriaPunto,
        sesion: SesionAuditoria,
        todos_puntos: list,
        meta_client: MetaClient,
    ) -> str:
        """Handle yes/no response for perfumery audit."""
        try:
            if not payload.contenido:
                await meta_client.send_text(
                    payload.telefono,
                    f"✅❌ {punto.pregunta}\n\nResponde: sí / no"
                )
                return "waiting_input"

            respuesta = payload.contenido.lower().strip()

            if respuesta not in {"sí", "si", "no"}:
                await meta_client.send_text(
                    payload.telefono,
                    "⚠️ Responde: sí / no"
                )
                return "invalid_response"

            # Store result
            resultados = json.loads(sesion.resultados_json) if sesion.resultados_json else {}
            resultados[f"punto_{sesion.punto_actual}"] = {
                "pregunta": punto.pregunta,
                "respuesta": respuesta,
                "tipo": punto.tipo_respuesta,
                "bloque": punto.bloque_id,
                "timestamp": self._utc_now_iso()
            }

            # Move to next point
            siguiente_punto = sesion.punto_actual + 1

            self.sheets.update_sesion(
                id_sesion=sesion.id_sesion,
                estado=sesion.estado,
                timestamp_ultimo_punto=self._utc_now_iso(),
                punto_actual=siguiente_punto,
                hallazgos_json=sesion.hallazgos_json,
                omitidos_json=sesion.omitidos_json,
                resultados_json=json.dumps(resultados, ensure_ascii=False),
            )

            # Show next point or completion
            if siguiente_punto < len(todos_puntos):
                siguiente = todos_puntos[siguiente_punto]
                await meta_client.send_text(
                    payload.telefono,
                    f"✅ Registrado.\n\n{siguiente.pregunta}"
                )
            else:
                await meta_client.send_text(
                    payload.telefono,
                    "✅ ¡Auditoría completada!"
                )

            return "response_stored"

        except Exception as e:
            logger.error(f"Error handling si_no: {e}", exc_info=True)
            return "error"


    async def _handle_perfumeria_observaciones(
        self,
        payload: WhatsAppPayload,
        punto: ChecklistPerfumeriaPunto,
        sesion: SesionAuditoria,
        todos_puntos: list,
        meta_client: MetaClient,
    ) -> str:
        """Handle free-form observations (text/audio/photo) for perfumery audit."""
        try:
            contenido = ""
            foto_url = None

            # Handle photo
            if payload.tipo == "image" and payload.media_url:
                try:
                    foto_url = await self.drive.upload_photo_from_url(
                        payload.media_url,
                        f"perf_obs_{sesion.id_sesion}_{uuid.uuid4().hex[:4]}.jpg"
                    )
                except Exception as e:
                    logger.error(f"Error uploading observation photo: {e}")

            # Handle audio
            elif payload.tipo == "audio" and payload.media_url:
                try:
                    contenido = await self.transcriber.transcribe_from_url(payload.media_url)
                except Exception as e:
                    logger.error(f"Error transcribing observation audio: {e}")
                    contenido = "[Audio no transcrito]"

            # Handle text
            elif payload.contenido:
                contenido = payload.contenido
            else:
                await meta_client.send_text(
                    payload.telefono,
                    f"📝 {punto.pregunta}\n\nPuedes enviar texto, audio o foto (opcional)."
                )
                return "waiting_input"

            # Store result
            resultados = json.loads(sesion.resultados_json) if sesion.resultados_json else {}
            resultados[f"punto_{sesion.punto_actual}"] = {
                "pregunta": punto.pregunta,
                "respuesta": contenido,
                "foto_url": foto_url,
                "tipo": punto.tipo_respuesta,
                "bloque": punto.bloque_id,
                "timestamp": self._utc_now_iso()
            }

            # Mark audit as complete (observaciones is the last block)
            self.sheets.update_sesion(
                id_sesion=sesion.id_sesion,
                estado="completa",
                timestamp_ultimo_punto=self._utc_now_iso(),
                punto_actual=sesion.punto_actual + 1,
                hallazgos_json=sesion.hallazgos_json,
                omitidos_json=sesion.omitidos_json,
                resultados_json=json.dumps(resultados, ensure_ascii=False),
            )

            self.sheets.update_conversacion(
                telefono=payload.telefono,
                estado=ConversationState.IDLE,
                id_pendiente="",
            )

            await meta_client.send_text(
                payload.telefono,
                "✅ ¡Auditoría completada!\n\nGracias por tu participación."
            )

            return "auditoria_completa"

        except Exception as e:
            logger.error(f"Error handling observaciones: {e}", exc_info=True)
            return "error"


    async def _handle_en_auditoria(

        self,

        payload: WhatsAppPayload,

        conv: Conversacion,

        meta_client: MetaClient,

    ) -> str:

        """Handle response during audit."""

        try:

            # Get active session

            sesion = self.sheets.get_sesion(conv.id_pendiente)

            if not sesion:

                await meta_client.send_text(

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

                    sesion.timestamp_ultimo_punto = self._utc_now_iso()

                    self.sheets.update_sesion(

                        id_sesion=sesion.id_sesion,

                        estado=sesion.estado,

                        timestamp_ultimo_punto=sesion.timestamp_ultimo_punto,

                        punto_actual=sesion.punto_actual,

                        hallazgos_json=sesion.hallazgos_json,

                        omitidos_json=sesion.omitidos_json,

                    )



                    # Check if finished

                    if sesion.punto_actual >= sesion.total_puntos:

                        return await self._cerrar_auditoria(sesion, meta_client, payload.telefono)



                    # Send next point

                    checklist = self.sheets.get_checklist()

                    await self._enviar_siguiente_punto(sesion, checklist, meta_client, payload.telefono)

                    return "punto_omitido"



                if cmd == "pausar":

                    sesion.estado = "pausada"

                    self.sheets.update_sesion(

                        id_sesion=sesion.id_sesion,

                        estado=sesion.estado,

                        timestamp_ultimo_punto=sesion.timestamp_ultimo_punto,

                        punto_actual=sesion.punto_actual,

                        hallazgos_json=sesion.hallazgos_json,

                        omitidos_json=sesion.omitidos_json,

                    )

                    self.sheets.update_conversacion(

                        telefono=payload.telefono,

                        estado=ConversationState.AUDITORIA_PAUSADA,

                        id_pendiente=conv.id_pendiente,

                    )

                    await meta_client.send_text(

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

                    await meta_client.send_text(

                        payload.telefono,

                        "❌ Error transcribiendo audio. Intenta de nuevo.",

                    )

                    return "transcription_error"



            if not respuesta:

                await meta_client.send_text(

                    payload.telefono,

                    "⚠️ Por favor envía audio, foto o texto con tu observación.",

                )

                return "empty_response"



            # Upload photo if present

            photo_url = None

            if payload.tipo == "image" and payload.media_url:

                try:

                    fecha = datetime.now().strftime("%Y%m%d")

                    checklist = self.sheets.get_checklist()

                    if sesion.punto_actual < len(checklist):

                        punto = checklist[sesion.punto_actual]

                        filename = f"{fecha}_{sesion.sucursal_id}_{punto.area.replace(' ','_')}_{punto.punto_orden}.jpg"

                        photo_url = await self.drive.upload_photo_from_url(

                            payload.media_url,

                            filename,

                        )

                except Exception as e:

                    logger.warning(f"Failed to upload photo: {e}")



            # Evaluate response

            checklist = self.sheets.get_checklist()



            # Check if punto_actual is valid

            if sesion.punto_actual >= len(checklist):

                logger.warning(f"punto_actual {sesion.punto_actual} exceeds checklist length {len(checklist)}")

                return await self._cerrar_auditoria(sesion, meta_client, payload.telefono)



            punto = checklist[sesion.punto_actual]

            eval_result = await self.parser.evaluate_punto_respuesta(punto, respuesta)



            if not eval_result:

                await meta_client.send_text(

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

                    await meta_client.send_text(sucursal.tel_responsable, msg)



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

            await meta_client.send_text(payload.telefono, eval_result.ok_message)



            # Advance to next point

            sesion.punto_actual += 1

            sesion.timestamp_ultimo_punto = self._utc_now_iso()

            self.sheets.update_sesion(

                id_sesion=sesion.id_sesion,

                estado=sesion.estado,

                timestamp_ultimo_punto=sesion.timestamp_ultimo_punto,

                punto_actual=sesion.punto_actual,

                hallazgos_json=sesion.hallazgos_json,

                omitidos_json=sesion.omitidos_json,

            )



            # Check if finished

            if sesion.punto_actual >= sesion.total_puntos:

                return await self._cerrar_auditoria(sesion, meta_client, payload.telefono)



            # Send next point

            checklist = self.sheets.get_checklist()

            await self._enviar_siguiente_punto(sesion, checklist, meta_client, payload.telefono)

            return "punto_evaluado"

        except Exception as e:

            logger.error(f"Error handling en_auditoria: {e}")

            await meta_client.send_text(

                payload.telefono,

                "❌ Error procesando respuesta.",

            )

            return "error"



    async def _handle_auditoria_pausada(

        self,

        payload: WhatsAppPayload,

        conv: Conversacion,

        meta_client: MetaClient,

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

                    await meta_client.send_text(

                        payload.telefono,

                        "❌ Sesión no encontrada.",

                    )

                    return "sesion_not_found"



                sesion.estado = "en_curso"

                sesion.timestamp_ultimo_punto = self._utc_now_iso()

                self.sheets.update_sesion(

                    id_sesion=sesion.id_sesion,

                    estado=sesion.estado,

                    timestamp_ultimo_punto=sesion.timestamp_ultimo_punto,

                    punto_actual=sesion.punto_actual,

                    hallazgos_json=sesion.hallazgos_json,

                    omitidos_json=sesion.omitidos_json,

                )



                self.sheets.update_conversacion(

                    telefono=payload.telefono,

                    estado=ConversationState.EN_AUDITORIA,

                    id_pendiente=conv.id_pendiente,

                )



                checklist = self.sheets.get_checklist()

                await self._enviar_siguiente_punto(sesion, checklist, meta_client, payload.telefono)

                return "auditoria_resumed"

            else:

                await meta_client.send_text(

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

        meta_client: MetaClient,

        phone: str,

    ) -> None:

        """Send next checklist point."""

        if sesion.punto_actual < len(checklist):

            punto = checklist[sesion.punto_actual]

            await meta_client.send_punto(

                phone,

                punto.punto_orden,

                sesion.total_puntos,

                punto.area,

                punto.descripcion,

            )



    async def _cerrar_auditoria(

        self,

        sesion: SesionAuditoria,

        meta_client: MetaClient,

        phone: str,

    ) -> str:

        """Close audit session and send summary."""

        try:

            sesion.estado = "completa"

            self.sheets.update_sesion(

                id_sesion=sesion.id_sesion,

                estado=sesion.estado,

                timestamp_ultimo_punto=sesion.timestamp_ultimo_punto,

                punto_actual=sesion.punto_actual,

                hallazgos_json=sesion.hallazgos_json,

                omitidos_json=sesion.omitidos_json,

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

            await meta_client.send_resumen_auditoria(

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

                await meta_client.send_text(settings.coordinador_tel, coord_msg)



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

        payload: WhatsAppPayload,

        conv: Conversacion,

        meta_client: MetaClient,

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

                    await meta_client.send_text(

                        payload.telefono,

                        "⏸️ Auditoría pausada. Mandá 'continuar' cuando estés listo.",

                    )

                    return "auditoria_pausada"



            # Get session

            sesion = self.sheets.get_sesion(conv.id_pendiente or "")

            if not sesion:

                await meta_client.send_text(payload.telefono, "❌ Sesión no encontrada")

                return "error"



            # Get block items

            bloques = self.sheets.get_checklist_bloques()

            bloque_id = sesion.bloque_actual

            if bloque_id not in bloques:

                await meta_client.send_text(payload.telefono, "❌ Bloque no encontrado")

                return "error"



            items = bloques[bloque_id]

            if await self._try_start_respuesta_collection(
                payload,
                sesion,
                bloque_id,
                ConversationState.EN_BLOQUE,
                meta_client,
            ):
                return "respuesta_collection_started"



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

                await meta_client.send_text(

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

            await meta_client.send_bloque_confirmacion(

                payload.telefono, bloque_id, f"Bloque {bloque_id}", items, resultados

            )



            return "bloque_respondido"

        except Exception as e:

            logger.error(f"Error in _handle_en_bloque: {e}", exc_info=True)

            return "error"



    async def _handle_confirmando_bloque(

        self,

        payload: WhatsAppPayload,

        conv: Conversacion,

        meta_client: MetaClient,

    ) -> str:

        """Handle block confirmation (SI/EDITAR/SALTAR)."""

        try:

            if payload.tipo != "text" or not payload.contenido:

                await meta_client.send_text(

                    payload.telefono,

                    """⚠️ Respondé una de estas:

1 o SI - Confirmar

2 o EDITAR - Cambios

3 o SALTAR - Saltar""",

                )

                return "invalid_response"



            respuesta = payload.contenido.upper().strip()



            # Normalize response: accept shortcuts like "1", "S", "E", etc.

            respuesta_map = {

                "1": "SI", "S": "SI", "Y": "SI",

                "2": "EDITAR", "E": "EDITAR",

                "3": "SALTAR", "SALTAR": "SALTAR BLOQUE",

            }

            respuesta = respuesta_map.get(respuesta, respuesta)



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

                                await meta_client.send_alerta_coordinador(

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

                    await meta_client.send_text(

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

                        await meta_client.send_bloque_prompt(

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

                    await meta_client.send_bloque_prompt(

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

                    await meta_client.send_text(

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

                        await meta_client.send_bloque_prompt(

                            payload.telefono, next_state, f"Bloque {next_state}",

                            bloques[next_state]

                        )



                return "bloque_saltado"



            else:

                await meta_client.send_text(

                    payload.telefono,

                    """⚠️ Respondé una de estas:

1 o SI - Confirmar

2 o EDITAR - Cambios

3 o SALTAR - Saltar""",

                )

                return "invalid_response"



        except Exception as e:

            logger.error(f"Error in _handle_confirmando_bloque: {e}", exc_info=True)

            return "error"



    async def _handle_stock_loop(

        self,

        payload: WhatsAppPayload,

        conv: Conversacion,

        meta_client: MetaClient,

    ) -> str:

        """Handle stock verification count input."""

        try:

            if payload.tipo != "text" or not payload.contenido:

                await meta_client.send_text(payload.telefono, "⚠️ Mandá un número o 0 para saltar")

                return "invalid_response"



            try:

                cantidad = int(payload.contenido.strip())

            except ValueError:

                await meta_client.send_text(payload.telefono, "⚠️ Mandá un número válido")

                return "invalid_response"



            sesion = self.sheets.get_sesion(conv.id_pendiente or "")

            if not sesion:

                return "error"



            if cantidad == 0:

                self.sheets.update_conversacion(

                    telefono=payload.telefono,

                    estado=ConversationState.DESVIO_LIBRE,

                    id_pendiente=sesion.id_sesion,

                )

                sesion.stock_total = 0

                sesion.stock_actual = 0

                self.sheets.update_sesion(

                    sesion.id_sesion,

                    estado=ConversationState.DESVIO_LIBRE.value,

                    timestamp_ultimo_punto=datetime.utcnow().isoformat(),

                    stock_total=0,

                    stock_actual=0,

                    stock_items_json=sesion.stock_items_json,

                    desvios_libres_json=sesion.desvios_libres_json,

                    bloque_actual=sesion.bloque_actual,

                    resultados_json=sesion.resultados_json,

                    punto_actual=sesion.punto_actual,

                    hallazgos_json=sesion.hallazgos_json,

                    omitidos_json=sesion.omitidos_json,

                )

                await meta_client.send_text(

                    payload.telefono,

                    "📋 Desvíos Libres\n\nTiene algún desvío o hallazgo libre para reportar?\n\nMandá 'NO' si no hay más desvíos, o describí el problema.",

                )

                return "stock_skipped"



            sesion.stock_total = cantidad

            sesion.stock_actual = 0

            self.sheets.update_conversacion(

                telefono=payload.telefono,

                estado=ConversationState.EN_STOCK_ITEM,

                id_pendiente=sesion.id_sesion,

            )

            self.sheets.update_sesion(

                sesion.id_sesion,

                estado=ConversationState.EN_STOCK_ITEM.value,

                timestamp_ultimo_punto=datetime.utcnow().isoformat(),

                stock_total=cantidad,

                stock_actual=0,

                stock_items_json=sesion.stock_items_json,

                desvios_libres_json=sesion.desvios_libres_json,

                bloque_actual=sesion.bloque_actual,

                resultados_json=sesion.resultados_json,

                punto_actual=sesion.punto_actual,

                hallazgos_json=sesion.hallazgos_json,

                omitidos_json=sesion.omitidos_json,

            )

            await meta_client.send_text(

                payload.telefono,

                f"📦 Producto 1/{cantidad}\n\nMandá: Nombre / Stock Físico / Stock Sistema\n\nEj: Ibuprofeno 400 / 23 / 18",

            )

            return "stock_started"

        except Exception as e:

            logger.error(f"Error in _handle_stock_loop: {e}", exc_info=True)

            return "error"



    async def _handle_en_stock_item(

        self,

        payload: WhatsAppPayload,

        conv: Conversacion,

        meta_client: MetaClient,

    ) -> str:

        """Handle stock item entry."""

        try:

            if payload.tipo != "text" or not payload.contenido:

                await meta_client.send_text(

                    payload.telefono,

                    "⚠️ Mandá el formato: Nombre / Stock Físico / Stock Sistema",

                )

                return "invalid_response"



            sesion = self.sheets.get_sesion(conv.id_pendiente or "")

            if not sesion:

                return "error"



            comando = payload.contenido.strip().lower()

            if comando in {"listo", "terminado", "terminé", "fin", "finalizar"}:

                self.sheets.update_conversacion(

                    telefono=payload.telefono,

                    estado=ConversationState.DESVIO_LIBRE,

                    id_pendiente=sesion.id_sesion,

                )

                self.sheets.update_sesion(

                    sesion.id_sesion,

                    estado=ConversationState.DESVIO_LIBRE.value,

                    timestamp_ultimo_punto=datetime.utcnow().isoformat(),

                    stock_total=sesion.stock_total,

                    stock_actual=sesion.stock_actual,

                    stock_items_json=sesion.stock_items_json,

                    desvios_libres_json=sesion.desvios_libres_json,

                    bloque_actual=sesion.bloque_actual,

                    resultados_json=sesion.resultados_json,

                    punto_actual=sesion.punto_actual,

                    hallazgos_json=sesion.hallazgos_json,

                    omitidos_json=sesion.omitidos_json,

                )

                await meta_client.send_text(

                    payload.telefono,

                    f"✓ Stock registrado: {sesion.stock_actual}/{sesion.stock_total}\n\n¿Algo más para registrar que no hayamos cubierto?\nPodés mandar texto, audio o foto. O escribí NO para terminar.",

                )

                return "stock_closed"



            stock_item = await self.parser.parse_stock_item(payload.contenido)

            if not stock_item:

                await meta_client.send_text(

                    payload.telefono,

                    "❌ No pude entender el formato. Intenta: Nombre / Físico / Sistema",

                )

                return "parse_error"



            auditor = self.sheets.get_auditor(payload.telefono)

            auditor_nombre = auditor.nombre if auditor else "Auditor"

            self.sheets.save_stock_item(

                sesion.id_sesion,

                sesion.sucursal_id,

                auditor_nombre,

                stock_item,

            )



            stock_items = json.loads(sesion.stock_items_json) if sesion.stock_items_json else []

            stock_items.append(vars(stock_item))

            sesion.stock_items_json = json.dumps(stock_items, ensure_ascii=False)

            sesion.stock_actual = min(sesion.stock_actual + 1, sesion.stock_total or (sesion.stock_actual + 1))



            if sesion.stock_total and sesion.stock_actual >= sesion.stock_total:

                self.sheets.update_conversacion(

                    telefono=payload.telefono,

                    estado=ConversationState.DESVIO_LIBRE,

                    id_pendiente=sesion.id_sesion,

                )

                self.sheets.update_sesion(

                    sesion.id_sesion,

                    estado=ConversationState.DESVIO_LIBRE.value,

                    timestamp_ultimo_punto=datetime.utcnow().isoformat(),

                    stock_total=sesion.stock_total,

                    stock_actual=sesion.stock_actual,

                    stock_items_json=sesion.stock_items_json,

                    desvios_libres_json=sesion.desvios_libres_json,

                    bloque_actual=sesion.bloque_actual,

                    resultados_json=sesion.resultados_json,

                    punto_actual=sesion.punto_actual,

                    hallazgos_json=sesion.hallazgos_json,

                    omitidos_json=sesion.omitidos_json,

                )

                await meta_client.send_text(

                    payload.telefono,

                    f"✓ Registrado: {stock_item.nombre}\n\nStock completo ({sesion.stock_actual}/{sesion.stock_total}).\n¿Algo más para registrar que no hayamos cubierto?\nPodés mandar texto, audio o foto. O escribí NO para terminar.",

                )

                return "stock_completed"



            self.sheets.update_sesion(

                sesion.id_sesion,

                estado=ConversationState.EN_STOCK_ITEM.value,

                timestamp_ultimo_punto=datetime.utcnow().isoformat(),

                stock_total=sesion.stock_total,

                stock_actual=sesion.stock_actual,

                stock_items_json=sesion.stock_items_json,

                desvios_libres_json=sesion.desvios_libres_json,

            )



            await meta_client.send_text(

                payload.telefono,

                f"✓ Registrado: {stock_item.nombre} ({sesion.stock_actual}/{sesion.stock_total})\n\nMandá el próximo producto o 'listo'",

            )

            return "stock_item_guardado"

        except Exception as e:

            logger.error(f"Error in _handle_en_stock_item: {e}", exc_info=True)

            return "error"



    async def _handle_desvio_libre(

        self,

        payload: WhatsAppPayload,

        conv: Conversacion,

        meta_client: MetaClient,

    ) -> str:

        """Handle free-form deviations."""

        try:

            if payload.tipo != "text" or not payload.contenido:

                await meta_client.send_text(

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

                self.sheets.update_sesion(

                    sesion.id_sesion,

                    estado=ConversationState.COMPROMISOS.value,

                    timestamp_ultimo_punto=datetime.utcnow().isoformat(),

                    stock_total=sesion.stock_total,

                    stock_actual=sesion.stock_actual,

                    stock_items_json=sesion.stock_items_json,

                    desvios_libres_json=sesion.desvios_libres_json,

                    bloque_actual=sesion.bloque_actual,

                    resultados_json=sesion.resultados_json,

                    punto_actual=sesion.punto_actual,

                    hallazgos_json=sesion.hallazgos_json,

                    omitidos_json=sesion.omitidos_json,

                )

                await meta_client.send_text(

                    payload.telefono,

                    "📝 Compromisos\n\n¿Firmaron compromisos de corrección?\n\nSI / NO / PENDIENTE",

                )

                return "sin_desvios"



            # Parse free deviation

            desvio = await self.parser.parse_desvio_libre(payload.contenido)

            if not desvio:

                await meta_client.send_text(

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

                    await meta_client.send_alerta_coordinador(

                        settings.coordinador_tel,

                        sucursal_nombre,

                        desvio.area_estimada,

                        desvio.descripcion,

                        "Alta",

                    )



            await meta_client.send_text(

                payload.telefono,

                f"✓ Registrado desvío en {desvio.area_estimada}\n\n¿Hay más desvíos? Describí o mandá 'NO'",

            )



            return "desvio_registrado"



        except Exception as e:

            logger.error(f"Error in _handle_desvio_libre: {e}", exc_info=True)

            return "error"



    async def _handle_compromisos(

        self,

        payload: WhatsAppPayload,

        conv: Conversacion,

        meta_client: MetaClient,

    ) -> str:

        """Handle compromise commitments (SI/NO/PENDIENTE)."""

        try:

            if payload.tipo != "text" or not payload.contenido:

                await meta_client.send_text(

                    payload.telefono,

                    "⚠️ Respondé SI, NO o PENDIENTE",

                )

                return "invalid_response"



            respuesta = payload.contenido.upper().strip()

            if respuesta not in {"SI", "SÍ", "NO", "PENDIENTE"}:

                await meta_client.send_text(

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

            await self._cerrar_auditoria_bloques(sesion, meta_client, payload.telefono)



            return "compromisos_registrados"



        except Exception as e:

            logger.error(f"Error in _handle_compromisos: {e}", exc_info=True)

            return "error"



    async def _cerrar_auditoria_bloques(

        self,

        sesion: SesionAuditoria,

        meta_client: MetaClient,

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



            await meta_client.send_resumen_final(

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

                await meta_client.send_text(settings.coordinador_tel, coord_msg)



            # Reset conversation

            self.sheets.update_conversacion(

                telefono=phone,

                estado=ConversationState.IDLE,

            )



        except Exception as e:

            logger.error(f"Error closing block audit: {e}", exc_info=True)




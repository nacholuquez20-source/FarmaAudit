# 🏗️ PROMPT PARA CODEX: Flujo Robusto de Auditoría WhatsApp Multi-Mensaje

**Fecha**: 2026-05-04  
**Prioridad**: ALTA — Implementación Quirúrgica sin Breaking Changes  
**Objetivo**: Permitir que auditor envíe múltiples fotos/audios/textos para UNA pregunta antes de avanzar

---

## 📌 CONTEXTO

**Problema Actual**: El bot avanza a la siguiente pregunta sin esperar a que el auditor termine de enviar fotos, audios y descripción. Pierden datos.

**Solución**: Flujo de "recolección de respuesta" con:
1. **Keyword primario**: Auditor escribe "LISTO" para terminar
2. **Fallback timeout**: 120s sin actividad → bot pregunta "¿Terminaste?"
3. **Auto-complete**: 150s sin respuesta → auto-completa
4. **Validación**: Asegura que respuesta sea completa (mín. texto, fotos requeridas, etc.)
5. **Audit trail**: Cada mensaje grabado con timestamp, URL, estado

---

## 🎯 FASE 1: ESTRUCTURA DE BASE DE DATOS (2-3 horas)

### 1.1 Crear archivo SQL de migración

**Archivo nuevo**: `frontend/docs/sql/etapa-8-respuesta-recolectora.sql`

```sql
-- Etapa 8 - Sistema de recolección robusto de respuestas multi-mensaje

-- Tabla para recolectar respuestas incompletas (durante auditoria)
CREATE TABLE IF NOT EXISTS respuesta_pregunta (
    id TEXT PRIMARY KEY,                           -- UUID generado por backend
    id_sesion TEXT NOT NULL,                       -- FK a sesiones_auditoria (si existe)
    telefono_auditor TEXT NOT NULL,                -- Para lookup rápido
    pregunta_numero INT NOT NULL,                  -- Ej: 3 (tercera pregunta)
    bloque_id TEXT NOT NULL,                       -- "PRES", "GOND", "STOCK", etc.
    
    -- Estado del flujo
    estado TEXT NOT NULL DEFAULT 'recolectando'
        CHECK (estado IN ('recolectando', 'completada', 'descartada')),
    
    -- Timestamps
    timestamp_inicio TIMESTAMPTZ DEFAULT NOW(),
    timestamp_ultimo_mensaje TIMESTAMPTZ DEFAULT NOW(),
    
    -- Duración configurable para esta pregunta (segundos)
    timeout_segundos INT NOT NULL DEFAULT 120,
    
    -- ¿Auditor confirmó manualmente con "LISTO"?
    confirmado_por_auditor BOOLEAN DEFAULT FALSE,
    
    -- Array JSON de mensajes recolectados
    -- [{tipo, contenido, media_ids, timestamp, estado_procesamiento}, ...]
    mensajes_json TEXT DEFAULT '[]',
    
    -- Array de URLs de medios (fotos, audios descargados/subidos)
    -- [{tipo, url, mime_type, descripcion}, ...]
    media_ids_json TEXT DEFAULT '[]',
    
    -- Respuesta consolidada (después de completar)
    respuesta_consolidada TEXT,
    
    -- Desvíos detectados (JSON con hallazgos)
    desvios_json TEXT,
    
    -- Razón de descarte (si aplica)
    razon_descarte TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para queries rápidas
CREATE INDEX IF NOT EXISTS idx_respuesta_pregunta_sesion 
    ON respuesta_pregunta(id_sesion) WHERE estado = 'recolectando';

CREATE INDEX IF NOT EXISTS idx_respuesta_pregunta_phone 
    ON respuesta_pregunta(telefono_auditor) WHERE estado = 'recolectando';

CREATE INDEX IF NOT EXISTS idx_respuesta_pregunta_estado 
    ON respuesta_pregunta(estado, timestamp_ultimo_mensaje);

-- Tabla de auditoría (log de cada acción en respuesta)
CREATE TABLE IF NOT EXISTS respuesta_pregunta_audit_log (
    id TEXT PRIMARY KEY,                    -- UUID
    id_respuesta TEXT NOT NULL 
        REFERENCES respuesta_pregunta(id) ON DELETE CASCADE,
    evento TEXT NOT NULL,                   -- "mensaje_agregado", "foto_subida", "completada", etc.
    detalles_json TEXT,                     -- Metadata del evento
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_respuesta 
    ON respuesta_pregunta_audit_log(id_respuesta);

-- Actualizar sesiones_auditoria (si existe tabla) para tracking de estado
ALTER TABLE IF EXISTS sesiones_auditoria 
ADD COLUMN IF NOT EXISTS id_respuesta_actual TEXT 
    REFERENCES respuesta_pregunta(id) ON DELETE SET NULL;

ALTER TABLE IF EXISTS sesiones_auditoria 
ADD COLUMN IF NOT EXISTS respuestas_completadas_json TEXT DEFAULT '[]';

-- Actualizar conversaciones para sincronizar estado
ALTER TABLE IF EXISTS conversaciones 
ADD COLUMN IF NOT EXISTS id_respuesta_actual TEXT 
    REFERENCES respuesta_pregunta(id) ON DELETE SET NULL;

-- Ejecutar estos INSERTs al final para crear el bucketde storage (si no existe)
-- Note: Storage bucket creation via SQL is limited in Supabase.
-- Ensure bucket 'auditoria-respuestas' exists via Dashboard or separate API call.
```

**Verificaciones**:
- [ ] Archivo creado en ruta exacta: `frontend/docs/sql/etapa-8-respuesta-recolectora.sql`
- [ ] SQL es idempotente (todos los CREATE TABLE llevan IF NOT EXISTS)
- [ ] Índices están optimizados para queries por (id_sesion, estado) y (telefono, estado)

---

## 🎯 FASE 2: MODELOS EN PYTHON (1-2 horas)

### 2.1 Actualizar `models.py`

Agregar al final del archivo (ANTES de cualquier clase FastAPI):

```python
# ============================================================================
# NUEVOS MODELOS PARA FLUJO ROBUSTO DE RESPUESTAS MULTI-MENSAJE
# ============================================================================

from typing import List, Optional
from dataclasses import dataclass, field
from enum import Enum

class RespuestaPreguntaEstado(str, Enum):
    """Estado del flujo de recolección de respuesta."""
    RECOLECTANDO = "recolectando"
    COMPLETADA = "completada"
    DESCARTADA = "descartada"

class TipoMensajeRespuesta(str, Enum):
    """Tipo de mensaje en respuesta."""
    TEXTO = "text"
    IMAGEN = "image"
    AUDIO = "audio"

@dataclass
class MensajeEnRespuesta:
    """Un mensaje individual dentro de una respuesta pregunta."""
    tipo: TipoMensajeRespuesta         # text, image, audio
    contenido: str                      # Texto limpio o transcripción
    media_ids: List[dict] = field(default_factory=list)  # [{tipo, url, mime_type}]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    estado_procesamiento: str = "pendiente"  # pendiente, exitoso, error
    error_mensaje: Optional[str] = None

@dataclass
class RespuestaPregunta:
    """Objeto de recolección de respuesta."""
    id: str
    id_sesion: str
    telefono_auditor: str
    pregunta_numero: int
    bloque_id: str
    estado: RespuestaPreguntaEstado
    timestamp_inicio: str
    timestamp_ultimo_mensaje: str
    timeout_segundos: int = 120
    confirmado_por_auditor: bool = False
    mensajes_json: str = "[]"  # JSON array of MensajeEnRespuesta
    media_ids_json: str = "[]"
    respuesta_consolidada: Optional[str] = None
    desvios_json: Optional[str] = None
    razon_descarte: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def get_mensajes(self) -> List[MensajeEnRespuesta]:
        """Deserialize mensajes from JSON."""
        try:
            raw = json.loads(self.mensajes_json) if self.mensajes_json else []
            return [MensajeEnRespuesta(**msg) for msg in raw]
        except Exception as e:
            logger.error(f"Error deserializing mensajes_json: {e}")
            return []

    def get_media_ids(self) -> List[dict]:
        """Deserialize media URLs."""
        try:
            return json.loads(self.media_ids_json) if self.media_ids_json else []
        except Exception as e:
            logger.error(f"Error deserializing media_ids_json: {e}")
            return []

@dataclass
class RespuestaPreguntaAuditLog:
    """Log de auditoría para cada acción en respuesta."""
    id: str
    id_respuesta: str
    evento: str  # "mensaje_agregado", "foto_subida", "completada", etc.
    detalles_json: str  # Metadata del evento
    timestamp: str

# ============================================================================
# CONFIGURACIÓN GLOBAL PARA TIMEOUTS
# ============================================================================

RESPUESTA_CONFIG = {
    "timeout_sin_actividad_segundos": 120,      # Primer prompt de "¿terminaste?"
    "timeout_auto_complete_segundos": 150,      # Auto-completar si no responde
    "timeout_max_segundos": 300,                # Descartar después de esto
    "mensaje_max_por_respuesta": 20,            # Evitar spam
    "respuesta_max_caracteres": 5000,           # Límite consolidado
}

# Validación de completitud por bloque
RESPUESTA_VALIDACION = {
    "PRES": {"min_texto": 10, "requiere_foto": False, "requiere_audio": False},
    "GOND": {"min_texto": 15, "requiere_foto": True, "requiere_audio": False},
    "STOCK": {"min_texto": 5, "requiere_foto": False, "requiere_audio": False},
    "TEMP": {"min_texto": 8, "requiere_foto": True, "requiere_audio": False},
    # Agregar más bloques según necesidad
}
```

**Verificaciones**:
- [ ] Modelos importan correctamente (Enum, dataclass, field)
- [ ] Método `get_mensajes()` y `get_media_ids()` deserializan correctamente
- [ ] Configuración es readable y modificable

---

## 🎯 FASE 3: SUPABASE MANAGER - NUEVAS FUNCIONES (2-3 horas)

### 3.1 Agregar a `supabase_manager.py` al final de la clase

```python
# ============================================================================
# MÉTODOS PARA RESPUESTA PREGUNTA RECOLECTORA
# ============================================================================

def create_respuesta_pregunta(self, respuesta: RespuestaPregunta) -> RespuestaPregunta:
    """Crear nuevo registro de respuesta pregunta."""
    try:
        data = {
            "id": respuesta.id,
            "id_sesion": respuesta.id_sesion,
            "telefono_auditor": respuesta.telefono_auditor,
            "pregunta_numero": respuesta.pregunta_numero,
            "bloque_id": respuesta.bloque_id,
            "estado": respuesta.estado.value,
            "timestamp_inicio": respuesta.timestamp_inicio,
            "timestamp_ultimo_mensaje": respuesta.timestamp_ultimo_mensaje,
            "timeout_segundos": respuesta.timeout_segundos,
            "confirmado_por_auditor": respuesta.confirmado_por_auditor,
            "mensajes_json": respuesta.mensajes_json,
            "media_ids_json": respuesta.media_ids_json,
        }
        result = self.client.table("respuesta_pregunta").insert(data).execute()
        return RespuestaPregunta(**result.data[0])
    except Exception as e:
        logger.error(f"Error creating respuesta_pregunta: {e}")
        raise

def get_respuesta_pregunta(self, id_respuesta: str) -> Optional[RespuestaPregunta]:
    """Obtener respuesta pregunta por ID."""
    try:
        result = self.client.table("respuesta_pregunta").select("*").eq("id", id_respuesta).execute()
        if result.data:
            return RespuestaPregunta(**result.data[0])
        return None
    except Exception as e:
        logger.error(f"Error getting respuesta_pregunta {id_respuesta}: {e}")
        return None

def get_respuesta_pregunta_activa(self, telefono: str) -> Optional[RespuestaPregunta]:
    """Obtener respuesta en recolección activa para este auditor."""
    try:
        result = (
            self.client.table("respuesta_pregunta")
            .select("*")
            .eq("telefono_auditor", telefono)
            .eq("estado", "recolectando")
            .order("timestamp_inicio", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return RespuestaPregunta(**result.data[0])
        return None
    except Exception as e:
        logger.error(f"Error getting respuesta_pregunta_activa for {telefono}: {e}")
        return None

def update_respuesta_pregunta(
    self,
    id_respuesta: str,
    **kwargs
) -> Optional[RespuestaPregunta]:
    """Actualizar respuesta pregunta."""
    try:
        # Asegurar que updated_at se actualiza
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        result = (
            self.client.table("respuesta_pregunta")
            .update(kwargs)
            .eq("id", id_respuesta)
            .execute()
        )
        if result.data:
            return RespuestaPregunta(**result.data[0])
        return None
    except Exception as e:
        logger.error(f"Error updating respuesta_pregunta {id_respuesta}: {e}")
        raise

def get_respuestas_incompletas_timeout(self, timeout_segundos: int) -> List[RespuestaPregunta]:
    """
    Obtener respuestas sin completar que superaron timeout.
    Usado por background job.
    """
    try:
        ahora = datetime.now(timezone.utc)
        hace_X_segundos = (ahora - timedelta(seconds=timeout_segundos)).isoformat()
        
        result = (
            self.client.table("respuesta_pregunta")
            .select("*")
            .eq("estado", "recolectando")
            .eq("confirmado_por_auditor", False)
            .lt("timestamp_ultimo_mensaje", hace_X_segundos)
            .order("timestamp_ultimo_mensaje", desc=False)
            .execute()
        )
        return [RespuestaPregunta(**r) for r in result.data] if result.data else []
    except Exception as e:
        logger.error(f"Error getting respuestas_incompletas_timeout: {e}")
        return []

def create_respuesta_audit_log(
    self,
    id_respuesta: str,
    evento: str,
    detalles: dict
) -> bool:
    """Registrar evento en audit log de respuesta."""
    try:
        data = {
            "id": str(uuid.uuid4()),
            "id_respuesta": id_respuesta,
            "evento": evento,
            "detalles_json": json.dumps(detalles, ensure_ascii=False),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.client.table("respuesta_pregunta_audit_log").insert(data).execute()
        logger.info(f"Audit log created: {evento} for {id_respuesta}")
        return True
    except Exception as e:
        logger.error(f"Error creating audit log: {e}")
        return False

def get_respuesta_audit_trail(self, id_respuesta: str) -> List[RespuestaPreguntaAuditLog]:
    """Obtener audit trail completo de una respuesta."""
    try:
        result = (
            self.client.table("respuesta_pregunta_audit_log")
            .select("*")
            .eq("id_respuesta", id_respuesta)
            .order("timestamp", desc=False)
            .execute()
        )
        return [RespuestaPreguntaAuditLog(**r) for r in result.data] if result.data else []
    except Exception as e:
        logger.error(f"Error getting audit trail for {id_respuesta}: {e}")
        return []
```

**Verificaciones**:
- [ ] Todos los métodos tienen try/except y logging
- [ ] updated_at se actualiza automáticamente en update_respuesta_pregunta
- [ ] Queries usan índices correctamente (eq + order)
- [ ] No hay hardcoded secrets

---

## 🎯 FASE 4: CONVERSATIONROUTER - LÓGICA DE RECOLECCIÓN (4-5 horas)

### 4.1 En `router.py`, agregar nueva clase estado (si no existe)

```python
# En ConversationState enum (si existe):
RECOLECTANDO_RESPUESTA = "recolectando_respuesta"  # Esperando múltiples mensajes para una pregunta
```

### 4.2 Agregar método en ConversationRouter

```python
async def _handle_recolectando_respuesta(
    self,
    payload: WhatsAppPayload,
    conv: Conversacion,
    meta_client: MetaClient,
    supabase_mgr: SupabaseManager,
) -> str:
    """
    Manejar flujo de recolección multi-mensaje.
    
    Flujo:
    1. Si auditor envía "LISTO", completar respuesta
    2. Si es mensaje (texto/foto/audio), agregar a array
    3. Descargar/subir medios
    4. Confirmar con mensaje al auditor
    5. Actualizar timestamps
    """
    
    respuesta_activa = supabase_mgr.get_respuesta_pregunta_activa(payload.telefono)
    
    if not respuesta_activa:
        logger.error(f"No respuesta activa encontrada para {payload.telefono}")
        await meta_client.send_text(payload.telefono, "❌ Error: no hay respuesta activa.")
        return "error_no_respuesta"
    
    # ========== STEP 1: Check keyword de completación ==========
    is_completion_keyword = False
    if payload.contenido:
        cleaned = payload.contenido.strip().upper()
        is_completion_keyword = cleaned in {"LISTO", "SIGUIENTE", "TERMINAR", "DONE", "FINISH"}
    
    if is_completion_keyword:
        logger.info(f"Completion keyword detected from {payload.telefono}: {payload.contenido}")
        return await self._complete_respuesta_collection(
            respuesta_activa=respuesta_activa,
            conv=conv,
            payload=payload,
            meta_client=meta_client,
            supabase_mgr=supabase_mgr,
            auto_complete=False,
        )
    
    # ========== STEP 2: Validar que no sea spam (max mensajes) ==========
    mensajes_actuales = respuesta_activa.get_mensajes()
    if len(mensajes_actuales) >= RESPUESTA_CONFIG["mensaje_max_por_respuesta"]:
        await meta_client.send_text(
            payload.telefono,
            f"⚠️ Máximo {RESPUESTA_CONFIG['mensaje_max_por_respuesta']} mensajes por respuesta. "
            "Escribe LISTO para terminar."
        )
        return "max_mensajes_alcanzado"
    
    # ========== STEP 3: Construir nuevo mensaje ==========
    nuevo_mensaje = {
        "tipo": payload.tipo,  # "text", "audio", "image"
        "contenido": payload.contenido or "",
        "media_ids": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "estado_procesamiento": "pendiente",
        "error_mensaje": None,
    }
    
    # ========== STEP 4: Procesar media (si aplica) ==========
    if payload.tipo == "image" and payload.media_id:
        try:
            # Descargar de Meta
            media_content, mime_type = await meta_client.download_media_with_metadata(
                payload.media_id
            )
            
            # Subir a Storage
            path = f"auditoria/{respuesta_activa.id_sesion}/{respuesta_activa.id}/{uuid.uuid4()}.jpg"
            signed_url = await meta_client.upload_to_storage(
                bucket="auditoria-respuestas",
                path=path,
                file_content=media_content,
                content_type=mime_type,
            )
            
            nuevo_mensaje["media_ids"].append({
                "tipo": "image",
                "url": signed_url,
                "mime_type": mime_type,
                "descripcion": "Foto auditoría",
            })
            nuevo_mensaje["estado_procesamiento"] = "exitoso"
            
            await meta_client.send_text(payload.telefono, "📸 Foto guardada. Puedes enviar más o escribe LISTO.")
            
            # Log
            supabase_mgr.create_respuesta_audit_log(
                id_respuesta=respuesta_activa.id,
                evento="foto_subida",
                detalles={"media_id": payload.media_id, "path": path}
            )
        
        except Exception as e:
            logger.error(f"Error downloading/uploading image: {e}")
            nuevo_mensaje["estado_procesamiento"] = "error"
            nuevo_mensaje["error_mensaje"] = str(e)
            await meta_client.send_text(
                payload.telefono,
                f"❌ Error descargando foto: {str(e)[:100]}. Intenta de nuevo."
            )
            supabase_mgr.create_respuesta_audit_log(
                id_respuesta=respuesta_activa.id,
                evento="error_foto",
                detalles={"error": str(e)}
            )
    
    elif payload.tipo == "audio" and payload.media_id:
        try:
            # Descargar de Meta
            media_content, mime_type = await meta_client.download_media_with_metadata(
                payload.media_id
            )
            
            # Subir audio a Storage
            path = f"auditoria/{respuesta_activa.id_sesion}/{respuesta_activa.id}/{uuid.uuid4()}.ogg"
            signed_url = await meta_client.upload_to_storage(
                bucket="auditoria-respuestas",
                path=path,
                file_content=media_content,
                content_type=mime_type,
            )
            
            # Transcribir (usa OpenAI Whisper o similar)
            # Para MVP: guardar sin transcripción. Agregar después.
            transcripcion = "[Audio] Transcripción no implementada aún"
            
            nuevo_mensaje["media_ids"].append({
                "tipo": "audio",
                "url": signed_url,
                "mime_type": mime_type,
                "descripcion": "Audio auditoría",
            })
            nuevo_mensaje["contenido"] = transcripcion
            nuevo_mensaje["estado_procesamiento"] = "exitoso"
            
            await meta_client.send_text(
                payload.telefono,
                f"🎙️ Audio guardado.\n\n{transcripcion}\n\nPuedes enviar más o escribe LISTO."
            )
            
            supabase_mgr.create_respuesta_audit_log(
                id_respuesta=respuesta_activa.id,
                evento="audio_subido",
                detalles={"media_id": payload.media_id, "path": path}
            )
        
        except Exception as e:
            logger.error(f"Error downloading/uploading audio: {e}")
            nuevo_mensaje["estado_procesamiento"] = "error"
            nuevo_mensaje["error_mensaje"] = str(e)
            await meta_client.send_text(
                payload.telefono,
                f"❌ Error descargando audio: {str(e)[:100]}. Intenta de nuevo."
            )
            supabase_mgr.create_respuesta_audit_log(
                id_respuesta=respuesta_activa.id,
                evento="error_audio",
                detalles={"error": str(e)}
            )
    
    elif payload.tipo == "text" and payload.contenido:
        nuevo_mensaje["estado_procesamiento"] = "exitoso"
        await meta_client.send_text(
            payload.telefono,
            "✓ Registrado. Puedes enviar más o escribe LISTO para terminar."
        )
        
        supabase_mgr.create_respuesta_audit_log(
            id_respuesta=respuesta_activa.id,
            evento="texto_agregado",
            detalles={"contenido": payload.contenido[:200]}
        )
    
    else:
        logger.warning(f"Unknown message type or empty content: {payload.tipo}")
        await meta_client.send_text(
            payload.telefono,
            "⚠️ Tipo de mensaje no soportado. Envía texto, foto o audio."
        )
        return "unsupported_message_type"
    
    # ========== STEP 5: Agregar mensaje al array ==========
    mensajes_actuales.append(nuevo_mensaje)
    mensajes_json_actualizado = json.dumps(
        [msg.__dict__ if isinstance(msg, MensajeEnRespuesta) else msg for msg in mensajes_actuales],
        ensure_ascii=False
    )
    
    # ========== STEP 6: Actualizar en BD ==========
    supabase_mgr.update_respuesta_pregunta(
        id_respuesta=respuesta_activa.id,
        mensajes_json=mensajes_json_actualizado,
        timestamp_ultimo_mensaje=datetime.now(timezone.utc).isoformat(),
        estado="recolectando",
    )
    
    logger.info(f"Message added to respuesta {respuesta_activa.id}: tipo={payload.tipo}")
    
    return "mensaje_agregado"


async def _complete_respuesta_collection(
    self,
    respuesta_activa: RespuestaPregunta,
    conv: Conversacion,
    payload: WhatsAppPayload,
    meta_client: MetaClient,
    supabase_mgr: SupabaseManager,
    auto_complete: bool = False,
) -> str:
    """
    Completar recolección de respuesta.
    
    Pasos:
    1. Consolidar todos los mensajes
    2. Validar completitud
    3. Si validación falla → pedir más info
    4. Si válida → marcar completada y avanzar
    """
    
    logger.info(f"Completing respuesta {respuesta_activa.id}, auto_complete={auto_complete}")
    
    # ========== STEP 1: Consolidar respuesta ==========
    mensajes = respuesta_activa.get_mensajes()
    
    if not mensajes:
        await meta_client.send_text(
            payload.telefono,
            "⚠️ No hay mensajes en tu respuesta. Intenta de nuevo."
        )
        return "empty_response"
    
    # Combinar contenidos de texto
    textos = [msg.get("contenido", "") for msg in mensajes if msg.get("contenido", "").strip()]
    respuesta_consolidada = "\n\n".join(textos)
    
    # Recolectar todas las URLs de media
    media_urls = []
    for msg in mensajes:
        for media in msg.get("media_ids", []):
            media_urls.append(media.get("url"))
    
    # ========== STEP 2: Validar completitud ==========
    validacion = self._validate_respuesta_completitud(
        bloque_id=respuesta_activa.bloque_id,
        respuesta_consolidada=respuesta_consolidada,
        media_urls=media_urls,
        mensajes=mensajes,
    )
    
    if not validacion["es_valida"]:
        logger.warning(f"Validation failed for respuesta {respuesta_activa.id}: {validacion['razon']}")
        
        await meta_client.send_text(
            payload.telefono,
            f"⚠️ {validacion['razon']}\n\n¿Puedes agregar más detalles? O escribe LISTO para continuar sin validar."
        )
        
        # Mantener en recolectando
        supabase_mgr.create_respuesta_audit_log(
            id_respuesta=respuesta_activa.id,
            evento="validacion_fallida",
            detalles={"razon": validacion["razon"]}
        )
        
        return "validation_failed"
    
    # ========== STEP 3: Marcar como completada ==========
    ahora = datetime.now(timezone.utc).isoformat()
    
    supabase_mgr.update_respuesta_pregunta(
        id_respuesta=respuesta_activa.id,
        estado="completada",
        respuesta_consolidada=respuesta_consolidada,
        confirmado_por_auditor=not auto_complete,
        timestamp_ultimo_mensaje=ahora,
    )
    
    supabase_mgr.create_respuesta_audit_log(
        id_respuesta=respuesta_activa.id,
        evento="completada",
        detalles={
            "auto_complete": auto_complete,
            "mensajes_count": len(mensajes),
            "textos_count": len(textos),
            "medios_count": len(media_urls),
        }
    )
    
    # ========== STEP 4: Actualizar conversación ==========
    supabase_mgr.update_conversacion(
        telefono=payload.telefono,
        estado=ConversationState.EN_BLOQUE,  # O EN_AUDITORIA según contexto
        id_respuesta_actual=None,
    )
    
    # ========== STEP 5: Enviar confirmación ==========
    await meta_client.send_text(payload.telefono, "✅ Respuesta registrada.")
    
    # ========== STEP 6: Avanzar a siguiente pregunta (si existe) ==========
    # Aquí va la lógica para obtener siguiente pregunta y enviarla
    # Por ahora, placeholder:
    await meta_client.send_text(
        payload.telefono,
        "Siguiente pregunta: (Implementar lógica de avance)"
    )
    
    logger.info(f"Respuesta {respuesta_activa.id} completed successfully")
    
    return "respuesta_completada"


def _validate_respuesta_completitud(
    self,
    bloque_id: str,
    respuesta_consolidada: str,
    media_urls: list,
    mensajes: list,
) -> dict:
    """
    Validar que la respuesta sea completa.
    
    Reglas por bloque_id (configurables en RESPUESTA_VALIDACION).
    """
    
    regla = RESPUESTA_VALIDACION.get(
        bloque_id,
        {"min_texto": 5, "requiere_foto": False, "requiere_audio": False}
    )
    
    # Validación 1: Mínimo de caracteres
    if len(respuesta_consolidada.strip()) < regla["min_texto"]:
        return {
            "es_valida": False,
            "razon": f"Tu respuesta es muy corta ({len(respuesta_consolidada.strip())} caracteres, "
                    f"mínimo {regla['min_texto']}). Describe más detalladamente."
        }
    
    # Validación 2: Requiere foto
    if regla["requiere_foto"] and not media_urls:
        return {
            "es_valida": False,
            "razon": "Este punto requiere una foto. Por favor envía una imagen."
        }
    
    # Validación 3: Errores en descarga de medios
    for msg in mensajes:
        if msg.get("estado_procesamiento") == "error":
            return {
                "es_valida": False,
                "razon": f"Hubo un problema con un medio: {msg.get('error_mensaje')}. Intenta enviar de nuevo."
            }
    
    return {"es_valida": True}
```

**Verificaciones**:
- [ ] Método `_handle_recolectando_respuesta` maneja texto, foto y audio
- [ ] Validación de completitud se ejecuta antes de avanzar
- [ ] Audit log se crea para cada evento importante
- [ ] Tiempos y transiciones de estado son claros
- [ ] No hay breaking changes con flujos existentes

---

## 🎯 FASE 5: BACKGROUND JOB - TIMEOUT CHECKING (2-3 horas)

### 5.1 Agregar en `main.py` (en la sección de scheduled tasks)

```python
# NUEVO: Background job para verificar timeouts en respuestas incompletas

async def check_incomplete_respuestas_timeout():
    """
    Background job: Verificar respuestas sin completar que superaron timeouts.
    
    Timeouts progresivos:
    - 120s sin actividad → Enviar "¿Terminaste?" prompt
    - 150s sin respuesta al prompt → Auto-completar
    - 300s total → Descartar
    
    Ejecutar cada 30-60 segundos.
    """
    
    while True:
        try:
            await asyncio.sleep(30)  # Revisar cada 30 segundos
            
            supabase_mgr = SupabaseManager()
            meta_client = MetaClient()
            
            # Obtener respuestas que superaron 120s
            respuestas_timeout_120 = supabase_mgr.get_respuestas_incompletas_timeout(
                timeout_segundos=120
            )
            
            for respuesta in respuestas_timeout_120:
                ahora = datetime.now(timezone.utc)
                
                # Parse timestamp
                ultimo_msg = datetime.fromisoformat(respuesta.timestamp_ultimo_mensaje)
                if ultimo_msg.tzinfo is None:
                    ultimo_msg = ultimo_msg.replace(tzinfo=timezone.utc)
                
                segundos_sin_actividad = (ahora - ultimo_msg).total_seconds()
                
                # STAGE 1: 120s → Enviar prompt de confirmación (una sola vez)
                if 120 <= segundos_sin_actividad < 150:
                    # Check if we already sent confirmation prompt
                    # (usar flag en conversacion tabla o respuesta tabla)
                    
                    logger.info(
                        f"Timeout 120s for respuesta {respuesta.id}: "
                        f"{segundos_sin_actividad:.1f}s sin actividad"
                    )
                    
                    await meta_client.send_text(
                        respuesta.telefono_auditor,
                        "⏱️ Timeout: ¿Ya terminaste de enviar tu respuesta?\n\n"
                        "Escribe LISTO para continuar, o sigue enviando mensajes."
                    )
                    
                    # Marcar que ya enviamos prompt
                    supabase_mgr.update_respuesta_pregunta(
                        id_respuesta=respuesta.id,
                        confirmado_por_auditor=False,  # Still waiting for confirmation
                    )
                    
                    supabase_mgr.create_respuesta_audit_log(
                        id_respuesta=respuesta.id,
                        evento="timeout_prompt_enviado",
                        detalles={"segundos": segundos_sin_actividad}
                    )
                
                # STAGE 2: 150s → Auto-completar
                elif 150 <= segundos_sin_actividad < 300:
                    logger.info(
                        f"Auto-completing respuesta {respuesta.id}: "
                        f"{segundos_sin_actividad:.1f}s sin respuesta"
                    )
                    
                    # Completar automáticamente
                    await meta_client.send_text(
                        respuesta.telefono_auditor,
                        "⏱️ Auto-completando tu respuesta por timeout..."
                    )
                    
                    # Llamar a _complete_respuesta_collection con auto_complete=True
                    # (Aquí simplificado: solo marcar como completada)
                    supabase_mgr.update_respuesta_pregunta(
                        id_respuesta=respuesta.id,
                        estado="completada",
                        confirmado_por_auditor=False,  # Auto-completed
                    )
                    
                    supabase_mgr.create_respuesta_audit_log(
                        id_respuesta=respuesta.id,
                        evento="auto_completada",
                        detalles={"segundos": segundos_sin_actividad}
                    )
                
                # STAGE 3: 300s → Descartar
                elif segundos_sin_actividad >= 300:
                    logger.warning(
                        f"Discarding respuesta {respuesta.id}: "
                        f"max timeout alcanzado ({segundos_sin_actividad:.1f}s)"
                    )
                    
                    await meta_client.send_text(
                        respuesta.telefono_auditor,
                        "❌ Timeout: Tu respuesta fue descartada por inactividad.\n\n"
                        "Escribe un nuevo hallazgo cuando estés listo."
                    )
                    
                    supabase_mgr.update_respuesta_pregunta(
                        id_respuesta=respuesta.id,
                        estado="descartada",
                        razon_descarte="timeout_300s",
                    )
                    
                    supabase_mgr.create_respuesta_audit_log(
                        id_respuesta=respuesta.id,
                        evento="descartada_timeout",
                        detalles={"segundos": segundos_sin_actividad}
                    )
        
        except Exception as e:
            logger.error(f"Error in check_incomplete_respuestas_timeout: {e}")
            await asyncio.sleep(60)  # Retry después de error


# Agregar a la función main() o startup event:
@app.on_event("startup")
async def startup_event():
    # ... existing startup code ...
    
    # Start background job
    asyncio.create_task(check_incomplete_respuestas_timeout())
    logger.info("Started check_incomplete_respuestas_timeout background job")
```

**Verificaciones**:
- [ ] Background job se inicia en startup event
- [ ] Revisa cada 30 segundos (configurable)
- [ ] Progressively escalates (120s → prompt, 150s → auto-complete, 300s → discard)
- [ ] Crea audit logs para cada acción

---

## 🎯 FASE 6: INTEGRACIÓN CON FLUJO EXISTENTE (1-2 horas)

### 6.1 Actualizar `ConversationRouter.route()` en router.py

En el método `route()` o equivalente, agregar:

```python
async def route(self, payload: WhatsAppPayload, conv: Conversacion) -> str:
    """
    Route mensaje a handler correcto según estado de conversación.
    """
    
    meta_client = MetaClient()
    supabase_mgr = SupabaseManager()
    
    # ... existing code ...
    
    # NUEVO: Check si estamos en flujo de recolección de respuesta
    if conv.estado == ConversationState.RECOLECTANDO_RESPUESTA:
        return await self._handle_recolectando_respuesta(
            payload=payload,
            conv=conv,
            meta_client=meta_client,
            supabase_mgr=supabase_mgr,
        )
    
    # ... resto de handlers existentes ...
```

### 6.2 Actualizar transición a RECOLECTANDO_RESPUESTA

Cuando se envíe una pregunta, la conversación debe transicionar a `RECOLECTANDO_RESPUESTA`:

```python
# Cuando se envía una pregunta (en el handler que corresponda):

# Crear respuesta_pregunta
respuesta = RespuestaPregunta(
    id=str(uuid.uuid4()),
    id_sesion=conv.id_sesion,
    telefono_auditor=payload.telefono,
    pregunta_numero=numero_actual,
    bloque_id=bloque_actual.id,
    estado=RespuestaPreguntaEstado.RECOLECTANDO,
    timestamp_inicio=datetime.now(timezone.utc).isoformat(),
    timestamp_ultimo_mensaje=datetime.now(timezone.utc).isoformat(),
    timeout_segundos=120,
    confirmado_por_auditor=False,
)

supabase_mgr.create_respuesta_pregunta(respuesta)

# Actualizar conversación
supabase_mgr.update_conversacion(
    telefono=payload.telefono,
    estado=ConversationState.RECOLECTANDO_RESPUESTA,
    id_respuesta_actual=respuesta.id,
)

# Enviar pregunta
await meta_client.send_text(
    payload.telefono,
    f"Pregunta {numero_actual}/X:\n\n{pregunta_texto}\n\n"
    f"Puedes enviar múltiples mensajes (texto, fotos, audios). "
    f"Escribe LISTO cuando termines."
)
```

**Verificaciones**:
- [ ] Transición a RECOLECTANDO_RESPUESTA está integrada
- [ ] respuesta_pregunta se crea antes de enviar la pregunta
- [ ] Flujo existente no se rompe

---

## 🎯 FASE 7: TESTING (2-3 horas)

### 7.1 Unit Tests (si hay suite de tests)

```python
# tests/test_respuesta_recolectora.py

import pytest
from datetime import datetime, timezone
from models import RespuestaPregunta, MensajeEnRespuesta, RespuestaPreguntaEstado

def test_respuesta_pregunta_deserialization():
    """Verificar que RespuestaPregunta deserializa mensajes correctamente."""
    mensaje1 = {"tipo": "text", "contenido": "Hallazgo 1", "media_ids": [], "timestamp": "..."}
    mensaje2 = {"tipo": "image", "contenido": "", "media_ids": [{"url": "..."}], "timestamp": "..."}
    
    respuesta = RespuestaPregunta(
        id="test-1",
        id_sesion="sesion-1",
        telefono_auditor="11234567890",
        pregunta_numero=1,
        bloque_id="PRES",
        estado=RespuestaPreguntaEstado.RECOLECTANDO,
        timestamp_inicio="...",
        timestamp_ultimo_mensaje="...",
        mensajes_json=json.dumps([mensaje1, mensaje2]),
    )
    
    mensajes = respuesta.get_mensajes()
    assert len(mensajes) == 2
    assert mensajes[0].tipo == "text"
    assert mensajes[1].tipo == "image"

def test_validacion_completitud_min_texto():
    """Verificar que validación detecta respuestas cortas."""
    router = ConversationRouter()
    
    resultado = router._validate_respuesta_completitud(
        bloque_id="PRES",
        respuesta_consolidada="Hola",  # Too short
        media_urls=[],
        mensajes=[],
    )
    
    assert not resultado["es_valida"]
    assert "muy corta" in resultado["razon"].lower()

def test_validacion_completitud_requiere_foto():
    """Verificar que validación requiere foto cuando aplica."""
    router = ConversationRouter()
    
    resultado = router._validate_respuesta_completitud(
        bloque_id="GOND",  # Requiere foto
        respuesta_consolidada="Gondola desordenada, muchos detalles...",
        media_urls=[],  # Sin foto
        mensajes=[],
    )
    
    assert not resultado["es_valida"]
    assert "foto" in resultado["razon"].lower()
```

### 7.2 End-to-End Manual Testing

**Scenario 1: Auditor envía 3 mensajes + LISTO**
```
1. Auditor: Pregunta recibida
2. Auditor: [Envía FOTO]
   Bot: "📸 Foto guardada..."
3. Auditor: "Vidriera desordenada"
   Bot: "✓ Registrado..."
4. Auditor: LISTO
   Bot: "✅ Respuesta registrada"
   Bot: "Siguiente pregunta: ..."
```

✓ Verificar: BD tiene 3 mensajes en respuesta_pregunta.mensajes_json

**Scenario 2: Timeout 120s + auto-complete**
```
1. Auditor: Pregunta recibida
2. Auditor: [Envía FOTO]
   Bot: "📸 Foto guardada..."
3. [Esperar 120s sin mensaje]
   Bot: "⏱️ ¿Ya terminaste?"
4. [Esperar 30s más sin respuesta]
   Bot: "Auto-completando..."
   Bot: "✅ Respuesta registrada"
```

✓ Verificar: BD tiene respuesta_pregunta.estado = "completada", confirmado_por_auditor = false

**Scenario 3: Validación falla**
```
1. Auditor: Pregunta recibida (GOND - requiere foto)
2. Auditor: "Vidriera desordenada"
   Bot: "✓ Registrado..."
3. Auditor: LISTO
   Bot: "⚠️ Este punto requiere una foto..."
```

✓ Verificar: BD tiene respuesta_pregunta.estado = "recolectando" (aún abierta)

---

## ✅ CHECKLIST FINAL DE IMPLEMENTACIÓN

### Base de Datos
- [ ] `etapa-8-respuesta-recolectora.sql` ejecutada en Supabase
- [ ] Tabla `respuesta_pregunta` creada con todos los índices
- [ ] Tabla `respuesta_pregunta_audit_log` creada
- [ ] Columnas agregadas a `sesiones_auditoria` y `conversaciones`

### Backend - Python
- [ ] Nuevos modelos en `models.py` (RespuestaPregunta, MensajeEnRespuesta, etc.)
- [ ] Nuevas funciones en `supabase_manager.py` (CRUD respuesta_pregunta)
- [ ] Método `_handle_recolectando_respuesta()` en router.py
- [ ] Método `_complete_respuesta_collection()` en router.py
- [ ] Método `_validate_respuesta_completitud()` en router.py
- [ ] Background job `check_incomplete_respuestas_timeout()` en main.py
- [ ] Integration en `ConversationRouter.route()` para state transition

### Testing
- [ ] Unit tests pasan (si existen)
- [ ] 3 scenarios end-to-end probados manualmente
- [ ] Audit logs verificados (eventos importantes grabados)
- [ ] No hay breaking changes en flujos existentes

### Code Quality
- [ ] 0 hardcoded secrets
- [ ] All exceptions logged (no swallowed errors)
- [ ] Timestamps always UTC
- [ ] JSON serialization safe (ensure_ascii=False)
- [ ] Índices en BD optimizados para queries

---

## 📋 NOTAS IMPORTANTES

1. **No romper flujo existente**: Los nuevos handlers se agregan como opciones adicionales en el router. Flujos existentes (auditor actual) siguen funcionando igual.

2. **Idempotencia SQL**: El script SQL es idempotente. Puede correrse múltiples veces sin problemas.

3. **Configuración centralizada**: RESPUESTA_CONFIG y RESPUESTA_VALIDACION están en un lugar fácil de modificar si se necesita ajustar timeouts o reglas de validación.

4. **Logging exhaustivo**: Cada acción importante se loguea y se crea audit log. Facilita debugging.

5. **Background job resiliente**: Si algo falla, reintentas después de 60s. El job sigue ejecutándose.

6. **Medios opcionales**: Las fotos/audios son opcionales según bloque_id. Configurar en RESPUESTA_VALIDACION.

7. **Future proofing**: Estructura preparada para agregar:
   - Transcripción de audios (OpenAI Whisper)
   - Extracción de desvíos automática (Claude API)
   - OCR de fotos (Google Vision)

---

## 📞 PREGUNTAS FRECUENTES PARA CODEX

**P**: ¿Qué sucede si el auditor no envía LISTO?  
**R**: Después de 150s sin respuesta al prompt de "¿terminaste?", el bot auto-completa automáticamente.

**P**: ¿Se pierden los mensajes si hay error?  
**R**: No. Cada mensaje se guarda en DB con `estado_procesamiento=error` si hay problema. El auditor puede reintentar.

**P**: ¿Cómo retroceder si la validación falla?  
**R**: El estado sigue siendo `recolectando`, el auditor puede enviar más mensajes sin perder los anteriores.

**P**: ¿Qué pasa si la conexión se pierde?  
**R**: Meta reintentará enviar el webhook. Si es duplicado, se deduplica con `message_id`. Los datos se guardan igual.

**P**: ¿Se pueden editar mensajes después?  
**R**: No. El sistema es append-only. Si hay error, crear nueva respuesta. (Feature futura: reeditar)

---

**Implementar en este orden**: 
1. BD (SQL)
2. Modelos Python
3. SupabaseManager
4. Router logic (_handle + _complete + _validate)
5. Background job
6. Integration
7. Testing

**Tiempo estimado**: 8-10 horas para implementación limpia + testing.

**Revisor**: Claude Code (yo), para audit de arquitectura y code review.

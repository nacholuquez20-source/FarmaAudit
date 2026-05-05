# Prompt para Codex: Módulo de Desvíos con Bot WhatsApp

## Resumen Ejecutivo

FarmaAudit es una aplicación de auditoría farmacéutica con un bot WhatsApp en producción (Railway). El flujo actual de desvíos está **parcialmente desconectado**: los auditores crean desvíos en la app, pero luego contactan manualmente a los encargados por WhatsApp y copian URLs de fotos a mano.

**Objetivo**: Automatizar el ciclo completo:
1. Auditor crea desvío en app → notifica al encargado por WhatsApp automáticamente
2. Encargado responde al bot → bot identifica que es encargado y enumera sus desvíos pendientes
3. Encargado selecciona desvío y sube foto de corrección en WhatsApp
4. Bot guarda automáticamente mensaje + foto en la base de datos
5. Auditor ve la respuesta en la app y cierra el desvío

---

## Stack Técnico Actual

### Backend (Bot)
- **Framework**: FastAPI (async Python)
- **WhatsApp**: Meta Cloud API v19.0
- **Database**: Supabase (PostgreSQL con RLS)
- **Deployment**: Railway
- **Key files**:
  - `main.py` (501 líneas) - webhook principal que recibe mensajes de Meta
  - `meta_client.py` (238 líneas) - cliente para enviar mensajes/fotos por WhatsApp
  - `router.py` - ConversationRouter con state machine para flujos de auditor
  - `config.py` - configuración centralizada de secretos y parámetros
  - `supabase_manager.py` - abstracción de DB con caché de 5 min

### Frontend
- **Framework**: React 18 + TypeScript + Vite + Tailwind
- **Backend API**: Supabase (cliente JS)
- **Deployment**: Vercel desde rama master
- **Auth**: Supabase Auth con roles (admin, auditor, sucursal)

### Database (Supabase)
Tablas relevantes:
- `reportes` - datos de auditoría (contiene `foto_url` de WhatsApp CDN)
- `gestion` - el desvío (estado: Abierta, En_proceso, Cerrada, etc.)
- `desvio_eventos` - timeline inmutable de eventos (creacion, contacto, respuesta, cierre, nota, evidencia)
  - Campo `metadata` JSONB: guarda datos adicionales
- `profiles` - usuarios (id, role, nombre, telefono, id_sucursal)
- `sucursales` - sucursales (id, nombre, responsable, tel_responsable)

---

## Bug Crítico a Corregir Primero

**Archivo**: `frontend/src/hooks/useAuth.ts` línea 51

El query al cargar perfil NO incluye `id_sucursal`:
```typescript
// ACTUAL (incorrecto):
.select('id, role, nombre, telefono')

// DEBE SER:
.select('id, role, nombre, telefono, id_sucursal')
```

Sin esto, el rol `sucursal` no puede filtrar desvíos por su sucursal.

---

## Cambios Requeridos

### 1. Base de Datos (Supabase)

**Archivo**: `frontend/docs/sql/etapa-7-bot-encargado.sql` (CREAR)

```sql
-- Extender tipos de evento en desvio_eventos
ALTER TABLE desvio_eventos
DROP CONSTRAINT IF EXISTS desvio_eventos_tipo_check;

ALTER TABLE desvio_eventos
ADD CONSTRAINT desvio_eventos_tipo_check
CHECK (tipo IN ('creacion','contacto','respuesta','cierre','nota','evidencia','mensaje'));

-- Tabla de notificaciones in-app para auditor
CREATE TABLE IF NOT EXISTS desvio_notificaciones (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  id_gestion  text NOT NULL REFERENCES gestion(id_gestion) ON DELETE CASCADE,
  user_id     uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tipo        text NOT NULL CHECK (tipo IN ('encargado_respondio','estado_cambio')),
  leida       boolean NOT NULL DEFAULT false,
  created_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notif_user    ON desvio_notificaciones(user_id, leida);
CREATE INDEX IF NOT EXISTS idx_notif_gestion ON desvio_notificaciones(id_gestion);

ALTER TABLE desvio_notificaciones ENABLE ROW LEVEL SECURITY;

CREATE POLICY "notif_own_read"   ON desvio_notificaciones FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "notif_own_update" ON desvio_notificaciones FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "notif_insert_auth" ON desvio_notificaciones FOR INSERT WITH CHECK (auth.uid() IS NOT NULL);

-- Storage bucket: nombre "desvio-evidencias" | Privado | Max 10MB | Tipos: image/*, application/pdf
-- (Crear manualmente en Supabase Dashboard → Storage)

-- RLS para Storage
CREATE POLICY "storage_evidencias_upload" ON storage.objects
  FOR INSERT WITH CHECK (
    bucket_id = 'desvio-evidencias'
    AND auth.uid() IS NOT NULL
  );

CREATE POLICY "storage_evidencias_read" ON storage.objects
  FOR SELECT USING (
    bucket_id = 'desvio-evidencias'
    AND auth.uid() IS NOT NULL
  );
```

---

### 2. Backend: Extensión del Bot

**Contexto**: El bot actual maneja conversaciones de AUDITOR. Ahora debe:
- Detectar si el mensaje viene de un ENCARGADO (lookup por teléfono en `profiles` o `sucursales`)
- Enumerar desvíos pendientes de esa sucursal
- Permitir al encargado seleccionar desvío y responder con foto
- Auto-guardar respuesta + foto en `desvio_eventos` + `storage`

**Cambios en `router.py`**:

Agregar nuevo path de conversación para encargados:

```python
# Pseudocódigo - implementar según patrón existente de ConversationRouter

class ConversationRouter:
    # ... código existente para auditor ...
    
    async def handle_encargado_message(self, payload: WhatsAppPayload) -> None:
        """
        Flujo para ENCARGADO respondiendo a desvíos:
        
        1. Lookup: phone → buscar en profiles o sucursales por telefono
        2. Si no existe, responder "No eres un encargado registrado"
        3. Si existe:
           - Listar desvíos pendientes de su id_sucursal
           - Mostrar menú numerado: "1) [severidad] descripción | 2) ..."
           - Guardar estado conversación: esperando selección de desvío
        
        4. Usuario selecciona número:
           - Guardar id_gestion seleccionado
           - Preguntar: "¿Subir foto o escribir descripción de corrección?"
           - Estado siguiente: esperando foto o texto
        
        5. Usuario sube foto o escribe:
           - Descargar foto de Meta CDN (si es imagen)
           - Guardar en Supabase Storage: gestion/{id_gestion}/{uuid}.jpg
           - Insertar en desvio_eventos:
             - tipo: 'mensaje' (si es texto) o 'evidencia' (si es foto)
             - metadata: { origen: 'sucursal', foto_path: '...', foto_url_signed: '...' }
           - Crear notificación en desvio_notificaciones para auditor
           - Responder al encargado: "Recibida tu respuesta, el auditor la revisará"
        """
        pass
```

**Cambios en `meta_client.py`**:

Agregar función para descargar archivos de Meta CDN:

```python
async def download_media(media_id: str) -> bytes:
    """Descargar archivo de Meta usando media_id"""
    # GET /v19.0/{media_id}?access_token={token}
    # Retornar bytes del archivo
    pass
```

**Cambios en `supabase_manager.py`**:

Agregar funciones para guardar mensajes/fotos del encargado:

```python
async def save_encargado_evento(
    id_gestion: str,
    tipo: str,  # 'mensaje' o 'evidencia'
    contenido: str,  # texto del mensaje o path de foto en storage
    metadata: dict,
) -> None:
    """Guardar evento en desvio_eventos"""
    pass

async def create_notification_for_auditor(
    id_gestion: str,
    auditor_id: str,
) -> None:
    """Crear notificación para auditor en desvio_notificaciones"""
    pass
```

---

### 3. Frontend: API + Hooks

**Archivo**: `frontend/src/lib/api.ts` - agregar funciones:

```typescript
// 1. Enviar notificación WhatsApp al encargado desde la app
export async function notificarEncargado(
  idGestion: string,
  telefonoEncargado: string,
  descripcionDesvio: string,
): Promise<void> {
  // POST /api/send-encargado-notification
  // Backend: envía WhatsApp al encargado con id_gestion + descripción
}

// 2. Obtener notificaciones no leídas (cuando auditor ve badge)
export async function getNotificaciones(): Promise<Notificacion[]> {
  const { data, error } = await supabase
    .from('desvio_notificaciones')
    .select('*')
    .eq('leida', false)
    .order('created_at', { ascending: false });
  if (error) throw error;
  return data ?? [];
}

// 3. Marcar notificación como leída
export async function marcarNotificacionLeida(id: string): Promise<void> {
  const { error } = await supabase
    .from('desvio_notificaciones')
    .update({ leida: true })
    .eq('id', id);
  if (error) throw error;
}
```

**Archivo**: `frontend/src/hooks/useNotificaciones.ts` (CREAR)

```typescript
export function useNotificaciones() {
  // Hook que:
  // 1. Polling cada 30 segundos de getNotificaciones()
  // 2. Retorna: notificaciones[], unreadCount, marcarLeida(id)
  // 3. Suena notificación si hay nuevas (opcional)
}
```

**Tipos**: `frontend/src/types/index.ts` - agregar:

```typescript
interface Notificacion {
  id: string;
  id_gestion: string;
  user_id: string;
  tipo: 'encargado_respondio' | 'estado_cambio';
  leida: boolean;
  created_at: string;
}
```

---

### 4. Frontend: Página DesvioDetail Modificada

**Archivo**: `frontend/src/pages/DesvioDetail.tsx`

En la sección superior del desvío, agregar botón:

```typescript
// Si el auditor aún no notificó al encargado (estado Abierta):
<button onClick={() => notificarEncargado(idGestion, tel_responsable, descripcion)}>
  📱 Notificar al Encargado por WhatsApp
</button>

// Vista de eventos existentes, pero ahora incluirá:
// - Eventos tipo 'mensaje' del encargado (solo texto)
// - Eventos tipo 'evidencia' del encargado (foto en Storage con signed URL)
```

---

### 5. Frontend: Navbar con Badge de Notificaciones

**Archivo**: `frontend/src/components/AppLayout.tsx`

Modificar navbar para:

```typescript
// Agregar useNotificaciones() hook
const { notificaciones, unreadCount } = useNotificaciones();

// Mostrar bell icon con badge rojo si unreadCount > 0
// Click → panel desplegable con lista:
//   - "Encargado respondió en Desvío #123"
//   - Click en notificación → navega a /desvios/:id + marca leída
```

---

## Flujo End-to-End (después de implementar)

```
1. AUDITOR en /desvios/:id
   └─ Click "Notificar al Encargado por WhatsApp"
      └─ Se envía a encargado: "Tienes desvíos por rectificar en tu sucursal"

2. ENCARGADO recibe WhatsApp (número del bot)
   └─ Responde cualquier cosa para iniciar conversación
   └─ Bot identifica: phone → profiles.id_sucursal
   └─ Bot responde: "Tienes 3 desvíos pendientes:
                    1) [Alta] Temperatura de congelador
                    2) [Media] Vencimientos en stock
                    3) [Baja] Etiquetas ilegibles"

3. ENCARGADO responde "1"
   └─ Bot responde: "¿Subir foto o escribir descripción?"

4. ENCARGADO sube foto (de congelador reparado)
   └─ Bot descarga foto de Meta CDN
   └─ Bot guarda en Supabase Storage: desvio-evidencias/gestion/{id_123}/{uuid}.jpg
   └─ Bot inserta evento en desvio_eventos:
      - tipo: 'evidencia'
      - metadata: { origen: 'sucursal', foto_path: '...', foto_url_signed: '...' }
   └─ Bot crea notificación en desvio_notificaciones (para auditor)
   └─ Bot responde al encargado: "✓ Foto recibida, auditor la revisará"

5. AUDITOR ve badge en navbar (🔔 con "1" rojo)
   └─ Click en badge → ve "Encargado respondió en Desvío #123"
   └─ Click en notificación → va a /desvios/123 + marca leída
   └─ En la página ve evento nuevo: foto del encargado con timestamp + badge "Encargado"
   └─ AUDITOR puede validar y hacer clic "Marcar como Cerrado"
```

---

## Archivos a Crear/Modificar

### Backend
| Cambio | Prioridad |
|--------|-----------|
| `router.py` - agregar path encargado | ALTA |
| `meta_client.py` - agregar download_media() | ALTA |
| `supabase_manager.py` - agregar save_encargado_evento(), create_notification() | ALTA |
| `main.py` - actualizar webhook para detectar encargado vs auditor | ALTA |
| Crear endpoint POST `/api/send-encargado-notification` | MEDIA |

### Frontend
| Cambio | Prioridad |
|--------|-----------|
| `frontend/src/hooks/useAuth.ts` - **FIX id_sucursal** | CRÍTICA |
| `frontend/src/types/index.ts` - agregar Notificacion | BAJA |
| `frontend/src/lib/api.ts` - agregar notificarEncargado(), getNotificaciones(), marcarNotificacionLeida() | ALTA |
| `frontend/src/hooks/useNotificaciones.ts` - crear | MEDIA |
| `frontend/src/pages/DesvioDetail.tsx` - agregar botón "Notificar Encargado" | MEDIA |
| `frontend/src/components/AppLayout.tsx` - agregar bell + dropdown notificaciones | MEDIA |

### Database
| Cambio | Prioridad |
|--------|-----------|
| `frontend/docs/sql/etapa-7-bot-encargado.sql` - crear | ALTA |
| Ejecutar migraciones en Supabase | ALTA |
| Crear bucket `desvio-evidencias` en Storage | ALTA |

---

## Notas Importantes

1. **Deduplicación de mensajes**: El bot ya tiene webhook deduplication en `main.py`. Asegurar que se aplique también a mensajes de encargados.

2. **Async locking**: El bot usa `_message_lock` y `_conversation_locks` para evitar race conditions. Mantener este patrón en nuevo path de encargado.

3. **Signed URLs**: Las fotos en Storage vencen en 24h. Frontend debe refrescar URLs si son antiguas.

4. **Retrocompatibilidad**: Desvíos antiguos pueden tener `metadata.evidencia_url` (URL pegada a mano). Mostrar como links sin thumbnail.

5. **RLS**: Las notificaciones solo se pueden leer si `auth.uid() = user_id`. El insert debe hacerse desde backend con `supabase_service_key`.

6. **Encargado solo responde**: El encargado NO puede cambiar estado del desvío ni crear mensajes en la app. Solo responde por WhatsApp.

7. **Auditor ve todo**: El auditor ve en timeline todas las respuestas del encargado, puede validar, rechazar (responder por WhatsApp), o cerrar.

---

## Testing

1. **Bug fix id_sucursal**: Login como `sucursal` → verificar en DevTools que `profile.id_sucursal` tiene valor
2. **Notificación**: Auditor → click "Notificar Encargado" → encargado recibe WhatsApp con menú
3. **Selección de desvío**: Encargado responde "1" → bot enumera opciones de foto/texto
4. **Upload de foto**: Encargado sube foto → bot descarga, guarda en Storage → auditor ve en app
5. **Notificación en app**: Auditor ve badge de notificación → click → va al desvío correcto
6. **Cierre de desvío**: Auditor valida respuesta del encargado → marca como Cerrada

---

## Entregables Esperados

- ✅ Backend: router.py + meta_client.py + supabase_manager.py completamente funcionales
- ✅ Frontend: bug fix id_sucursal, API functions, hooks, componentes de notificación
- ✅ Database: migraciones ejecutadas, bucket creado
- ✅ Testing: todos los pasos de testing completados
- ✅ Documentación: readme de nuevas funciones (opcional pero recomendado)

---

## Preguntas de Clarificación para Codex

Si hay dudas durante implementación:
1. ¿Cómo se maneja la persistencia de "en qué desvío estoy respondiendo" si el encargado abre varias conversaciones?
2. ¿El encargado puede rechazar un desvío o solo marcar como solucionado?
3. ¿Si el auditor notifica múltiples encargados, cada uno solo ve sus desvíos o todos los de su sucursal?
4. ¿El bot debe enviar foto de prueba o solo texto con link a la app para ver fotos?

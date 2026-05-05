# ✅ Checklist de Revisión Post-Codex

## 📝 Pre-Review: Cambios Esperados

**Archivos a ser creados**: 8
**Archivos a ser modificados**: 6
**Migraciones SQL**: 1

---

## 🔴 CRÍTICO - Revisar Primero

### 1. Bug Fix: id_sucursal en useAuth.ts
**Archivo**: `frontend/src/hooks/useAuth.ts:51`

```typescript
// ❌ ANTES (línea 51):
.select('id, role, nombre, telefono')

// ✅ DESPUÉS:
.select('id, role, nombre, telefono, id_sucursal')
```

**Verificación**:
- [ ] Cambio aplicado exactamente en línea 51
- [ ] No hay otros `.select()` sin `id_sucursal` en el mismo archivo
- [ ] El resto de la función `loadProfile()` intacta

---

## 🟠 ALTA PRIORIDAD

### 2. Database: Migraciones (etapa-7-bot-encargado.sql)
**Archivo**: `frontend/docs/sql/etapa-7-bot-encargado.sql` (CREAR)

**Verificaciones**:
- [ ] Archivo existe y está en la ruta correcta
- [ ] `desvio_eventos` tiene constraint actualizado con tipo `'mensaje'`
- [ ] Tabla `desvio_notificaciones` creada con:
  - [ ] Columnas: id, id_gestion, user_id, tipo, leida, created_at
  - [ ] FK a gestion y auth.users con ON DELETE CASCADE
  - [ ] Constraint de `tipo` con valores correctos
  - [ ] Índices creados (idx_notif_user, idx_notif_gestion)
  - [ ] RLS ENABLED
  - [ ] 3 policies: notif_own_read, notif_own_update, notif_insert_auth
- [ ] Storage bucket RLS policies creadas

**SQL a ejecutar manualmente en Supabase**:
- [ ] Verificar que script es idempotente (CREATE TABLE IF NOT EXISTS, DROP CONSTRAINT IF EXISTS, etc.)

---

### 3. Backend: Router.py - Nuevo Path de Encargado
**Archivo**: `router.py` (MODIFICAR)

**Verificaciones**:
- [ ] Nueva clase o método `handle_encargado_message()` existe
- [ ] Función identifica encargado por teléfono (lookup en profiles/sucursales)
- [ ] Si teléfono no existe, responde "No eres un encargado registrado"
- [ ] Enumera desvíos pendientes de `id_sucursal`:
  - [ ] Query correcto: `estado IN ('Abierta', 'En_proceso')`
  - [ ] Ordena por fecha o severidad
  - [ ] Muestra formato: "1) [SEVERIDAD] descripción"
- [ ] Guarda estado conversación (async locks + conversation state machine)
- [ ] Maneja entrada de usuario:
  - [ ] Si número: valida que existe desvío, pide foto o texto
  - [ ] Si foto: descarga de Meta, guarda en Storage
  - [ ] Si texto: guarda texto en desvio_eventos
- [ ] Crea evento en `desvio_eventos` con metadata correcta:
  - [ ] `tipo`: 'mensaje' o 'evidencia'
  - [ ] `metadata.origen`: 'sucursal'
  - [ ] `metadata.foto_path`: ruta en Storage (si es foto)
- [ ] Crea notificación en `desvio_notificaciones` para auditor
- [ ] Responde al encargado: "✓ Recibida tu respuesta..."
- [ ] No rompe flujo existente de auditor (validar ConversationRouter.route())

---

### 4. Backend: meta_client.py - Download Media
**Archivo**: `meta_client.py` (MODIFICAR)

**Verificaciones**:
- [ ] Función `download_media(media_id: str) -> bytes` existe
- [ ] Hace GET a `/v19.0/{media_id}?access_token=...`
- [ ] Retorna bytes del archivo
- [ ] Maneja errores de Meta (media_id inválido, expirado)
- [ ] Log de errores sin exponer access_token
- [ ] Timeout razonable (no indefinido)

---

### 5. Backend: supabase_manager.py - Nuevas Funciones
**Archivo**: `supabase_manager.py` (MODIFICAR)

**Verificaciones**:
- [ ] Función `save_encargado_evento()`:
  - [ ] Parámetros: id_gestion, tipo, contenido, metadata
  - [ ] Inserta en `desvio_eventos` con columnas correctas
  - [ ] Usa `supabase_service_key` si inserta notificaciones (admin)
  - [ ] Manejo de errores
- [ ] Función `create_notification_for_auditor()`:
  - [ ] Parámetros: id_gestion, auditor_id
  - [ ] Inserta en `desvio_notificaciones` con tipo='encargado_respondio'
  - [ ] Usa supabase_service_key (para RLS)
  - [ ] No duplica notificaciones

---

### 6. Backend: main.py - Webhook Actualizado
**Archivo**: `main.py` (MODIFICAR)

**Verificaciones**:
- [ ] Webhook POST /webhook sigue funcionando
- [ ] Deduplicación (`_claim_message_for_processing`) se aplica a encargados también
- [ ] Routing detecta si es auditor o encargado:
  - [ ] Auditor: llama ConversationRouter.route() (flujo existente)
  - [ ] Encargado: llama ConversationRouter.handle_encargado_message()
- [ ] No hay cambios innecesarios en flujo existente
- [ ] Logs incluyen identificación (auditor vs encargado)

---

### 7. Frontend: Types - Nuevas Interfaces
**Archivo**: `frontend/src/types/index.ts` (MODIFICAR)

**Verificaciones**:
- [ ] Interface `Notificacion` existe con campos:
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
- [ ] No hay typos en nombres de campos
- [ ] Tipos exportados correctamente

---

### 8. Frontend: api.ts - Nuevas Funciones
**Archivo**: `frontend/src/lib/api.ts` (MODIFICAR)

**Verificaciones**:
- [ ] Función `notificarEncargado()`:
  - [ ] Parámetros: idGestion, telefonoEncargado, descripcionDesvio
  - [ ] POST a endpoint correcto (probablemente `/api/notify-encargado`)
  - [ ] Manejo de errores
- [ ] Función `getNotificaciones()`:
  - [ ] SELECT * FROM desvio_notificaciones WHERE leida=false
  - [ ] Ordena por created_at DESC
  - [ ] Castea a Notificacion[]
- [ ] Función `marcarNotificacionLeida()`:
  - [ ] UPDATE desvio_notificaciones SET leida=true WHERE id=?
  - [ ] Manejo de errores
- [ ] Todas importan supabase correctamente
- [ ] Tipos de retorno correctos

---

### 9. Frontend: useNotificaciones.ts (CREAR)
**Archivo**: `frontend/src/hooks/useNotificaciones.ts`

**Verificaciones**:
- [ ] Archivo existe
- [ ] Función `useNotificaciones()` exportada
- [ ] Implementación:
  - [ ] `const [notificaciones, setNotificaciones] = useState<Notificacion[]>([])`
  - [ ] `useEffect` que hace polling cada 30s de `getNotificaciones()`
  - [ ] `const unreadCount = notificaciones.length`
  - [ ] Función `marcarLeida(id)` que llama a api.marcarNotificacionLeida()
  - [ ] Cleanup: `clearInterval()` en return del useEffect
- [ ] Retorna object: `{ notificaciones, unreadCount, marcarLeida }`
- [ ] Sin memory leaks (cleanup correcto)

---

### 10. Frontend: DesvioDetail.tsx - Botón Notificar
**Archivo**: `frontend/src/pages/DesvioDetail.tsx` (MODIFICAR)

**Verificaciones**:
- [ ] Botón "📱 Notificar al Encargado por WhatsApp" agregado
- [ ] Solo visible cuando:
  - [ ] `estado === 'Abierta'` (no notificar si ya está cerrado)
  - [ ] `tel_responsable` existe
  - [ ] Usuario es auditor o admin
- [ ] Click en botón:
  - [ ] Llama `notificarEncargado(idGestion, tel_responsable, descripcionDesvio)`
  - [ ] Muestra loading state
  - [ ] Muestra mensaje de éxito/error
- [ ] No rompe UI existente (espaciado, responsive)
- [ ] En timeline de eventos, eventos tipo 'mensaje' y 'evidencia' con origen='sucursal' se muestran:
  - [ ] Badge "Encargado" o ícono diferente
  - [ ] Si es 'evidencia': mostrar foto con signed URL

---

### 11. Frontend: AppLayout.tsx - Bell + Notificaciones
**Archivo**: `frontend/src/components/AppLayout.tsx` (MODIFICAR)

**Verificaciones**:
- [ ] Navbar tiene bell icon (🔔 o similar)
- [ ] Badge rojo muestra `unreadCount` si > 0
- [ ] Click en bell:
  - [ ] Abre dropdown/modal con lista de notificaciones
  - [ ] Cada notificación muestra:
    - [ ] Texto: "Encargado respondió en Desvío #XXX"
    - [ ] Timestamp
  - [ ] Click en notificación:
    - [ ] Navega a `/desvios/:id_gestion`
    - [ ] Llama `marcarLeida(notificacion.id)`
    - [ ] Badge desaparece después
- [ ] Hook `useNotificaciones()` inicializado
- [ ] Loading state mientras obtiene notificaciones
- [ ] No rompe diseño existente de navbar

---

## 🟡 MEDIA PRIORIDAD

### 12. Backend: Endpoint POST /api/notify-encargado
**Archivo**: `main.py` (CREAR ENDPOINT)

**Verificaciones**:
- [ ] Ruta POST `/api/notify-encargado` existe
- [ ] Parámetros en body: `{ idGestion, telefonoEncargado, descripcionDesvio }`
- [ ] Valida que:
  - [ ] Usuario autenticado es auditor/admin
  - [ ] `id_gestion` existe en DB
  - [ ] `telefonoEncargado` tiene formato válido
- [ ] Llama `meta_client.send_text()` para enviar WhatsApp
- [ ] Retorna 200 OK o error apropiado
- [ ] No expone detalles de error sensibles

---

### 13. Integración: Storage Download y Upload
**Verificación end-to-end**:
- [ ] Encargado sube foto por WhatsApp → Meta CDN
- [ ] Bot descarga vía `download_media(media_id)` → bytes
- [ ] Bot sube a Supabase Storage:
  - [ ] Path: `desvio-evidencias/gestion/{id_gestion}/{uuid}.jpg`
  - [ ] Metadatos: content-type correcto
  - [ ] Sin errores de permiso
- [ ] Frontend obtiene signed URL:
  - [ ] Válida por 24h
  - [ ] Se refresca si expira
- [ ] Frontend muestra foto en timeline con preview thumbnail

---

## 🟢 VERIFICACIONES FINALES

### 14. Sin Regressions
**Verificar que flujo existente sigue funcionando**:
- [ ] Auditor login → ve desvíos normalmente
- [ ] Auditor puede cambiar estado (Abierta → En_proceso → Cerrada)
- [ ] Auditor puede crear eventos tipo 'nota'
- [ ] Auditor puede subir evidencias (si ya existía esta función)
- [ ] Encargado login → ve solo desvíos de su sucursal (FIX id_sucursal)
- [ ] Admin ve todo
- [ ] Bot sigue enviando notificaciones de auditoría a encargados (flujo existente)

### 15. Seguridad
- [ ] No hay hardcoded secrets en código
- [ ] Todas credenciales vienen de config.py (env vars)
- [ ] RLS policies en desvio_notificaciones funcionan:
  - [ ] Usuario solo ve notificaciones suyas
  - [ ] Usuario solo puede actualizar (marcar leída) las suyas
- [ ] Storage bucket `desvio-evidencias` tiene RLS:
  - [ ] Solo usuarios autenticados pueden subir
  - [ ] Solo usuarios autenticados pueden leer
- [ ] Validación en endpoints: no se puede notificar si no es auditor
- [ ] Signed URLs nunca exponen path crudo

### 16. Performance
- [ ] Polling de notificaciones cada 30s (no más frecuente)
- [ ] Índices en DB creados:
  - [ ] `idx_notif_user` en (user_id, leida)
  - [ ] `idx_notif_gestion` en (id_gestion)
- [ ] Queries usan índices apropiadamente

---

## 📊 Testing Funcional

### Scenario 1: Auditor notifica encargado
```
1. Auditor en /desvios/123 (estado=Abierta)
2. Click botón "Notificar al Encargado"
3. ✅ WhatsApp enviado al teléfono del encargado
4. ✅ Mensaje dice: "Tienes desvíos para rectificar"
```

### Scenario 2: Encargado responde con foto
```
1. Encargado recibe WhatsApp, responde al bot
2. Bot: "¿Cuál desvío? 1) [Alta] Temp congelador 2) [Media] Vencimientos"
3. Encargado: "1"
4. Bot: "¿Foto o descripción?"
5. Encargado: [sube foto de congelador reparado]
6. Bot: "✓ Recibida"
7. ✅ Foto guardada en desvio-evidencias/gestion/123/{uuid}.jpg
8. ✅ Evento creado en desvio_eventos (tipo='evidencia', origen='sucursal')
9. ✅ Notificación creada en desvio_notificaciones
```

### Scenario 3: Auditor ve respuesta
```
1. Auditor en /desvios/123
2. ✅ Navbar muestra 🔔 con badge "1"
3. Click bell → ve "Encargado respondió en Desvío #123"
4. Click → navega a /desvios/123
5. ✅ En timeline, ve evento nuevo con foto + "Encargado" badge
6. ✅ Badge desaparece (notificación marcada leída)
```

### Scenario 4: Encargado solo ve sus desvíos
```
1. Encargado A login (sucursal_id=10)
2. Bot: enumera 3 desvíos de sucursal 10
3. Encargado B login (sucursal_id=20)
4. Bot: enumera 2 desvíos de sucursal 20
5. ✅ Cada uno ve solo sus desvíos
```

---

## 🔍 Code Review Detallado

### Por archivo (si existe):

#### router.py
```python
# ✅ Verificar:
- Manejo async/await correcto
- Locks con async context managers
- No hay deadlocks potenciales
- Logs detallados
```

#### meta_client.py
```python
# ✅ Verificar:
- Manejo de timeouts
- Errores de Meta API manejados
- No hay leaks de tokens en logs
```

#### main.py
```python
# ✅ Verificar:
- Webhook signature validation intacta
- Deduplicación funcionando
- Async tasks no bloquean respuesta
```

#### Frontend TypeScript
```typescript
// ✅ Verificar:
- Sin 'any' types
- Todas funciones tipadas
- Imports/exports correctos
- No hay console.log de debug
```

---

## 📋 Checklist de Cierre

- [ ] Todos los archivos creados/modificados según plan
- [ ] No hay conflictos merge o archivos incompletos
- [ ] Migraciones SQL ejecutadas exitosamente
- [ ] Storage bucket creado y RLS activo
- [ ] 4 scenarios de testing completados
- [ ] 0 console.log de debug
- [ ] 0 hardcoded secrets
- [ ] Frontend compila sin errores TS
- [ ] Backend tests pasan (si existen)
- [ ] Ramas limpias: master lista para merge

---

## 🚨 Si algo no está bien

**Paso 1**: Documentar qué está mal exactamente
**Paso 2**: Crear issue con detalles
**Paso 3**: Pedir corrección a Codex o fix manualmente

---

**Fecha de revisión**: 2026-05-04
**Revisor**: Claude Code
**Estado**: En espera de cambios de Codex

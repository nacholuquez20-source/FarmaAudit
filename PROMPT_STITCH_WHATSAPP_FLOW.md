# Prompt para Stitch: Flujo WhatsApp + Frontend - FarmaAudit

## 🎯 Contexto Clave: El Flujo de Desvios vía WhatsApp

FarmaAudit tiene una arquitectura **hybrid WhatsApp + Web App** donde:

### ACTOR 1: Auditor (en WhatsApp)
1. Auditor entra a una sucursal y encuentra hallazgos
2. **Envía mensaje al bot**: "Medicamento ABC vencido en la vidriera"
3. Bot con Claude API parsea el mensaje y crea un **BORRADOR** de desvio
4. Auditor recibe respuesta con resumen (severidad, área, descripción)
5. Auditor confirma: "SI", "NO", o "EDITAR"
6. Si "SI" → Desvio se **CREA FORMALMENTE** y se notifica al responsable

### ACTOR 2: Responsable de Sucursal (en WhatsApp)
1. **Recibe notificación vía WhatsApp** del nuevo desvio asignado
2. Lee descripción, severidad, plazo
3. Inicia plan de acción (compras, capacitación, ajustes operacionales)
4. **Envía fotos como evidencia** del problema resuelto
5. Escribe descripción de la solución
6. Bot captura fotos y comentarios en el sistema

### ACTOR 3: Auditor (en App Web)
1. Entra a **Gestión de Desvios** → ve los desvios creados
2. Hace click en un desvio → abre **Detalles**
3. Ve:
   - Estado actual (Abierta, En Proceso, Resuelta, Cerrada)
   - Fotos enviadas por responsable vía WhatsApp
   - Comentarios y actualizaciones en tiempo real
   - Timeline de eventos
4. **Revisa evidencia y aprueba o rechaza**
5. Si aprueba → marca como **CERRADA**
6. Si rechaza → notifica responsable para que complete

---

## 📱 Flujo Técnico: De WhatsApp a Base de Datos a Web App

```
┌─────────────────────────────────────────────────────────────┐
│ AUDITOR (WhatsApp)                                          │
│ "Medicamento ABC vencido en vidriera"                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ AUDITBOT (Backend - main.py)                                │
│ ├─ Recibe mensaje                                           │
│ ├─ Claude Parser: extrae área, descripción, severidad       │
│ ├─ Crea BORRADOR en Supabase                                │
│ ├─ Responde al auditor con preview                          │
│ └─ Espera SI/NO/EDITAR                                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼ (SI)                    ▼ (NO)
    ┌─────────────────┐       ┌─────────────────┐
    │ Crea GESTION    │       │ Descarta        │
    │ en Supabase     │       │ BORRADOR        │
    │ y notifica      │       │                 │
    │ responsable     │       └─────────────────┘
    └────────┬────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│ RESPONSABLE DE SUCURSAL (WhatsApp)                          │
│ "Tu desvio: Medicamento ABC vencido. Plazo: 24h"          │
│ [Botón] Ver detalles                                        │
│                                                              │
│ Responsable:                                                │
│ - Lee descripción y plazo                                   │
│ - Inicia trabajo correctivo                                 │
│ - Envía FOTO 1: "Problema encontrado"                       │
│ - Envía FOTO 2: "Medicamento retirado"                      │
│ - Comenta: "Problema resuelto. Verificado stock"            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ BACKEND (Supabase)                                          │
│ ├─ Recibe fotos vía Meta Cloud API                          │
│ ├─ Descarga y guarda en Google Drive                        │
│ ├─ Crea EVENTOS en tabla `Eventos` (tipo: "evidencia")      │
│ ├─ Actualiza estado GESTION → "En_proceso"                  │
│ └─ Genera notificación para auditor                         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ AUDITOR (Web App - /desvios/:id)                           │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ Estado: 🟠 EN PROCESO                                │   │
│ │ Severidad: 🔴 Alta                                   │   │
│ │ Plazo: 24h (Vence en 12h)                            │   │
│ ├──────────────────────────────────────────────────────┤   │
│ │ [Responsable] Juan M. - Farmacia Centro              │   │
│ │ [Teléfono] +54 9 11 2345 6789                        │   │
│ │ [Sucursal] Centro Histórico - 004                    │   │
│ ├──────────────────────────────────────────────────────┤   │
│ │ TIMELINE:                                            │   │
│ │ • Desvio creado (hace 2h)                            │   │
│ │ • Juan marcó como "En_proceso" (hace 1h)             │   │
│ │ • Fotos recibidas (hace 15 min) [Ver fotos]          │   │
│ │ • Comentario: "Problema resuelto..."                 │   │
│ ├──────────────────────────────────────────────────────┤   │
│ │ EVIDENCIAS:                                          │   │
│ │ [Foto 1] medicamento-vencido.jpg                     │   │
│ │ [Foto 2] medicamento-retirado.jpg                    │   │
│ ├──────────────────────────────────────────────────────┤   │
│ │ CHAT INTERNO:                                        │   │
│ │ Auditor: "¿Verificaron todo el stock?"               │   │
│ │ Juan (via bot): "Si, stock verificado y ok"          │   │
│ ├──────────────────────────────────────────────────────┤   │
│ │ [✓ Resolver] [✗ Rechazar] [💬 Comentar]             │   │
│ └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 📋 Tabla: Estados y Transiciones de un Desvio

| Estado | Quién lo hace | Acción | Siguiente Estado | Notificación |
|--------|---------------|--------|------------------|--------------|
| **Borrador** | Auditor (confirma en WA) | "SI" en bot | Abierta | Responsable notificado vía WA |
| **Abierta** | Responsable (en WA) | Inicia trabajo | En_proceso | Auditor ve actualización en app |
| **En_proceso** | Responsable (en WA) | Envía fotos + comentario | Resuelta (espera aprobación) | Auditor recibe notificación |
| **Resuelta** | Auditor (en app web) | Revisa y aprueba | Cerrada | Responsable notificado en WA |
| **Cerrada** | Sistema | Resuelto ✅ | - | Ambos tienen registro final |
| **Rechazada** | Auditor (en app web) | "No cumple" | Abierta (de nuevo) | Responsable notificado, vuelve a trabajar |

---

## 🎨 Componentes Frontend Necesarios para este Flujo

### 1. **Chat/Conversación integrada** (Detalles Desvio)
**Props:**
- `idGestion`: string
- `eventos`: Array<{tipo, comentario, actor, timestamp, metadata}>
- `onNewMessage`: callback

**Renderiza:**
- Mensajes del auditor (azul, derecha)
- Mensajes del responsable via bot (gris, izquierda)
- Fotos recibidas (inline, galería)
- Timestamps relativos ("hace 15 min")
- Avatares con iniciales
- Input para auditor comentar (si es auditor)

**Ejemplo:**
```
┌─────────────────────────────────┐
│ Chat - Desvio FAR-001           │
├─────────────────────────────────┤
│                                 │
│ JM - Juan M.                    │
│ "Iniciamos trabajo hoy"         │
│ Hace 1 hora                     │
│                                 │
│                      Tú (Auditor)
│              "¿Ya tienen las fotos?"
│              Hace 15 min         │
│                                 │
│ JM - Juan M.                    │
│ [Foto 1] medicamento-vencido    │
│ [Foto 2] medicamento-retirado   │
│ "Problema resuelto"             │
│ Hace 5 min                      │
│                                 │
├─────────────────────────────────┤
│ [Escribe algo...............] ↑ │
└─────────────────────────────────┘
```

### 2. **Galería de Evidencias/Fotos**
**Props:**
- `eventos`: Array (filtrar por tipo: "evidencia")
- `onPhotoClick`: (url) => void

**Renderiza:**
- Grid de fotos thumbnail
- Click → abre lightbox
- Metadatos: actor, timestamp, descripción si existe

### 3. **Badge de Estado Dinámico**
**Props:**
- `estado`: "Abierta" | "En_proceso" | "Resuelta" | "Cerrada"
- `tiempoRestante`: Date | null
- `tiempoVencido`: boolean

**Renderiza:**
```
┌──────────────────────────────────┐
│ 🟠 EN PROCESO                    │
│ Plazo: 24h (Vence en 12h 30m)    │ ← Actualiza cada minuto
│ Responsable activo ✓              │
└──────────────────────────────────┘
```

### 4. **Timeline de Eventos**
**Props:**
- `eventos`: Array<{id, tipo, timestamp, comentario, actor_nombre, metadata}>

**Tipos de eventos:**
- `creacion` → "Auditor creó desvio"
- `estado_cambio` → "Cambió a En_proceso"
- `evidencia` → "Fotos recibidas" (link a foto)
- `contacto` → "Contacto enviado por WhatsApp"
- `respuesta` → "Responsable respondió"
- `cierre` → "Desvio cerrado"
- `rechazo` → "Desvio rechazado"

**Ejemplo:**
```
════════════════════════════════════
║ 📅 TIMELINE                        ║
════════════════════════════════════
  ●━━ Juan M. creó desvio            
      Hace 3 días                    
                                     
  ●━━ Juan M. envió fotos            
      Medicamento ABC retirado       
      Hace 1 día                     
      [Ver foto 1] [Ver foto 2]      
                                     
  ●━━ Auditor: Revisar bien          
      Hace 12h                       
                                     
  ●━━ Desvio RESUELTO ✓              
      Por: Auditor María             
      Hace 1h                        
════════════════════════════════════
```

### 5. **Botones de Acción Contextuales**

Según el estado y el rol:

**Si Auditor + Estado: Resuelta**
```
┌──────────────────────────────────┐
│ [✓ Aprobar Resolución]           │
│ [✗ Rechazar y Reabrí]            │
│ [💬 Pedir más info]              │
└──────────────────────────────────┘
```

**Si Responsable + Estado: Abierta/En_proceso**
```
┌──────────────────────────────────┐
│ [📷 Subir fotos]                 │
│ [💬 Comentar]                    │
│ [☎️ Contactar Auditor por WA]     │
└──────────────────────────────────┘
```

### 6. **Notificación de Cambios Real-Time**
**Funcionalidad:**
- Cuando responsable envía foto vía WA → toast notifica auditor
- Cuando auditor aprueba → responsable ve notificación en app o WA
- Sonido opcional (configurable)

**Ejemplo:**
```
┌─────────────────────────────────┐
│ 📸 Nuevas fotos en FAR-001       │
│ Juan M. envió evidencia         │
│ [Ver] [Descartar]               │
└─────────────────────────────────┘
```

### 7. **Panel de Gestión (Lista Desvios)**
**Agregar columnas/información:**
- **Estado**: Abierta | En_proceso | Resuelta | Cerrada (coloreado)
- **Evidencia**: ✓ (si tiene fotos) o ✗
- **Última actualización**: "hace 15 min" (actualiza en tiempo real)
- **Responsable**: Nombre del que respondió
- **Acciones rápidas**: 
  - Click → Abre detalles
  - Menú 3-puntos: Reasignar, Rechazar, Enviar recordatorio

**Ejemplo fila mejorada:**
```
┌────┬───┬──────────┬────────────┬────────────────┬─────────────┐
│    │ # │ Severid. │ Estado     │ Evidencia      │ Hace        │
├────┼───┼──────────┼────────────┼────────────────┼─────────────┤
│ ☑  │FAR│ 🔴 Alta  │ 🟠 Proceso │ ✓ 2 fotos     │ 15 min      │
│    │001│ (24h)    │            │ [Ver]          │             │
│    │   │ Medicina │ Juan M.    │ Hace 15 min    │             │
│    │   │ vencida  │            │                │             │
└────┴───┴──────────┴────────────┴────────────────┴─────────────┘
```

---

## 📲 Integración Específica WhatsApp → Frontend

### A. Fotos enviadas vía WhatsApp
**Flujo:**
1. Responsable envía foto en WA al bot
2. Meta Cloud API → Backend recibe
3. Backend descarga y guarda en Google Drive
4. Backend crea evento tipo "evidencia" en Supabase
5. Frontend detecta cambio (query con polling o WebSocket)
6. **Aparece automáticamente en la galería**

**UI Consideration:**
- Mostrar "Foto cargándose..." mientras se descarga
- Si falla, mostrar "Error al cargar foto" con retry
- Timestamp exacto de cuándo se recibió

### B. Comentarios vía WhatsApp
**Flujo:**
1. Responsable escribe mensaje en WA
2. Backend parsea como evento tipo "respuesta"
3. Frontend renderiza en chat con avatar de responsable
4. **No editable**, solo lectura para auditor

### C. Notificaciones bidireccionales
**Auditor → Responsable:**
- Auditor escribe en app → Se convierte a notificación WA
- Ejemplo: "Auditor dice: ¿Verificaste stock?"
- Backend envia via Meta API

**Responsable → Auditor:**
- Responsable manda foto en WA → Auditor recibe notificación en app
- Toast: "Juan M. envió 2 fotos en FAR-001"

---

## 🔄 Estados Finales de Un Desvio (Para Mostrar)

```
ESTADO: ABIERTA
├─ El desvio fue creado pero responsable no ha iniciado
├─ Auditor puede: Contactar, Enviar recordatorio, Cerrar forzadamente
└─ SLA: Activo, cuenta hacia abajo

ESTADO: EN_PROCESO
├─ Responsable inició trabajo
├─ Esperando evidencia (fotos)
├─ Auditor puede: Comentar, Pedir más info, Rechazar
└─ SLA: En riesgo si queda poco tiempo

ESTADO: RESUELTA
├─ Responsable envió fotos y solución
├─ Esperando validación de auditor
├─ Auditor puede: Aprobar (→ Cerrada) o Rechazar (→ Abierta)
└─ SLA: Crítico, auditor debe actuar rápido

ESTADO: CERRADA
├─ Desvio validado y aprobado
├─ Responsable recibió confirmación
├─ Archivo completado
└─ Solo visualización, sin cambios
```

---

## 💡 Consideraciones de Diseño

### Performance
- **Real-time updates**: Usar Supabase real-time subscriptions en lugar de polling
- **Foto preview**: Thumbs pequeños en lista, full size en click
- **Lazy load**: Cargar fotos solo cuando se expande desvio

### Mobile (WhatsApp View)
- Responsable accede desde WhatsApp (link o bot menu)
- Vista debe ser mobile-first
- Botones grandes y claros para acciones (Enviar foto, Comentar)

### Accesibilidad
- Colores no solo para estado (rojo/verde) → agregar iconos (🔴🟠🟢)
- Contraste suficiente para legibilidad
- Labels claros para botones

### Mensajería
- Timestamps: "Hace 15 minutos" (relativo) + hover muestra "3 Jun 2026 14:30 UTC"
- Actor nombre: Mostrar siempre quién hizo qué
- Tono: Profesional pero amable

---

## 📦 Resumen de Funcionalidades Clave

✅ **Chat integrado** con mensajes de responsable vía WhatsApp
✅ **Galería de fotos** que se actualiza en tiempo real
✅ **Timeline visual** de todos los eventos
✅ **Estado dinámico** con SLA/plazo restante
✅ **Notificaciones** cuando hay nuevas evidencias
✅ **Botones contextuales** (Aprobar/Rechazar/Pedir info)
✅ **Responsable info** (nombre, teléfono, sucursal)
✅ **Contacto rápido** (WhatsApp direct link con pre-filled message)
✅ **Historial completo** de lo que pasó
✅ **Mobile-responsive** para ver desde WhatsApp

---

## 🎯 Deliverables Esperados

1. **DetailDesvio Component mejorado** 
   - Layout moderno con 3 columnas
   - Chat funcional integrado
   - Fotos en galería deslizable
   
2. **Componentes reutilizables**
   - `<ChatMessage />` - mensaje individual
   - `<PhotoGallery />` - galería de fotos
   - `<Timeline />` - timeline de eventos
   - `<EstadoBadge />` - badge de estado con SLA
   
3. **DesviosList mejorada**
   - Filas con información actualizada
   - Indicador de "nuevas fotos"
   - Acciones contextuales
   
4. **Real-time subscriptions**
   - Integración Supabase para cambios en tiempo real
   - Notificaciones toast cuando llegan fotos
   
5. **Responsive mobile**
   - Vista funcional en teléfono
   - Fotos se ven bien en cualquier tamaño

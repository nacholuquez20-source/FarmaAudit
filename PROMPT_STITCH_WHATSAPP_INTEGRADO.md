# Prompt Mejorado para Google Stitch - FarmaAudit con Flujo WhatsApp

Copia este prompt completo a Google Stitch/AI Studio para la siguiente iteración del diseño.

---

# FarmaAudit - Sistema de Gestión de Auditorías + Flujo WhatsApp Integrado

## Misión
Crear un sistema profesional de gestión de auditorías de farmacia que integre perfectamente dos canales: **WhatsApp para campo** (auditores y responsables), **Web App para gestión** (auditores, responsables, admin).

## Visión del Producto
Auditoría continua en tiempo real: auditor envía desvío vía WhatsApp → bot lo valida → responsable de sucursal recibe notificación → responde con fotos → auditor aprueba en web app. Todo en horas, no semanas.

---

## 🏗️ ARQUITECTURA DEL FLUJO

### El Viaje de un Desvío (3 Pasos)

#### PASO 1️⃣: AUDITOR Registra en WhatsApp
```
Timeline:
• Auditor en sucursal: "Medicamento XYZ vencido en vidriera sector D"
  ↓
• Bot (Claude API) parsea: severidad="Alta", area="Vencimientos", sucursal="PLA-001"
  ↓
• Bot propone: "¿Crear desvío: Vencimiento crítico? [SI] [NO]"
  ↓
• Auditor: "SI"
  ↓
• Desvío CREADO (estado: ABIERTA)
  ↓
• Responsable PLA-001 NOTIFICADO automáticamente por WhatsApp
```

Result: Desvío FAR-2847 abierto, responsable en alerta.

---

#### PASO 2️⃣: RESPONSABLE Responde en WhatsApp
```
Timeline:
• Responsable recibe: "Desvío FAR-2847: Medicamento XYZ vencido..."
  ↓
• Inicia plan de acción dentro de 24h (SLA)
  ↓
• Responsable: [📷 Subir foto] → envía 2-3 fotos de la solución
  ↓
• Responsable: "Problema resuelto. Stock verificado, medicamento retirado."
  ↓
• Estado: ABIERTA → EN_PROCESO → RESUELTA
  ↓
• AUDITOR NOTIFICADO: "Nuevas fotos en FAR-2847"
```

Result: Fotos almacenadas en Google Drive, evento "evidencia" creado en BD.

---

#### PASO 3️⃣: AUDITOR Valida en App Web
```
Timeline:
• Auditor abre app: ve toast "Juan López enviado 2 fotos en FAR-2847"
  ↓
• Click en desvío → abre detalles
  ↓
• Ve la galería de fotos en orden cronológico
  ↓
• Lee comentarios + plan de acción realizado
  ↓
• Aprueba: "Cerrada ✅" O Rechaza: "Necesita revisión"
  ↓
• Si rechaza → responsable recibe mensaje en WhatsApp
  ↓
• Si aprueba → Estado: RESUELTA → CERRADA
  ↓
• RESPONSABLE NOTIFICADO: "Desvío FAR-2847 aprobado y cerrado"
```

Result: Ciclo completo en ~2 horas vs 2-3 semanas antes.

---

## 👥 ROLES y PERMISOS

| Rol | WhatsApp | Web App | Permisos |
|-----|----------|---------|----------|
| **Auditor** | Crear desvios, consultar | Gestionar, revisar, aprobar | Todo excepto admin |
| **Responsable** | Recibir y responder | Ver propios desvios, subir fotos | Solo lectura propia |
| **Admin** | — | Gestionar usuarios, permisos, audit log | Todo |

---

## 🎨 PALETA DE COLORES (Plazoleta branding)

```
Primario (Navy):       #1E3A6D  ← Profesional, confianza
Complementario (Naranja): #F15A29  ← Urgencia, CTAs
Éxito (Verde):         #2A9D5F  ← Aprobado, cerrado
Advertencia (Amarillo): #D97706  ← En proceso, vencimiento próximo
Error (Rojo):          #DC2626  ← Vencido, crítico

Neutros: Grises 50-950 (escala Tailwind)
```

---

## 📱 PANTALLAS PRINCIPALES

### 1. LOGIN (/login)
**Usuarios:** Todos (antes de autenticar)

**Componentes:**
- Fondo gradiente: navy → naranja
- Card centrada (380px ancho en desktop)
- Logo Plazoleta (64x64)
- Email + Password con validación en vivo
- "¿Olvidaste contraseña?" link
- Error messages con icono
- Loading state con spinner

**UX:**
- Tab key navega entre campos
- Enter submite
- Checkmark animado en validaciones
- Password toggle visibility

---

### 2. DASHBOARD (/dashboard)
**Usuarios:** Admin (visión total), Sucursal (solo su resumen)

**Hero Section:**
```
┌──────────────────────────────────────┐
│ ¡Bienvenido, Marina!                 │
│ Desvios vencidos: 2 · Críticos: 1    │
│                                      │
│ [⏰] 12h para vencer: 5 desvios      │
└──────────────────────────────────────┘
```

**KPI Cards (Degradado por severidad):**
- Registros colectados: 44 (azul)
- En proceso: 12 (naranja)
- Críticos vencidos: 3 (rojo)
- Tasa cierre 30d: 94% (verde)

**Gráficos Recharts:**
- Tendencia 30d: línea (desvios creados vs cerrados)
- Distribución por severidad: pastel
- Por estado: barras horizontales

**Supervision Sucursales (Admin only):**
- Cards "health status" tipo semáforo
- Rojo: >8 desvios abiertos
- Amarillo: 4-8 desvios
- Verde: <4 desvios
- Últimas 3 sucursales "en alerta" destacadas

---

### 3. GESTIÓN DESVIOS (/gestion-desvios)
**Usuarios:** Auditor, Admin

**Sidebar Filtros (Colapsable):**
```
┌─ FILTROS
│ ☐ Estado
│   ☑ Abierta (17)
│   ☑ En proceso (12)
│   ☑ Resuelta (5)
│   ☐ Cerrada
│
│ ☐ Severidad
│   ☑ Alta (8)
│   ☑ Media (15)
│   ☐ Baja (11)
│
│ ☐ Sucursal
│   (search + list)
│
│ [Clear all]
```

**Tabla/Lista:**
- Chips removibles de filtros activos
- Búsqueda en tiempo real (por ID, descripción)
- Barra de severidad izquierda (coloreada)
- Row expansion: click muestra preview sin navegar
- Hover effect: sombra + fondo gris suave
- Badges: estado + severidad
- Menú 3-puntos: ver, editar, reasignar, cerrar
- Checkboxes para batch actions

**Acciones:**
- [✓ Marcar varias en proceso]
- [🔗 Contactar por WA]
- [📄 Exportar]

---

### 4. DETALLES DESVIO (/desvios/:id) ⭐ CENTRAL
**Usuarios:** Auditor (full), Admin (full), Responsable (read-only)

**LAYOUT 3 COLUMNAS:**

```
┌─────────────────────────────────────────────────────────┐
│ ◄ FAR-2847 | VENCIDA | 5h vence | [🔗 WA] [✓ Aprobar]  │
├──────────────┬──────────────────────┬───────────────────┤
│              │                      │                   │
│  LEFT        │    CENTER            │      RIGHT        │
│  (280px)     │    (flex)            │      (320px)      │
│              │                      │      sticky       │
├──────────────┼──────────────────────┼───────────────────┤
```

#### LEFT SIDEBAR:
```
📌 SUCURSAL
  Plazoleta Centro (PLA-001)
  Av. Corrientes 1430, CABA
  [Foto: 🏢]

⚠️ SEVERIDAD
  Alta | Vencimientos

📋 PLAN DE ACCIÓN
  ▼ Retirar medicamentos vencidos
    Verificar stock físico
    Reportar al proveedor

👤 RESPONSABLE
  Juan López
  📞 +54 9 11 5555-1010
  Encargado de turno

⏱️ TIMELINE ESTADO
  ── Abierta (5/5 10:00)
  ── En proceso (5/5 11:30)
  → Resuelta (5/5 13:45) [conectando a auditor]
  
  SLA: -5h (VENCIDA) ⚠️
```

#### CENTER AREA (TABS):

**TAB 1: CHAT INTEGRADO** (Default)
```
Conversación en tiempo real:

[💬] Auditor: "Necesito fotos del stock actual"
      10:15

[💬] Responsable: "Enviando fotos ahora"
      11:30
      
[📷] 3 fotos: Stock verificado
      Metadata: Juan L. · 11:32 · "Medicamentos retirados"
      
      [thumbnail] [thumbnail] [thumbnail]
      Click → Lightbox

[💬] Auditor: "Perfecto, está ok"
      13:45
      
[Input] Escribir comentario...
         [Enviar]
```

**Features:**
- Avatares circulares (iniciales + color por role)
- Timestamp relativo ("hace 2h")
- Fotos inline con preview
- Click foto → lightbox en grande
- Skeleton loading mientras carga chat
- Real-time: nuevos mensajes aparecen sin refrescar
- Toast: "Nuevas fotos en FAR-2847"

**TAB 2: GALERÍA DE EVIDENCIAS**
```
[Card 1]              [Card 2]              [Card 3]
[Imagen]              [Imagen]              [Imagen]
Subida por: Juan L.   Subida por: Auditor  ...
11/05 13:45           11/05 14:00
"Stock verificado"    "Antes: estado"

Metadata completa al click:
• Fecha/Hora exacta
• Quién subió
• Descripción
• Full-size lightbox
```

**TAB 3: TIMELINE VISUAL**
```
⚫ ─── Desvío creado: FAR-2847
      Auditor: Juan Pérez · 11:05 · Vencimientos

⚫ ─── Estado: En proceso
      Responsable: Juan López · 11:30

⚫ ─── Evidencia: 3 fotos
      Juan López · 13:45 · "Stock verificado"
      [Ver fotos ↗️]

⚫ ─── Comentario auditor
      Auditor: Juan Pérez · 14:15 · "Excelente"

→ ⚫ Estado: Resuelta → Cerrada
      (En espera de aprobación)
```

**TAB 4: DETALLE**
```
ID:              FAR-2847
Área:            Vencimientos
Sucursal:        PLA-001 Plazoleta Centro
Responsable:     Juan López
Zona:            CABA
Severidad:       Alta
Estado:          Resuelta
Plazo:           05/05 (VENCIDA -5h)
Creado:          05/05 10:00
Plan de acción:  Retirar medicamentos vencidos...
```

#### RIGHT PANEL (Sticky):

**Si estado = RESUELTA:**
```
✅ APROBAR COMO CERRADO

El responsable propone:
  ✓ Medicamentos retirados
  ✓ Stock verificado
  ✓ Reportado a proveedor

[✓ Aprobar] [✗ Rechazar]
```

**Si estado = ABIERTA o EN_PROCESO:**
```
⏱️ ACCIONES RÁPIDAS

[💬 Comentar]
[☎️ Contactar por WA]
[📷 Subir evidencia]
[⏹️ Marcar en proceso]

Plazo: 24h
Vence: 05/05 10:00 (-5h) ⚠️
```

---

### 5. MIS DESVIOS (/mis-desvios)
**Usuarios:** Responsable de sucursal

**Hero:**
```
Tu responsabilidad: 5 desvios activos
Vencidos: 2 · En plazo: 3

Comenzar a resolver ▶
```

**Cards grandes (mobile-first):**
```
┌─────────────────────────┐
│ FAR-2847                │
│ Vencimientos (VENCIDA) │
│ Medicamentos en vidriera│
│                         │
│ Plazo: -5h | Crítico 🔴│
│                         │
│ [💬 Ver detalles] [+]  │
└─────────────────────────┘
```

Quick filters: [Abiertos] [En plazo] [Vencidos] [Resueltos]

---

### 6. REVISION DESVIOS (/revision-desvios)
**Usuarios:** Auditor (para revisar borradores de otros auditores)

**Side-by-side:**
```
┌─────────────────┬─────────────────┐
│ PROPUESTO       │ ORIGINAL         │
├─────────────────┼─────────────────┤
│ Severidad: Alta │ Severidad: Alta │ ✓
│ Área: Vencim.   │ Área: Vencim.   │ ✓
│ Desc: "Medic..." │ Desc: "Medic..." │ ✓
│                 │                 │
│ [Aprobar] [Rechazar con motivo]   │
└─────────────────┴─────────────────┘
```

---

### 7. SUCURSALES (/sucursales)
**Usuarios:** Admin, Auditor

**Listing Grid (2-3 cols):**
```
┌────────────────┐
│ [🏢 Foto]      │
│ PLA-001        │
│ Plazoleta Cba  │
│ CABA · 🔴 Rojo │
│ 8 desvios      │
│ Encargado: J.L │
│ [Ver detalle]  │
└────────────────┘
```

**Detalle Sucursal (/sucursales/:id):**
```
[🏢 Hero foto]
Plazoleta Centro
Av. Corrientes 1430, CABA

4-CARD KPI:
[Abiertos: 8] [En proceso: 3] [Resueltos: 12] [Cerrados: 34]

RESPONSABLES:
• Juan López | 📞 +54 9 11 5555-1010 | Encargado
• María García | 📞 ... | Farmacéutica

DESVIOS RECIENTES:
[Tabla filtrable]

TIMELINE AUDITORÍAS:
[05/05 10:00] Auditoría de campo - Juan Pérez
[04/05 14:30] Auditoría de campo - Carla M.
```

---

### 8. ADMIN PANEL (/admin)
**Usuarios:** Admin only

**Sidebar Nav:**
```
👥 Usuarios
📋 Permisos
📊 Audit log
⚙️ Configuración
```

**Usuarios Tab:**
- Tabla: nombre, email, rol, sucursal, estado
- Search + filter
- Agregar usuario [+]
- Bulk: Activar/Desactivar
- Row actions: Editar, resetear password, eliminar

**Permisos Tab:**
- Role selector
- Grid de módulos:
  * ☑️ Ver desvios
  * ☑️ Crear desvios
  * ☑️ Aprobar desvios
  * ☑️ Ver sucursales
  * ☑️ Gestionar usuarios
- Copy from role shortcut

---

## 🎯 COMPONENTES REUTILIZABLES (Design System)

### Botones
```
ButtonPrimary    → Navy, rounded-lg, hover shadow
ButtonSecondary  → Gray border, ghost
ButtonDanger     → Red
ButtonGhost      → No background, hover underline
IconButton       → Solo ícono, 44x44px
```

### Badges
```
SeveridadBadge   → Alta/Media/Baja con dot + color
EstadoBadge      → Abierta/En proceso/Resuelta/Cerrada
SlaPill          → Overdue/Today/Soon/OK/Closed
StatusDot        → Indicador circular simple
```

### Containers
```
Card             → White, border gray-200, rounded-lg
CardHover        → Card + hover shadow-lg
Panel            → Sticky sidebar panel
Modal            → Backdrop blur, fade animation
Drawer           → Slide from right/left
```

### Inputs
```
InputField       → Border rounded-lg, ring on focus
TextArea         → Similar, múltiples líneas
Select           → Dropdown custom
SearchInput      → Con clear button
FileUpload       → Drag & drop area
```

### Feedback
```
EmptyState       → SVG + headline + CTA
LoadingState     → Skeleton screens (no spinner)
ErrorState       → Icono rojo + mensaje + retry
Toast            → Sonner style, bottom-right
```

### Media
```
ChatMessage      → Bubble style, avatar, timestamp
PhotoGallery     → Grid + lightbox modal
Timeline         → Vertical con dots y líneas
Avatar           → Inicial + color por role
```

---

## 📐 RESPONSIVE DESIGN

### Breakpoints (Tailwind)
- xs (0px) → Mobile pequeño
- sm (640px) → Mobile
- md (768px) → Tablet
- lg (1024px) → Desktop
- xl (1280px) → Desktop grande

### Mobile-First Adaptations
- Tablas → Cards
- Sidebar → Drawer/collapse
- 3 columnas → Stack vertical
- Lightbox → Full screen
- Touch targets: mínimo 44x44px
- Dropdowns → Modal en mobile

---

## ⚡ ANIMACIONES

```css
Button hover:    scale(1.02) + shadow, 150ms
Card hover:      translateY(-2px), 200ms
Page enter:      fade-in, 300ms
Modal:           scale + fade, 300ms
Toast:           slide-in from bottom, 200ms
Loader spinner:  rotation smooth, infinite
Pulse avatar:    opacity pulse on new message
```

---

## 🔄 REAL-TIME FEATURES (CRÍTICO)

1. **Chat en vivo:**
   - Nuevos mensajes aparecen sin refrescar
   - Indicador "typing..."
   - Sonido/notificación al llegar mensaje

2. **Fotos en vivo:**
   - Nueva foto aparece en galería <3s
   - Toast notification: "Juan López enviò 2 fotos"
   - Lightbox se actualiza automáticamente

3. **Estado en vivo:**
   - Cambio de estado en tiempo real
   - Timeline se actualiza
   - Badged color cambio

4. **Notificaciones:**
   - Toast: "FAR-2847 marcada como resuelta"
   - Toast: "Nuevas fotos en FAR-2847"
   - Sound: ding suave (optional)
   - Desktop notification: si está minimizado

---

## 📊 DATOS MOCK PARA PROTOTIPO

### Desvios (20+ ejemplos)
```
{
  id: "FAR-2847",
  desvio: "Medicamento XYZ vencido en vidriera",
  sucursal: "Plazoleta Centro",
  sucursalCod: "PLA-001",
  severidad: "Alta",
  estado: "Resuelta",
  responsable: "Juan López",
  tel: "+54 9 11 5555-1010",
  plazo: "2026-05-05T10:00:00",
  creado: "2026-05-05T10:00:00",
  eventos: 7,
  planAccion: "Retirar medicamento vencido",
  rolResponsable: "Encargado"
}
```

### Sucursales (6+ ejemplos)
```
{
  id: "PLA-001",
  nombre: "Plazoleta Centro",
  zona: "CABA",
  direccion: "Av. Corrientes 1430",
  responsable: "Juan López",
  tel: "+54 9 11 5555-1010",
  semaforo: "rojo",
  abiertos: 8,
  enProceso: 3,
  resueltos: 12,
  cerrados: 34
}
```

### Usuarios (5+ ejemplos)
```
{
  id: "user-001",
  nombre: "Marina Ramírez",
  email: "marina@plazoleta.com.ar",
  rol: "admin",
  sucursal: null
}
```

---

## ✅ TESTING CHECKLIST

- [ ] Login funciona, persiste sesión en localStorage
- [ ] Dashboard carga en <2s, KPIs actualizados
- [ ] Búsqueda de desvios es rápida (debounced)
- [ ] Chat: nuevo mensaje aparece sin refrescar
- [ ] Fotos: nueva evidencia aparece en galería <3s
- [ ] Timestamps relativos se actualizan ("hace 2h")
- [ ] Lightbox: abre, cierra, navega entre fotos
- [ ] Estados: cambio reflejado en tiempo real
- [ ] Notificaciones toast: aparecen y desaparecen
- [ ] Mobile: todo es tocable, legible, responsive
- [ ] Accesibilidad: colores + iconos, no solo color
- [ ] Performance: LCP < 2.5s, CLS < 0.1

---

## 🎨 ASPECTOS VISUALES CRÍTICOS

1. **Profundidad visual:**
   - Cards con sombra suave (shadow-sm)
   - Hover: sombra más profunda (shadow-lg)
   - Layers: background claro, foreground oscuro

2. **Tipografía:**
   - Headlines: Bold, letter-spacing +0.5px
   - Body: Regular, line-height 1.6
   - Small: 12px para metadata, timestamps

3. **Espaciado:**
   - Container max-width: 7xl (80rem)
   - Gutters: px-4 sm:px-6 lg:px-8
   - Gaps: gap-4, gap-6, gap-8
   - Padding cards: p-4 sm:p-6

4. **Colores de estado:**
   - Abierta: azul claro (E0EAFF)
   - En proceso: naranja claro (FFF1E6)
   - Resuelta: verde claro (E7F6EC)
   - Cerrada: gris claro (F1F4F9)
   - Vencida: rojo claro (FEE2E2)

---

## 🚀 PRIORIZACIÓN

**Tier 1 (MVP - Semana 1-2):**
- ✅ Login + Auth
- ✅ Dashboard con KPIs
- ✅ Gestión desvios tabla/filtros
- ✅ Desvio detail con chat + fotos
- ✅ Timeline visual
- ✅ Real-time updates (Supabase)
- ✅ Responsive mobile

**Tier 2 (Semana 3):**
- ✅ Sucursales detail
- ✅ Mis desvios (responsable view)
- ✅ Revision desvios (auditor)
- ✅ Notifications toast
- ✅ Dark mode prep

**Tier 3 (Polish):**
- ✅ Advanced animations
- ✅ Performance optimization
- ✅ Audit log
- ✅ Reportes

---

## 🎯 ÉXITO SE MIDE POR

✅ **Tiempo de ciclo:** Desvío abierto → cerrado en <4 horas  
✅ **Satisfacción responsables:** Chat + fotos intuitivos, <2 clics  
✅ **Auditor efficiency:** Ver detalles completos sin saltar entre tabs  
✅ **Mobile-ready:** Funciona bien desde celular en campo  
✅ **Real-time:** Actualizaciones <3 segundos  
✅ **Profesional:** Diseño premium, tokens consistentes  

---

## 📝 ENTREGABLES ESPERADOS

1. **Diseño completo:**
   - Figma con todas las pantallas
   - Component library documented
   - Color system + typography scale
   - Responsive breakpoints

2. **Prototipo funcional:**
   - React 19 + TypeScript
   - Todos los componentes working
   - Integración Supabase real-time
   - Mobile responsive
   - No cambios backend (API compatible)

3. **Code quality:**
   - TypeScript strict mode
   - ESLint + Prettier configured
   - Test coverage >80%
   - Performance: LCP <2.5s

---

**¡Listo para pasar a Stitch! Este prompt cubre todo lo que necesitan: diseño, flujo WhatsApp integrado, componentes, tokens, responsividad y real-time.**

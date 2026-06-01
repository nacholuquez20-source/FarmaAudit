# Prompt para Google AI Studio - FarmaAudit UI

Copia todo el texto debajo en el prompt de AI Studio y ejecuta.

---

# FarmaAudit - Sistema de Auditoría de Farmacias con Integración WhatsApp

Eres un diseñador UI/UX experto en crear interfaces profesionales para sistemas empresariales. Debes diseñar una aplicación web completa llamada **FarmaAudit** que gestiona auditorías de calidad en 23 farmacias.

## Contexto del Negocio

FarmaAudit es un sistema que integra:
- **WhatsApp**: Auditores registran hallazgos, responsables responden con fotos
- **Web App**: Gestión, revisión y aprobación de desvíos

El flujo es: Auditor envía desvío por WhatsApp → Bot parsea → Responsable responde con fotos → Auditor aprueba en web app.

## Roles

1. **Auditor**: Crea desvíos en WhatsApp, gestiona y aprueba en web app
2. **Responsable de Sucursal**: Recibe notificaciones, responde con fotos en WhatsApp, ve progreso en app
3. **Admin**: Visión completa, gestiona usuarios y permisos

## Paleta de Colores (Branding Plazoleta)

- **Primario (Navy)**: #1E3A6D
- **Secundario (Naranja)**: #F15A29
- **Éxito (Verde)**: #2A9D5F
- **Advertencia (Ámbar)**: #D97706
- **Error (Rojo)**: #DC2626
- **Neutros**: Grises Tailwind (50-950)

## Estados de un Desvío

```
ABIERTA (azul) → EN_PROCESO (naranja) → RESUELTA (verde) → CERRADA (gris)
VENCIDA (rojo) = cuando pasó el plazo
```

## Severidad

- **Alta**: #DC2626 (rojo)
- **Media**: #D97706 (ámbar)
- **Baja**: #0EA5E9 (azul claro)

---

# PANTALLAS A DISEÑAR

## 1. LOGIN (/login)

**Descripción**: Página de autenticación elegante y profesional.

**Componentes**:
- Fondo: Gradiente navy (#1E3A6D) → naranja (#F15A29)
- Círculos decorativos sutiles en las esquinas (opacity 0.08)
- Card blanca centrada (380px ancho en desktop)
- Logo Plazoleta (64x64, en cuadrado blanco)
- Texto: "FarmaAudit · v3.2"
- Headline: "Auditoría continua para Farmacias Plazoleta"
- Descripción: "Detectá desvíos en campo, gestioná la respuesta y cerrá el ciclo en horas, no semanas."
- Stats: 
  * 142 sucursales activas
  * 94% tasa de cierre 30d
  * 4.2h tiempo prom. respuesta

**Campos**:
- Email (precompletado: marina@plazoleta.com.ar)
- Password con toggle visibility
- Checkbox "Recordarme"
- Botón primario "Iniciar sesión" (navy)
- Link secundario "¿Olvidaste tu contraseña?"

**UX**:
- Validación en tiempo real con checkmark animado
- Error messages con icono rojo
- Loading state con spinner suave
- Tab key navega entre campos
- Enter submite formulario

---

## 2. DASHBOARD (/dashboard)

**Descripción**: Visión general del sistema para admin y responsables.

### HERO SECTION

Card grande destacada:
- Título: "¡Bienvenido, Marina!"
- Métrica principal: "Desvios vencidos: 2 | Críticos: 1"
- Subtítulo: "⏰ 12h para vencer: 5 desvios"
- Acción CTA: Botón naranja

### KPI CARDS (4 tarjetas)

Cada una con:
- Ícono en círculo coloreado
- Métrica principal (número grande, bold)
- Variación (↑ +12% o ↓ -3% con color dinámico)
- Etiqueta descriptiva pequeña

**KPIs**:
1. Registros Colectados: 44 (azul)
2. En Proceso: 12 (naranja)
3. Críticos Vencidos: 3 (rojo)
4. Tasa Cierre 30d: 94% (verde)

### GRÁFICOS (usando Recharts)

**Gráfico 1: Tendencia 30 días**
- Línea dual: desvios creados (naranja) vs cerrados (verde)
- Eje X: últimos 30 días
- Eje Y: cantidad
- Tooltip personalizado al hover
- Animación suave al cargar

**Gráfico 2: Distribución por Severidad**
- Pastel: Alta (rojo), Media (ámbar), Baja (azul)
- Leyenda debajo
- Hover muestra porcentaje

**Gráfico 3: Por Estado**
- Barras horizontales apiladas
- Abierta, En proceso, Resuelta, Cerrada
- Colores según estado

### SUPERVISIÓN DE SUCURSALES (Admin only)

"Últimas sucursales en alerta"

3 cards tipo "health status":
- Semáforo visual (rojo/amarillo/verde)
- Nombre sucursal + ubicación
- Desvios abiertos (número grande)
- Link "Ver detalles"

Rojo: >8 abiertos | Amarillo: 4-8 abiertos | Verde: <4 abiertos

---

## 3. GESTIÓN DE DESVIOS (/gestion-desvios)

**Descripción**: Tabla principal con filtros para auditar desvíos.

### SIDEBAR FILTROS (Colapsable en mobile)

Ancho: 240px en desktop

**Secciones**:
1. **Estado**
   - Checkboxes: Abierta (17), En proceso (12), Resuelta (5), Cerrada
   
2. **Severidad**
   - Checkboxes: Alta (8), Media (15), Baja (11)
   
3. **Sucursal**
   - Search input
   - Lista de 23 sucursales
   
4. **Botón**: [Clear all filters]

### TABLA/LISTA PRINCIPAL

**Búsqueda**: Input searchable por ID, descripción, responsable

**Chips de filtros activos**: Removibles con X

**Columnas**:
1. **Barra severidad**: Línea vertical coloreada (izquierda)
2. **ID**: FAR-2847 (monospace)
3. **Descripción**: Texto truncado
4. **Sucursal**: Nombre + zona
5. **Estado**: Badge coloreado
6. **Severidad**: Badge con dot
7. **Plazo**: Fecha + SLA (Overdue/Today/Soon/OK)
8. **Acciones**: Menú 3-puntos

**Row hover**: Sombra + background gris suave (z-lift visual)

**Row expansion**: Click abre preview en drawer sin navegar

**Batch actions**: 
- Checkbox en header
- Si seleccionadas: botones bottom "[✓ Marcar en proceso]" "[🔗 Contactar WA]" "[📄 Exportar]"

---

## 4. DETALLES DESVIO (/desvios/:id) ⭐ CRÍTICO

**Descripción**: Pantalla central donde se gestiona todo. Layout 3 columnas.

### HEADER (Sticky top)

```
◄ FAR-2847 | VENCIDA (rojo) | -5h vence | [🔗 Contactar WA] [✓ Aprobar] [✗ Rechazar]
```

Breadcrumb + ID + Estado badge grande + plazo rojo + botones primarios

### LEFT SIDEBAR (280px)

**Sucursal Card**:
- Foto/placeholder de la sucursal
- Nombre: "Plazoleta Centro"
- Código: "PLA-001"
- Dirección: "Av. Corrientes 1430, CABA"

**Severidad**:
- Badge grande: "Alta | Vencimientos"
- Barra coloreada (4px width)

**Plan de Acción** (Acordeón):
- Titulo desplegable
- Checklist de pasos:
  * ☐ Retirar medicamentos vencidos
  * ☐ Verificar stock físico
  * ☐ Reportar al proveedor

**Responsable Info**:
- Nombre: "Juan López"
- Rol: "Encargado"
- Teléfono: "+54 9 11 5555-1010" (clickeable → WhatsApp)
- Sucursal: "PLA-001"

**Timeline de Estados**:
```
── Abierta (5/5 10:00)
── En proceso (5/5 11:30)
→ Resuelta (5/5 13:45)

SLA: -5h (VENCIDA) ⚠️ (rojo)
```

### CENTER AREA (Flex, main content)

**Tabs** (4 pestañas, underline indicador):

#### TAB 1: CHAT INTEGRADO (Default)

**Conversación tipo WhatsApp**:
```
[Auditor message - Azul derecha]
"Necesito fotos del stock actual"
10:15

[Responsable message - Gris izquierda]
"Enviando fotos ahora"
11:30

[Fotos - Inline gallery]
📷 📷 📷
"3 fotos: Stock verificado"
Subida por: Juan López
Metadata: 11:32
Descripción: "Medicamentos retirados"

[Auditor message]
"Perfecto, está ok"
13:45

[Input area - Bottom]
Escribir comentario... [Enviar]
```

**Features**:
- Avatares circulares (iniciales + color según rol)
- Timestamp relativo ("hace 2h") actualizado
- Fotos inline con preview thumbnail
- Click foto → lightbox full screen
- Skeleton loading mientras carga chat
- Real-time: nuevos mensajes aparecen sin refrescar
- Scroll auto al fondo
- Unread badge en tab si hay nuevos

#### TAB 2: GALERÍA DE EVIDENCIAS

Grid responsive 2-3 columnas:
```
[Card 1]
┌──────────┐
│ [Imagen] │
│          │
│ Encargado│ (naranja badge)
│ 11/05    │
│ 13:45    │
│"Stock ok"│
└──────────┘
```

Cada card:
- Imagen thumbnail (aspect ratio 1:1, object-cover)
- Click → Lightbox full screen
- Quién subió (badge color diferenciado)
- Fecha y hora
- Descripción/comentario

Lightbox:
- Imagen grande (responsive)
- Navigation arrows (prev/next)
- Close button (X)
- Metadata visible: quién, cuándo, descripción
- Download link

#### TAB 3: TIMELINE VISUAL

Vertical timeline:
```
⚫────── Desvío creado: FAR-2847
         Auditor: Juan Pérez · 11:05
         Área: Vencimientos
         Sucursal: PLA-001

⚫────── Estado: En proceso
         Responsable: Juan López · 11:30
         
⚫────── Evidencia: 3 fotos
         Juan López · 13:45
         "Stock verificado, medicamento retirado"
         [Ver fotos ↗]

⚫────── Comentario auditor
         Juan Pérez · 14:15
         "Excelente, estado confirmado"
         
→⚫──── Estado: Resuelta → Cerrada
         En espera de aprobación final
```

Estilos:
- Dot coloreado según tipo evento
- Línea conectora (gris claro)
- Flecha (→) en evento en progreso
- Metadata pequeña bajo cada evento

#### TAB 4: DETALLE

Información estructurada:
```
ID:                 FAR-2847
Área:               Vencimientos
Sucursal:           PLA-001 Plazoleta Centro
Responsable:        Juan López (Encargado)
Zona:               CABA
Severidad:          Alta
Estado:             Resuelta
Plazo:              05/05 (VENCIDA -5h)
Creado:             05/05 10:00 por Juan Pérez
Descripción:        Medicamento XYZ vencido en vidriera
Plan de acción:     Retirar medicamentos vencidos
                    Verificar stock físico
                    Reportar al proveedor
```

### RIGHT PANEL (320px, Sticky)

**Si estado = RESUELTA:**
```
✅ APROBAR COMO CERRADO

El responsable propone resolver:
  ✓ Medicamentos retirados
  ✓ Stock verificado
  ✓ Reportado a proveedor

Detalles:
- Fotos: 3 evidencias
- Comentarios: 2
- Tiempo: 3h 45min

[✓ Aprobar] [✗ Rechazar]
```

**Si estado = ABIERTA o EN_PROCESO:**
```
⏱️ ACCIONES RÁPIDAS

[💬 Agregar comentario]
[☎️ Contactar por WhatsApp]
[📷 Subir evidencia]
[⏹️ Marcar en proceso]
[🔄 Reasignar]

Plazo: 24h
Vence: 05/05 10:00
Estado: -5h ⚠️ VENCIDA (rojo)
```

**Layout mobile**: Stack vertical cuando <lg

---

## 5. MIS DESVIOS (/mis-desvios)

**Descripción**: Vista para responsables de sucursal.

### HERO SECTION

Tarjeta destacada:
```
Tu responsabilidad: 5 desvios activos

Vencidos: 2 🔴 | En plazo: 3 🟡

[▶ Comenzar a resolver]
```

### FILTROS RÁPIDOS

Chips: [Abiertos] [En plazo] [Vencidos] [Resueltos]

### CARDS GRANDES (Mobile-first)

Cada tarjeta:
```
┌─────────────────────────┐
│ FAR-2847                │
│                         │
│ Vencimientos            │
│ Medicamentos en vidriera│
│                         │
│ Estado: VENCIDA (rojo)  │
│ Plazo: -5h | Crítico 🔴│
│                         │
│ [💬 Ver detalles] [>]   │
└─────────────────────────┘
```

En desktop: vista tabla, en mobile: cards apiladas

---

## 6. REVISIÓN DESVIOS (/revision-desvios)

**Descripción**: Auditor revisa borradores de otros auditores.

### HEADER

"X desvios esperando revisión"

### SIDE-BY-SIDE VIEW

```
┌─────────────────────┬─────────────────────┐
│ PROPUESTO           │ ORIGINAL            │
├─────────────────────┼─────────────────────┤
│ Severidad: Alta     │ Severidad: Alta  ✓  │
│ Área: Vencim.       │ Área: Vencim.    ✓  │
│ Desc: "Medic..."    │ Desc: "Medic..."  ✓  │
│                     │                     │
│ [Aprobar] [Rechazar con motivo...]       │
└─────────────────────┴─────────────────────┘
```

Checkmarks verdes si coincide, red X si no.

Acciones: 
- [✓ Aprobar]
- [✗ Rechazar] → Modal con campo "Motivo"

---

## 7. SUCURSALES (/sucursales)

**Descripción**: Listado de 23 farmacias con estado.

### LISTING GRID (2-3 columnas en desktop)

Cada card:
```
┌────────────────────┐
│ [🏢 Foto/Cover]    │
│                    │
│ PLA-001            │
│ Plazoleta Centro   │
│                    │
│ 📍 CABA            │
│ 🔴 Rojo (8 desvios)│
│                    │
│ Encargado:         │
│ Juan López         │
│                    │
│ [Ver detalles ↗]   │
└────────────────────┘
```

Semáforo:
- 🔴 Rojo: >8 desvios abiertos
- 🟡 Amarillo: 4-8 desvios
- 🟢 Verde: <4 desvios

Search: input para filtrar por nombre

### DETALLE SUCURSAL (/sucursales/:id)

**Hero Section**:
- Foto grande (cover, 400x200)
- Nombre: "Plazoleta Centro"
- Dirección: "Av. Corrientes 1430, CABA"
- Teléfono principal

**4-Card KPI Grid**:
```
[Abiertos: 8]  [En proceso: 3]  [Resueltos: 12]  [Cerrados: 34]
```

**Responsables**:
```
👤 Juan López
   Encargado de turno
   📞 +54 9 11 5555-1010

👤 María García  
   Farmacéutica
   📞 +54 9 11 5555-1011
```

**Timeline Auditorías Recientes**:
```
⚫ 05/05 10:00 - Auditoría de campo (Juan Pérez)
⚫ 04/05 14:30 - Auditoría de campo (Carla M.)
⚫ 03/05 09:15 - Auditoría de stock (Pablo R.)
```

**Tabla Desvios**: Listado filtrable de último año

---

## 8. ADMIN PANEL (/admin)

**Descripción**: Gestión de usuarios y permisos (Admin only).

### SIDEBAR NAVIGATION

- 👥 Usuarios
- 🔐 Permisos & Roles
- 📊 Audit log
- ⚙️ Configuración

### USUARIOS TAB

Tabla:
- Búsqueda por nombre/email
- Columnas: Nombre, Email, Rol, Sucursal, Estado (Activo/Inactivo)
- Bulk actions: Activar/Desactivar múltiples
- Row actions: 
  * Editar
  * Resetear password
  * Eliminar

Agregar usuario [+]:
- Modal con form
- Email, Nombre, Rol (select), Sucursal (si aplica)

### PERMISOS TAB

**Role Selector** (Auditor/Sucursal/Admin)

**Permission Grid**:
- Rows: módulos (Ver desvios, Crear desvios, Aprobar, Ver sucursales, Gestionar usuarios, etc.)
- Columns: permisos
- Checkboxes: ☑️ Sí, ☐ No

Shortcut: "Copy from role X" (pre-llena según template)

### AUDIT LOG TAB

Tabla de últimas acciones:
- Quién: nombre usuario
- Qué: acción realizada
- Cuándo: timestamp
- Detalles: ID recurso afectado

Filtrable por fecha y usuario.

---

# COMPONENTES REUTILIZABLES

**Botones**:
- Primary (Navy) con hover shadow
- Secondary (Gray border)
- Danger (Red)
- Ghost (transparent)
- Icon Button (44x44px)

**Badges**:
- Severidad (Alta/Media/Baja con dot coloreado)
- Estado (Abierta/En proceso/Resuelta/Cerrada/Vencida)
- SLA Pill (Overdue/Today/Soon/OK/Closed)

**Containers**:
- Card (white, border-gray-200, rounded-lg, shadow-sm)
- Card Hover (shadow-lg on hover)
- Modal (backdrop blur, fade animation)
- Drawer (slide from right, mobile-optimized)

**Inputs**:
- Text Input (border rounded-lg, focus ring-2)
- TextArea (rows configurable)
- Select (custom dropdown)
- Search Input (clear button)

**Feedback**:
- Empty State (SVG + headline + CTA)
- Loading State (skeleton screens, no spinner)
- Error State (red icon + message + retry)
- Toast (Sonner style, bottom-right, 4s auto-dismiss)

**Media**:
- Chat Message (bubble, avatar, timestamp)
- Photo Gallery (grid + lightbox)
- Timeline (vertical dots + lines)
- Avatar (initials + role color)

---

# ANIMACIONES

- Button hover: scale(1.02) + box-shadow, 150ms
- Card hover: translateY(-2px), 200ms
- Page enter: fade-in, 300ms
- Modal: scale + fade-in, 300ms
- Toast: slide-up from bottom, 200ms
- Loader: smooth rotation infinite
- Pulse on notification: opacity pulse

---

# RESPONSIVE DESIGN

**Breakpoints**:
- xs (0px): Mobile pequeño
- sm (640px): Mobile
- md (768px): Tablet
- lg (1024px): Desktop
- xl (1280px): Desktop grande

**Mobile Adaptations**:
- Sidebar → Hamburger menu (drawer)
- 3 columnas → Stack vertical
- Tabla → Cards
- Dropdowns → Modal/drawer
- Touch targets: 44x44px mínimo

---

# REAL-TIME FEATURES

1. **Chat en vivo**: Nuevos mensajes sin refrescar, indicador "typing...", sonido al llegar
2. **Fotos en vivo**: Nueva evidencia aparece en galería <3s, toast notification
3. **Estado en vivo**: Cambio de estado reflejado inmediatamente, timeline se actualiza
4. **Notificaciones**: Toast con sonido suave (ding), desktop notification si minimizado

---

# DATOS MOCK PARA PROTOTIPO

**Sucursales**: 6 tarjetas (3 rojo, 1 amarillo, 2 verde)

**Desvios**: 20+ ejemplos con estados variados

**Usuarios**: 5 perfiles (admin, 2 auditores, 2 responsables)

**Eventos/Timeline**: 50+ eventos variados (creación, estado, fotos, comentarios)

---

# CHECKLIST DE ÉXITO

✅ Diseño profesional y cohesivo (tokens, colores, tipografía)
✅ Toda la información visible sin exceso de scrolling
✅ Chat integrado funcional (messages, fotos, timeline)
✅ Galería con lightbox responsive
✅ Botones y acciones claras según rol y estado
✅ Mobile responsive (testear en 375px, 768px, 1024px)
✅ Real-time updates simuladas (toast notifications)
✅ Accesibilidad: colores + iconos, no solo color
✅ Performance: página carga rápido, transiciones suaves
✅ Prototipo totalmente navegable y clickeable

---

FIN DEL PROMPT

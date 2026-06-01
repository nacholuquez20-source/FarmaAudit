# Prompt para Stitch: FarmaAudit Frontend Redesign

## 🎯 Visión General del Proyecto

**FarmaAudit** es un sistema integral de gestión de auditorías de calidad para cadenas de farmacias. Gestiona hallazgos (desvios) de auditorías en 23 sucursales, genera planes de acción automáticos, supervisa avances, y facilita comunicación entre auditores, responsables de sucursales, y administradores.

**Roles de usuario:**
- **Admin**: Vista completa. Gestiona desvios, revisa, supervisa sucursales, panel administrativo
- **Auditor**: Crea y gestiona desvios, revisa desvios, accede a información de sucursales
- **Sucursal**: Responsables de farmacia. Ven solo sus desvios, responden, documentan evidencia

**Fases de un desvio:**
1. **Abierta** → Auditor crea hallazgo
2. **En Proceso** → Responsable inicia acción correctiva
3. **Resuelta** → Propone solución con evidencia
4. **Cerrada** → Auditor valida y cierra

## 📐 Stack Tecnológico Actual

- **Frontend**: React 19 + TypeScript + React Router
- **UI Framework**: Tailwind CSS (colores: azul-600, verde-600, ámbar-500, rojo-600)
- **Charting**: Recharts (gráficos de barras, líneas, pastel)
- **Componentes**: Sonner (toasts), componentes custom
- **Backend**: FastAPI + Supabase (auth + DB)
- **Base de datos**: Supabase PostgreSQL

## 🎨 Recomendaciones de Diseño & Estética

### Paleta de Colores Mejorada
```
Primario:     #2563EB → #1E40AF (azul más profundo y premium)
Éxito:        #059669 → #047857 (verde más elegante)
Advertencia:  #F59E0B → #D97706 (ámbar más saturado)
Error:        #DC2626 → #B91C1C (rojo más definido)
Neutro:       Grises 50-950 (mantener Tailwind)
Complementario: #7C3AED (púrpura para acentos)
```

### Tipografía & Espaciado
- **Headlines**: Bold, letter-spacing +0.5px, line-height 1.2
- **Body**: Regular, line-height 1.6
- **Spacing**: Usar multiples de 4px (Tailwind grid)

### Componentes Visuales
- **Badges**: Más redondeados (rounded-full), padding comprimido, fuente más pequeña
- **Botones**: Sombras sutiles en hover, transiciones suaves (150ms)
- **Cards**: Bordes sutiles (border-gray-200), sombras más profundas en hover
- **Inputs**: Bordes redondeados (rounded-lg), foco visible (ring-2)
- **Modales/Dropdowns**: Backdrop blur, animación suave de entrada

### Mejoras UX Generales
1. **Loader animations**: Skeleton screens en lugar de simple "Cargando..."
2. **Empty states**: Ilustraciones SVG personalizadas, no solo texto
3. **Feedback visual**: Mejor uso de toast notifications con íconos
4. **Responsive**: Mejorar mobile experience (dropdowns en header colapsables)
5. **Accesibilidad**: Contrast ratios, ARIA labels, keyboard navigation
6. **Hover/Focus states**: Más clara, consistente

## 📄 Páginas & Componentes Principales

### 1. **Login** (`/login`)
**Actual:** Minimalista, funcional pero poco atractivo

**Mejoras sugeridas:**
- Fondo con gradiente sutil (azul → púrpura)
- Tarjeta de login centrada con sombra profunda
- Ilustración/icono de farmacia en la esquina
- Checkmark animado para validaciones exitosas
- Password visibility toggle con icono
- "¿Olvidaste tu contraseña?" en link visible
- Error messages con icono de alerta rojo

### 2. **Dashboard** (`/dashboard`)
**Actual:** Grid de KPI cards + gráficos Recharts
**Audiencia:** Admin ve visión global. Sucursal ve solo su resumen.

**Mejoras sugeridas:**
- **Hero section**: Tarjeta superior grande con bienvenida + KPI destacado (ej: "3 desvios vencidos")
- **KPI Cards**: 
  - Fondo degradado por severidad (rojo, ámbar, verde)
  - Icono con fondo redondeado
  - Porcentaje de cambio (↑/↓) con color dinamico
  - Hover effect que expande
- **Gráficos**:
  - Más colores vibrantes
  - Tooltips personalizados con más info
  - Legend debajo del gráfico
  - Animación suave al cargar
- **Supervision de sucursales** (Admin):
  - Tarjetas tipo "health status"
  - Semáforo (rojo/amarillo/verde) más visual
  - Últimas 3 sucursales activas destacadas
  - "Ver más" para listar todas

### 3. **Desvios Gestion** (`/gestion-desvios`)
**Actual:** Lista simple de desvios con filtros

**Mejoras sugeridas:**
- **Filtros mejores**:
  - Sidebar colapsable en desktop, drawer en mobile
  - Chips removibles para filtros activos
  - "Clear all filters" button
- **Lista/Tabla**:
  - Alternancia de colores de fila (gris muy claro)
  - Hover effect destaca fila completa
  - Bordes verticales sutiles entre columnas
  - Estados con badges coloreados + pequeño icono
  - Indicador visual de severidad (barra izquierda coloreada)
- **Row expansion**: Click expande preview rápido sin navegar
- **Acciones**:
  - Menú de 3 puntos con opciones
  - Botones principales (Ver, Editar) con iconos
  - Batch actions si hay checkboxes

### 4. **Desvio Detail** (`/desvios/:id`)
**Actual:** Layout 3-columnas, mucho contenido, denso

**Mejoras sugeridas:**
- **Header mejorado**:
  - Breadcrumb visible
  - Estado grande con icono animado
  - Botones de acción principales (Notificar, Contactar, Resolver)
  - Back button con transición
- **Left sidebar - Info principal**:
  - Card con info de sucursal (nombre, ubicación, foto si existe)
  - Severidad con badge grande
  - Plan de acción desplegable (acordeón)
  - Timeline vertical de estado
- **Center - Chat/Actividad**:
  - Separación clara entre "Comentarios internos" vs "Comunicación oficial"
  - Avatares de usuarios
  - Timestamps relativos (hace 2h)
  - Replies anidadas si aplica
- **Right sidebar - Resolution Panel**:
  - Steps/Progress bar si hay pasos
  - Form fields con validación inline
  - Preview de evidencia antes de submit
  - Botones de acción sticky cuando scroll

### 5. **Mis Desvios** (`/mis-desvios`) - Sucursal View
**Actual:** Similar a Gestion pero para sucursal

**Mejoras sugeridas:**
- **Tono diferente**: Más "welcome/instructivo"
- **Hero section**: "Tu responsabilidad: 3 desvios activos"
- **Quick filters**: Solo por estado (Abierto, En Plazo, Vencido, Resuelto)
- **Cards grandes** en lugar de tabla (mejor mobile)
- **Call-to-action**: "Comenzar a resolver" con paso a paso

### 6. **Revision Desvios** (`/revision-desvios`)
**Actual:** Vista para review final

**Mejoras sugeridas:**
- **Indicador de trabajo**: "X desvios esperando revision"
- **Checkboxes** para marcar como revisado
- **Side-by-side**: Desvio propuesto vs datos originales
- **Approve/Reject flow**:
  - Modal con campo de "Motivo rechazo" si aplica
  - Confirmación con summary

### 7. **Sucursales** (`/sucursales` y `/sucursales/:id`)
**Actual:** Listado de sucursales

**Mejoras sugeridas:**
- **Listing**:
  - Cards o grid (2-3 cols en desktop)
  - Foto/logo de sucursal si existe
  - Indicador de salud (# desvios abiertos)
  - Location badge con icono de ubicación
  - Search por nombre
- **Detail page**:
  - Hero section con foto, nombre, dirección
  - 4-card KPI grid (desvios por estado)
  - Timeline de auditorías recientes
  - Responsables (nombre, tel, email)
  - Historial de desvios (tabla filtrable)

### 8. **Admin Panel** (`/admin`)
**Actual:** Gestión de usuarios y permisos

**Mejoras sugeridas:**
- **Layout**: Sidebar nav + main content
- **User Management**:
  - Tabla con search/filter
  - Bulk actions (activate/deactivate)
  - Modal para agregar usuario
  - Row actions (editar, resetear password, eliminar)
- **Permissions**:
  - Role selector con checkbox grid de módulos
  - Visual indicator de permisos activos
  - "Copy from role" shortcut
- **Audit log** (nuevo): Tabla de últimas acciones

## 🎭 Componentes Reutilizables (Design System)

Crear/mejorar estos componentes para consistencia:

```
ButtonPrimary     → azul, más redondeado
ButtonSecondary   → gris, border
ButtonDanger      → rojo
ButtonGhost       → sin fondo

StatusBadge       → coloreado por estado
SeverityBadge     → coloreado por severidad (rojo/ámbar/verde)

Card              → sombra mejorada, border gris-200
CardHover         → hover shadow-lg

InputField        → border rounded-lg, focus ring
TextArea          → similar pero más alto
Select            → mejores opciones visuales

EmptyState        → SVG + headline + subtext
LoadingState       → spinner + "Cargando..."
ErrorState         → icono rojo + mensaje + retry button

Modal             → backdrop blur, animación fade
Dropdown          → mismo de AppLayout pero mejorado
Toast             → Sonner, con iconos
```

## 📱 Responsive & Mobile

- **Breakpoints**: xs (0), sm (640), md (768), lg (1024), xl (1280)
- **Mobile first**: Diseñar mobile → luego desktop
- **Touch targets**: Mínimo 44x44px
- **Fonts**: Escalar bien (no texto chico en mobile)
- **Dropdowns**: Convertir a drawer/modal en mobile
- **Tablas**: Convertir a cards en mobile (no horizontal scroll)

## 🎬 Animaciones & Transiciones

- **Button hover**: scale 1.02 + shadow, 150ms
- **Card hover**: translateY -2px, 200ms
- **Page transition**: fade in, 300ms
- **Toast**: slide in from bottom, 200ms
- **Modal**: scale + fade, 300ms
- **Loading spinners**: smooth rotation

## 📐 Spacing & Grid

- **Container max-width**: 7xl (80rem)
- **Gutters**: px-4 sm:px-6 lg:px-8
- **Gaps**: Usar gap-4, gap-6, gap-8
- **Padding cards**: p-4 sm:p-6
- **Vertical spacing**: space-y-4, space-y-6

## 🔄 Consideraciones Técnicas

1. **Performance**: 
   - Lazy load charts (Recharts)
   - Skeleton screens para tablas
   - Debounce search

2. **Accessibility**:
   - WCAG 2.1 AA minimum
   - Contrast ratio 4.5:1 para texto
   - Focus visible en todos los interactivos
   - ARIA labels en buttons sin texto

3. **Dark Mode** (opcional future):
   - Usar Tailwind dark: modifier
   - Tested colors en light + dark

## 🚀 Priorización de Mejoras

### Tier 1 (High Impact)
- Dashboard hero section + mejorar KPI cards
- Desvio detail redesign (layout más limpio)
- Color palette upgrade
- Buttons & badges consistency

### Tier 2 (Medium Impact)
- Gestion desvios filtros sidebar
- Sucursales list → cards
- Empty states + loading states
- Hover animations

### Tier 3 (Polish)
- Dark mode prep
- Micro-interactions
- Advanced animations
- Page transitions

## 📝 Deliverables Esperados

1. **Figma/Design file** con:
   - All pages wireframed
   - Component library (buttons, cards, etc.)
   - Color system documented
   - Typography scale
   - Grid/spacing rules

2. **Frontend code** (React + Tailwind):
   - Todos los componentes implementados
   - Responsive en mobile/tablet/desktop
   - Navegación funcional
   - Integración con API existente (no cambiar backend)

3. **Documentation**:
   - Design system specs
   - Color swatches con valores hex
   - Component props documented
   - Usage examples

## 🎯 Éxito se mide por:

✅ Diseño más profesional y moderno
✅ Mejor UX (más intuitivo, menos clics)
✅ Mobile-first responsiveness
✅ Accesibilidad mejorada
✅ Performance sin regresiones
✅ Código mantenible y escalable

---

**Presupuesto estimado**: 40-60 horas de diseño + 80-120 horas de desarrollo frontend

**Timeline**: 4-6 semanas con dedicación time-focused

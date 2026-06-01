# FarmaAudit - Stitch Prompt (Versión Corta)

## Proyecto
Sistema de gestión de auditorías de calidad para 23 farmacias. Roles: Admin (visión total), Auditor (crea/revisa desvios), Sucursal (responde desvios). Estados: Abierta → En Proceso → Resuelta → Cerrada.

## Tech Stack
React 19 + TypeScript + Tailwind CSS + Recharts + Supabase

## Paleta Colores Mejorada
```
Primario:    #1E40AF (azul premium)
Éxito:       #047857 (verde elegante)
Advertencia: #D97706 (ámbar saturado)
Error:       #B91C1C (rojo definido)
Acento:      #7C3AED (púrpura)
```

## Mejoras Principales por Página

### Login (/login)
- Fondo gradiente (azul → púrpura)
- Card centrada con sombra profunda
- Icono/ilustración farmacia
- Validaciones con checkmark animado
- Password toggle visibility

### Dashboard (/dashboard)
- Hero section con KPI principal destacado
- KPI cards con degradado por severidad + hover effect
- Gráficos Recharts con colores vibrantes y tooltips personalizados
- Supervision sucursales: tarjetas tipo "health status"
- Semáforo visual mejorado (rojo/amarillo/verde)

### Desvios Gestion (/gestion-desvios)
- Sidebar colapsable para filtros
- Chips removibles de filtros activos
- Lista con hover effect + barra severidad izquierda
- Badges con iconos para estados
- Row expansion para preview rápido
- Menú 3-puntos para acciones

### Desvio Detail (/desvios/:id)
- Header con breadcrumb + estado grande + botones principales
- Left: Info sucursal + severidad + timeline estado
- Center: Chat separado (comentarios vs comunicación oficial)
- Right: Resolution panel sticky con form + preview evidencia
- Avatares + timestamps relativos

### Mis Desvios (/mis-desvios)
- Hero: "Tu responsabilidad: X desvios activos"
- Cards grandes (mobile-first) vs tabla
- Quick filters (solo por estado)
- Call-to-action "Comenzar a resolver"

### Revision Desvios (/revision-desvios)
- Side-by-side: propuesto vs original
- Checkboxes para marcar revisado
- Approve/Reject modal con motivo

### Sucursales (/sucursales)
- Grid/cards con foto, nombre, indicador salud
- Location badge, search por nombre
- Detail page: foto hero + 4-card KPI + timeline + responsables

### Admin (/admin)
- Sidebar nav + table con search/filter
- Bulk actions (activate/deactivate)
- Modal agregar usuario
- Role permissions: checkbox grid de módulos
- Audit log (nuevo)

## Componentes del Design System
ButtonPrimary, ButtonSecondary, ButtonDanger, StatusBadge, SeverityBadge, Card, InputField, TextArea, Select, EmptyState, LoadingState, ErrorState, Modal, Dropdown, Toast

## Mobile-First Responsive
- xs (0), sm (640), md (768), lg (1024), xl (1280)
- Touch targets: 44x44px min
- Tablas → cards en mobile
- Dropdowns → drawer/modal en mobile

## Animaciones
- Button hover: scale 1.02 + shadow (150ms)
- Card hover: translateY -2px (200ms)
- Page: fade in (300ms)
- Modal: scale + fade (300ms)
- Toast: slide in (200ms)

## Spacing
- Container max-width: 7xl (80rem)
- Gutters: px-4 sm:px-6 lg:px-8
- Gaps: gap-4, gap-6, gap-8
- Padding cards: p-4 sm:p-6

## Accessibility (WCAG 2.1 AA)
- Contrast ratio 4.5:1
- Focus visible en interactivos
- ARIA labels en buttons sin texto
- Keyboard navigation

## Priorización
**Tier 1**: Dashboard hero + KPI cards, Desvio detail layout, Paleta colores, Buttons/badges consistency
**Tier 2**: Filtros sidebar, Sucursales cards, Empty/loading states, Hover animations
**Tier 3**: Dark mode prep, Micro-interactions, Page transitions

## Éxito se mide por:
✅ Diseño profesional y moderno
✅ Mejor UX (intuitivo, menos clics)
✅ Mobile responsiveness
✅ Accesibilidad mejorada
✅ Performance sin regresiones
✅ Código mantenible

## Entrega esperada:
- Figma con todas las páginas + component library
- Frontend React/Tailwind funcional y responsive
- Design system documented
- Sin cambios en backend (API compatible)

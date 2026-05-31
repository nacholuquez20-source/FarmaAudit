# FarmaAudit - Prompt Exhaustivo para Google Stitch

## 📋 Contexto General del Proyecto

**FarmaAudit** es un sistema de QA para auditorías de farmaciasmediante WhatsApp. El proyecto está diseñado para:
- Gestionar desvíos (no conformidades) en 23 sucursales de farmacias
- Rastrear planes de acción y evidencias de cumplimiento
- Proporcionar dashboards de supervisión en tiempo real
- Integrar comunicación vía WhatsApp para contactar responsables

**Usuario Target:** Auditores, administradores, y responsables de sucursales
**Rol del Frontend:** Plataforma de web para gestión, revisión y supervisión de desvíos

---

## 🛠️ Stack Tecnológico Actual

```
Frontend:
- React 19 + TypeScript
- React Router v7 para navegación
- TailwindCSS 4 para estilos
- Recharts para visualizaciones
- Supabase para auth y datos
- React Query para state management
- Sonner para notificaciones toast

Arquitectura:
- Componentes funcionales con hooks
- Custom hooks para lógica de negocio (useAuth, useGestion, etc.)
- Layout pattern con AppLayout wrapper
- Design tokens para colores y estilos
- Lazy loading de rutas
```

---

## 📊 Páginas y Componentes Principales (Estado Actual)

### 1. **Dashboard** (`/dashboard`)
   - **Función:** Overview de KPIs, semáforo por sucursal, gráficos de tendencias
   - **Componentes:** KPICard, recharts (BarChart, LineChart, PieChart)
   - **Datos mostrados:** Total desvíos, gestiones abiertas/resueltas/cerradas, criticos, tasa de cierre
   - **Problema actual:** Grid-based layout simple, gráficos básicos sin interactividad avanzada
   - **Oportunidad:** Diseño modular mejorado, cards animadas, filtros dinámicos

### 2. **Gestión de Desvíos** (`/gestion-desvios`)
   - **Función:** Vista de lista principal con filtros y búsqueda
   - **Componentes:** FilterChip, SelectBox, EstadoBadge, SeveridadBadge, SlaPill
   - **Interacciones:** Filtrar por estado/severidad, agrupar por estado/sucursal, selección múltiple
   - **Problema actual:** Drawer desplegable a la derecha (mobile-unfriendly), diseño denso de tabla
   - **Oportunidad:** Modal mejorado, vista mobile optimizada, tabla más visual

### 3. **Detalle de Desvío** (Drawer lateral)
   - **Función:** Ver actividad, plan de acción, evidencias, detalles
   - **Componentes:** Timeline, Fact labels, tabs (actividad/plan/evidencias/detalle)
   - **Problema actual:** Drawer pequeño, scrolling dentro del drawer
   - **Oportunidad:** Experiencia modal más clara, mejor jerarquía de información

### 4. **Sucursales** (`/sucursales`, `/sucursales/:id`)
   - **Función:** Vista de sucursales con semáforo, detalles individuales
   - **Componentes:** Tabla con datos, links a detalles
   - **Problema actual:** Layout básico
   - **Oportunidad:** Tarjetas más visuales, geolocalización (si disponible)

### 5. **Admin** (`/admin`)
   - **Función:** Gestión de usuarios, permisos, roles
   - **Componentes:** Formularios, tablas
   - **Problema actual:** No visto en detalle pero estructura básica
   - **Oportunidad:** Panel admin más robusto, mejor UX

---

## 🎨 Design Tokens Actuales (Analizar y Mejorar)

```
Navy: #1E3A6D (primario)
Orange: #F15A29 (acciones, urgencia)
Green: #2A9D5F (éxito, resuelto)
Red: #DC2626 (crítico, vencido)
Muted: #64748B (texto secundario)

Estados:
- Vencida: rojo (#991B1B fg, #FEE2E2 bg)
- Abierta: navy (#1E3A6D)
- En_proceso: orange (#F15A29)
- Resuelta: green (#2A9D5F)
- Cerrada: gris (#475467)

Severidad:
- Alta: rojo (#DC2626)
- Media: amber (#D97706)
- Baja: azul cielo (#0EA5E9)
```

---

## 🚀 Oportunidades de Mejora Visual y UX

### A. Diseño General
1. **Modernizar paleta visual** - Agregar gradientes sutiles, sombras sofisticadas
2. **Mejorar espaciado y tipografía** - Jerarquía visual más clara
3. **Agregar microinteracciones** - Transiciones fluidas, feedback visual inmediato
4. **Optimizar para mobile** - Actualmente layout muy desktop-centric

### B. Dashboard
1. **Cards interactivas** - Hover effects, drill-down capabilities
2. **Gráficos animados** - Animaciones de entrada, transiciones suaves
3. **Comparativas visuales** - Week-over-week, month-over-month trends
4. **Real-time indicators** - Badges de "actualizado hace X minutos"

### C. Gestión de Desvíos
1. **Tabla más visual** - Row highlights, colores por estado, iconografía
2. **Filtros avanzados** - Tags visuales, búsqueda facetada
3. **Modal vs Drawer** - Evaluar si modal sería mejor para detalles
4. **Acciones rápidas** - Inline actions con confirmación elegante

### D. Timeline y Actividad
1. **Timeline más visual** - Mejor conexión visual entre eventos
2. **Avatares de usuarios** - Visual para quién hizo qué acción
3. **Timestamps relativos** - "hace 2 horas" vs timestamps absolutos

### E. Formularios y Entrada de Datos
1. **Inputs más robustos** - Focus states mejorados, placeholders claros
2. **Validación inline** - Feedback en tiempo real sin molestias
3. **Rich text editor para planes** - Si no existe

---

## 📱 Componentes para Redesign Prioritario

**TIER 1 (Alto impacto, visible en todas partes):**
- [ ] Botones y CTAs (uniformidad, estados, variantes)
- [ ] Cards de desvíos (tabla → componentes reutilizables)
- [ ] Badges y pills (estado, severidad, SLA)
- [ ] Navegación (header, sidebar)

**TIER 2 (Mejora significativa de experiencia):**
- [ ] Dashboard - layout de cards, gráficos
- [ ] Modal/Drawer de detalle
- [ ] Timeline de actividad
- [ ] Filtros y busca

**TIER 3 (Polish final):**
- [ ] Ilustraciones y empty states
- [ ] Animaciones de transición
- [ ] Dark mode (si se requiere)

---

## 🎯 Especificaciones para Stitch

### Requerimientos Funcionales
1. **Mantener todas las funcionalidades actuales:**
   - Filtros por estado, severidad, sucursal
   - Búsqueda full-text (desvio, ID, sucursal, responsable)
   - Agrupación dinámica
   - Selección múltiple
   - Integración con WhatsApp
   - Timeline de eventos
   - Comentarios internos

2. **Mejorar la experiencia visual:**
   - Componentes más modernos y consistentes
   - Mejor responsive design
   - Animaciones sutiles pero agradables
   - Estados visuales claros (hover, active, disabled, loading)

3. **Mantener la compatibilidad:**
   - React 19 + TypeScript
   - TailwindCSS para utility classes
   - Supabase integration
   - React Router v7
   - Recharts para gráficos (o mejoradas)

### Wireframe Conceptual para Rediseño

#### Dashboard v2
```
┌─────────────────────────────────────────────┐
│ Dashboard · Actualizado hace 2 min           │
├─────────────────────────────────────────────┤
│ [Auto-refresh: 30s] [Refrescar]              │
├─────────────────────────────────────────────┤
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ 45       │  │ 12       │  │ 3        │  │
│  │ Desvíos  │  │ Abiertos │  │ Vencidos │  │
│  │ Totales  │  │          │  │ Críticos │  │
│  └──────────┘  └──────────┘  └──────────┘  │
│                                              │
│  ┌──────────────────┐  ┌─────────────────┐  │
│  │ Gestiones Estado │  │ Ranking Crítico │  │
│  │ (Pie Chart)      │  │ (Card List)     │  │
│  └──────────────────┘  └─────────────────┘  │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │ Tendencia 30 Días (Line Chart)          │  │
│  └────────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

#### Gestión de Desvíos v2
```
┌──────────────────────────────────────────────┐
│ FA │ FarmaAudit · Plazoleta - Gestión        │
├──────────────────────────────────────────────┤
│ [🔍 Buscar...] [Vista: Estado|Sucursal|List]│
│ [Estado: Todos|Abierta|...] [Severidad: ..] │
├──────────────────────────────────────────────┤
│ [2 seleccionados] [Reasignar] [Exportar]    │
├──────────────────────────────────────────────┤
│ ┌────────────────────────────────────────┐  │
│ │ [☐] │ Severidad │ Desvío              │  │
│ │     │ (Visual)  │ (Descripción)       │  │
│ ├─────┼───────────┼─────────────────────┤  │
│ │ [☑] │ 🔴 Alta   │ Medicamento vencido │  │
│ │     │           │ FAR-001 · Sucursal A│  │
│ │     │           │ Responsable: Juan   │  │
│ │     │           │ SLA: 🔴 Vencido hace│  │
│ │     │           │ 3 días              │  │
│ ├─────┼───────────┼─────────────────────┤  │
│ │ ... (más filas)                       │  │
│ └────────────────────────────────────────┘  │
│                                              │
│ ┌────────────────────────────────────────┐  │
│ │ ▧ Detalle Desvío                       │  │
│ │ ┌────────────────────────────────────┐ │  │
│ │ │ 🔴 Alta │ ☐ Abierta │ ⏱️ Venc. 3d  │ │  │
│ │ │ FAR-001 - Medicamento vencido      │ │  │
│ │ ├────────────────────────────────────┤ │  │
│ │ │ 📍 Sucursal A │ 👤 Juan │ 📅 3/6  │ │  │
│ │ ├────────────────────────────────────┤ │  │
│ │ │ [💬 WhatsApp] [✓ Resolver] [...]   │ │  │
│ │ ├────────────────────────────────────┤ │  │
│ │ │ Actividad │ Plan │ Evidencias      │ │  │
│ │ ├────────────────────────────────────┤ │  │
│ │ │ • Juan creó desvío (hace 3 días)   │ │  │
│ │ │ • María comentó (hace 1 día)       │ │  │
│ │ │ • Plan cargado (ayer)              │ │  │
│ │ └────────────────────────────────────┘ │  │
│ └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

---

## 🎨 Principios de Diseño a Aplicar

1. **Consistencia:** Un componente Button debe verse igual en toda la app
2. **Claridad:** Información importante visible sin clicks innecesarios
3. **Validación:**  Estados claros (loading, error, success, empty)
4. **Accesibilidad:** WCAG AA mínimo, contrast ratios suficientes
5. **Performance:** Animaciones suaves 60fps, no pesadas
6. **Mobile-First:** Diseñar para mobile primero, escalar a desktop

---

## 📦 Componentes Reutilizables a Crear

```typescript
// Botones
<Button variant="primary|secondary|danger" size="sm|md|lg" />
<IconButton icon={Icon} />

// Inputs y forms
<TextInput placeholder="" />
<Select options={[]} />
<Checkbox />
<Badge variant="success|warning|error" />

// Feedback
<Toast type="success|error|info" />
<Modal isOpen={} onClose={} />
<Drawer position="right|left" isOpen={} />

// Data
<DataTable columns={} data={} />
<Pagination current={} total={} />
<FilterChip active={} />

// Cards
<Card />
<StatCard title="" value="" />
<DesvioCard desvio={} onClick={} />

// Layout
<Container />
<Grid cols={} />
<Stack direction="vertical|horizontal" />
```

---

## 🔍 Problemas Actuales a Resolver

1. **Mobile Experience:** Drawer lateral no es ideal en móvil → Modal adaptativo
2. **Tabla densa:** Muchas columnas comprimidas → Componentes card para móvil
3. **Color repetitivo:** Navy muy presente → Agregar más variedad visual
4. **Sin animaciones:** Transiciones abruptas → Agregar micro-transiciones
5. **Forms básicos:** Sin validación visual clara → Mejorar feedback
6. **Empty states:** Texto plano → Ilustraciones o iconografía
7. **Loading states:** Simple spinner → Skeletal loaders contextuales
8. **Error handling:** Errores sin contexto → Mensajes claros y accionables

---

## ✅ Entregables Esperados de Stitch

1. **Componentes React reutilizables** - Library de 20-30 componentes
2. **Páginas redesñadas** - Dashboard, Gestión, Detalles
3. **Storybook o demostración** - Catálogo de componentes
4. **TypeScript completo** - Sin any types
5. **Tailwind utilities** - Aprovechando la nueva v4
6. **Documentación** - Props, ejemplos de uso
7. **Responsive design** - Mobile, tablet, desktop testeado
8. **Temas o customización** - Fácil de adaptar a diferentes marca

---

## 📊 Métricas de Éxito

- [ ] Lighthouse performance >85
- [ ] Responsive design funciona en phones, tablets, desktops
- [ ] Accesibilidad WCAG AA
- [ ] Reducción de clicks para acciones principales >20%
- [ ] Loading time de páginas <2s
- [ ] Mobile time-on-task 30% menor que actual

---

## 🎭 Tono y Estilo Visual

- **Profesional pero accesible** - No demasiado corporativo
- **Moderno pero estable** - Tendencias sin exceso
- **Optimista** - Colores vivos cuando es apropiado (verde para éxito)
- **Eficiente** - Máxima información relevante, mínimo ruido

---

## Notas Finales para Stitch

- **No** duplicar componentes: una Button rule for all
- **Sí** crear variantes: Button.Primary, Button.Danger, Button.Ghost
- **Mantener** la filosofía de TailwindCSS (utility-first)
- **Considerar** dark mode para futuro (hacer arquitectura preparada)
- **Testear** con usuarios reales si es posible
- **Documentar bien** - Tu trabajo debe ser fácil de mantener por otros desarrolladores

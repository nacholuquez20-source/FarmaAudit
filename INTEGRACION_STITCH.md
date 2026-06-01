# Guía de Integración: Stitch → React (FarmaAudit)

## Estado Actual
- ✅ Stitch generó un **prototipo interactivo completo** con 23KB de componentes React
- ✅ Ya tienen **ChatMensajes.tsx**, **EvidenciaGaleria.tsx** en el proyecto
- ✅ Sistema de **TOKENS** bien definido (colores, espaciado, tipografía)
- ⚠️ Falta: **Chat mejorado**, **Gallery con lightbox**, **Timeline visual**, **Real-time updates**

## Estructura de Código Stitch

```
farmaaudit_extracted/
├── modules.jsx          (71KB) → Todas las pantallas del sistema
├── screens.jsx          (21KB) → Prototipos interactivos
├── detail.jsx           (16KB) → Vista de desvío + drawer/modal
├── table.jsx            (16KB) → Tabla de desvios con filtros
├── data.jsx             (10KB) → Mock data + helpers
├── primitives.jsx       (12KB) → TOKENS, badges, botones
├── chrome.jsx           (16KB) → Frames para desktop/mobile
└── tweaks-panel.jsx     (24KB) → Panel de controles del prototipo
```

## Archivos a Adaptar al Proyecto React

### 1. Copiar TOKENS desde `primitives.jsx`

**Destino:** `frontend/src/lib/design-tokens.ts`

```typescript
export const DESIGN_TOKENS = {
  brand: {
    orange: '#F15A29',
    orangeSoft: '#FFE9DF',
    navy: '#1E3A6D',
    navyDeep: '#142A52',
    green: '#2A9D5F',
  },
  estado: {
    Vencida:    { bg: '#FEE2E2', fg: '#991B1B', dot: '#DC2626' },
    Abierta:    { bg: '#E0EAFF', fg: '#1E3A6D', dot: '#1E3A6D' },
    En_proceso: { bg: '#FFF1E6', fg: '#9A3A12', dot: '#F15A29' },
    Resuelta:   { bg: '#E7F6EC', fg: '#1E6F3D', dot: '#2A9D5F' },
    Cerrada:    { bg: '#F1F4F9', fg: '#475467', dot: '#667085' },
  },
  severidad: {
    Alta:  { bar: '#DC2626', soft: '#FEE2E2', fg: '#991B1B' },
    Media: { bar: '#D97706', soft: '#FEF3C7', fg: '#92400E' },
    Baja:  { bar: '#0EA5E9', soft: '#E0F2FE', fg: '#075985' },
  },
  sla: {
    overdue: { bg: '#FEE2E2', fg: '#991B1B', bar: '#DC2626' },
    today:   { bg: '#FFE5D6', fg: '#9A3A12', bar: '#F15A29' },
    soon:    { bg: '#FEF3C7', fg: '#92400E', bar: '#D97706' },
    ok:      { bg: '#F1F4F9', fg: '#344054', bar: '#94A3B8' },
    closed:  { bg: '#E7F6EC', fg: '#1E6F3D', bar: '#2A9D5F' },
  },
};
```

### 2. Componentes Base (desde Stitch)

**Destino:** `frontend/src/components/ui/`

Copiar y adaptar de Stitch:
- `SeveridadBadge.tsx` → usa DESIGN_TOKENS
- `EstadoBadge.tsx` → usa DESIGN_TOKENS
- `SlaPill.tsx` → visual SLA con semáforo
- `PrimaryAction.tsx` → botones contextuales
- `IconButton.tsx` → botones con íconos

### 3. Mejorar ChatMensajes.tsx

**Destino:** `frontend/src/components/ChatMensajes.tsx` (REEMPLAZAR)

Mejoras necesarias:
- ✅ Avatares de usuario (iniciales + color)
- ✅ Separación visual: "Comentarios internos" vs "Comunicación oficial"
- ✅ Timestamps relativos ("hace 2h")
- ✅ Soporte para replies anidadas
- ✅ Skeleton loading mientras carga
- ✅ Real-time updates via Supabase subscription

```typescript
// Agregar al hook useMensajesInternos
useEffect(() => {
  const subscription = supabase
    .from('desvio_eventos')
    .on('INSERT', payload => {
      if (payload.new.id_gestion === idGestion) {
        setMensajes(prev => [...prev, payload.new]);
      }
    })
    .subscribe();
  
  return () => subscription.unsubscribe();
}, [idGestion]);
```

### 4. Mejorar EvidenciaGaleria.tsx

**Destino:** `frontend/src/components/EvidenciaGaleria.tsx` (REEMPLAZAR)

Mejoras necesarias:
- ✅ Grid responsive 2-3 columnas
- ✅ Lightbox modal para ver en grande
- ✅ Metadata: quién subió, cuándo, descripción
- ✅ Skeleton loading mientras descarga
- ✅ Badge color diferenciado (Auditor azul, Encargado naranja)
- ✅ Soporte para videos (play button overlay)

```typescript
// Agregar lightbox
import Lightbox from 'yet-another-react-lightbox';

const [selectedPhoto, setSelectedPhoto] = useState<EvidenciaItem | null>(null);

return (
  <>
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {evidencias.map(item => (
        <div 
          key={item.id}
          onClick={() => setSelectedPhoto(item)}
          className="cursor-pointer transition hover:opacity-80"
        >
          {/* thumbnail */}
        </div>
      ))}
    </div>
    
    {selectedPhoto && (
      <Lightbox open onClose={() => setSelectedPhoto(null)} slides={[...]} />
    )}
  </>
);
```

### 5. NUEVO: Timeline.tsx

**Destino:** `frontend/src/components/Timeline.tsx`

```typescript
interface TimelineProps {
  eventos: DesvioEvento[];
}

export function Timeline({ eventos }: TimelineProps) {
  return (
    <div className="space-y-4">
      {eventos.map((evento, i) => (
        <div key={evento.id} className="flex gap-4">
          {/* Dot + Line */}
          <div className="flex flex-col items-center">
            <div className={`h-3 w-3 rounded-full ${getDotColor(evento.tipo)}`} />
            {i !== eventos.length - 1 && <div className="h-12 w-0.5 bg-gray-200" />}
          </div>
          
          {/* Content */}
          <div className="pb-8">
            <div className="font-medium">{getEventLabel(evento.tipo)}</div>
            <div className="text-sm text-gray-500">{formatDateTime(evento.created_at)}</div>
            {evento.comentario && <p className="mt-1 text-sm">{evento.comentario}</p>}
            {evento.metadata?.foto_url && (
              <a href={evento.metadata.foto_url} className="mt-2 inline-block text-sm text-blue-600">
                Ver foto
              </a>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
```

### 6. NUEVO: DesvioDetailEnhanced.tsx

**Destino:** `frontend/src/pages/DesvioDetail.tsx` (MEJORAR)

Layout mejorado:
```
┌─────────────────────────────────────────┐
│ Header: ID · Estado · SLA               │
├──────────────┬──────────────┬───────────┤
│              │              │           │
│ Left Sidebar │ Center Area  │   Right   │
│              │              │   Panel   │
│ • Sucursal   │ TABS:        │ • Acción  │
│ • Severity   │ ├ Chat       │ • Estado  │
│ • Timeline   │ ├ Fotos      │ • Botones │
│ • Respons.   │ ├ Plan       │           │
│              │ └ Detalle    │           │
└──────────────┴──────────────┴───────────┘
```

## Integración Paso a Paso

### Paso 1: Copiar TOKENS (30 min)
1. Abrir `primitives.jsx` de Stitch
2. Copiar objeto `TOKENS`
3. Crear `frontend/src/lib/design-tokens.ts`
4. Exportar como constante

### Paso 2: Crear Componentes Base (1 hora)
1. Copiar `SeveridadBadge`, `EstadoBadge` desde `primitives.jsx`
2. Adaptarlos a TypeScript + Tailwind
3. Guardar en `frontend/src/components/ui/`
4. Usarlos en `ChatMensajes.tsx` y `EvidenciaGaleria.tsx`

### Paso 3: Mejorar Chat y Galería (2 horas)
1. Reemplazar `ChatMensajes.tsx` con versión mejorada
2. Reemplazar `EvidenciaGaleria.tsx` con versión + lightbox
3. Agregar Supabase real-time subscriptions
4. Agregar skeleton loaders

### Paso 4: Crear Timeline (1 hora)
1. Crear `Timeline.tsx` con visual timeline
2. Integrar en `DesvioDetail.tsx`

### Paso 5: Mejorar DesvioDetail (2 horas)
1. Restructurar layout 3-columnas
2. Integrar Chat + Fotos + Timeline
3. Agregar panel de acción sticky en mobile
4. Testing en mobile

### Paso 6: Pulir UI (1 hora)
1. Usar DESIGN_TOKENS en todas partes
2. Transiciones suaves
3. Responsive testing

## Archivos a Ignorar/No Usar de Stitch
- ❌ `modules.jsx` → Es de prototipo Stitch, no código listo
- ❌ `screens.jsx` → Prototipo solamente
- ❌ `chrome.jsx`, `ios-frame.jsx` → Frames de visualización
- ❌ `tweaks-panel.jsx` → Panel de Stitch solamente

## Archivos a Usar de Stitch
- ✅ `primitives.jsx` → TOKENS, componentes base
- ✅ `detail.jsx` → Estructura del layout
- ✅ `data.jsx` → Mock data (referencia)
- ✅ CSS/styling patterns

## Validación Final

```bash
# TypeScript check
npx tsc --noEmit

# Tests
npm test

# Mobile check
npm run dev # Ctrl+Shift+M en DevTools

# Performance
npm run build
# Check bundle size
```

## Timeline Estimado
- **Paso 1-2:** ~1.5 horas
- **Paso 3-4:** ~3 horas
- **Paso 5-6:** ~3 horas
- **Total:** ~7-8 horas

## Entregables
✅ DesvioDetail.tsx mejorado 80% visualmente
✅ Chat + Fotos + Timeline integrados
✅ Supabase real-time working
✅ Responsive en mobile
✅ Usando DESIGN_TOKENS de Stitch

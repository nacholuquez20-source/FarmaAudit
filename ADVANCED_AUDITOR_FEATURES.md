# Características Avanzadas para Auditor de Perfumería

**Status**: ✅ Componentes creados  
**Date**: 2026-06-03  
**Features**: Sub-items por marca, WhatsApp mejorado, checkmarks visuales  

---

## 🎯 3 Mejoras Principales Agregadas

### 1️⃣ **Sub-puntos por Marca en OFERTAS** 
### 2️⃣ **Flujo WhatsApp Mejorado**
### 3️⃣ **Checkmarks Visuales**

---

## 📊 1. AuditBlocksPanelAdvanced.tsx

Versión mejorada que desglose **OFERTAS** en 4 marcas principales:

### Estructura
```typescript
OFERTAS (Bloque principal)
├─ Unilever (Sub-item)
│  └─ Puntuación 1-5
├─ Colgate-Palmolive (Sub-item)
│  └─ Puntuación 1-5
├─ Haleon (Sub-item)
│  └─ Puntuación 1-5
└─ Genomma Lab (Sub-item)
   └─ Puntuación 1-5
```

### Flujo de Usuario

**En lista lateral** (cuando selecciona OFERTAS):
```
[OFERTAS]
Precios correctos, promociones, exhibición

  🔵 Unilever        Sin puntuar
  ┌─────────────────────────────┐
  │ 1  2  3  4  5               │
  └─────────────────────────────┘

  🔵 Colgate-Palmolive  Sin puntuar
  ┌─────────────────────────────┐
  │ 1  2  3  4  5               │
  └─────────────────────────────┘

  🔵 Haleon          Sin puntuar
  ┌─────────────────────────────┐
  │ 1  2  3  4  5               │
  └─────────────────────────────┘

  🔵 Genomma Lab     Sin puntuar
  ┌─────────────────────────────┐
  │ 1  2  3  4  5               │
  └─────────────────────────────┘
```

**En panel principal** (cuando abre OFERTAS):
```
╔════════════════════════════════════════╗
║ OFERTAS & EXHIBICIÓN DE MARCAS         ║
║ Precios correctos, exhibición por marca║
╚════════════════════════════════════════╝

PUNTUACIÓN GENERAL
  1  2  3  4  5

EVALUACIÓN POR MARCA

┌─ ✓ Unilever                        5/5 ┐
│ [1] [2] [3] [4] [5]                     │
└─────────────────────────────────────────┘

┌─ ⭕ Colgate-Palmolive               ?   ┐
│ [1] [2] [3] [4] [5]                     │
└─────────────────────────────────────────┘

┌─ ⭕ Haleon                           ?   ┐
│ [1] [2] [3] [4] [5]                     │
└─────────────────────────────────────────┘

┌─ ⭕ Genomma Lab                     ?   ┐
│ [1] [2] [3] [4] [5]                     │
└─────────────────────────────────────────┘
```

### Props Nuevos

```typescript
interface AuditBlocksPanelAdvancedProps {
  bloques: AuditBloqueAdvanced[];
  activeBloque: AuditBloqueId | null;
  onSelectBloque: (bloqueId: AuditBloqueId) => void;
  onScoreChange: (bloqueId: AuditBloqueId, score: number) => void;
  
  // NUEVO: Para scores de marcas
  onBrandScoreChange?: (bloqueId: AuditBloqueId, brandId: string, score: number) => void;
}

interface BrandScore {
  id: string;              // 'unilever', 'colgate', 'haleon', 'genomma'
  nombre: string;          // 'Unilever', 'Colgate-Palmolive', etc
  puntuacion: number | null;
}
```

### Uso en AuditPerfumeriaV2

```typescript
const [bloques, setBloques] = useState<AuditBloqueAdvanced[]>(
  INITIAL_BLOQUES.map(b => ({
    ...b,
    subItems: b.id === 'OFERTAS' 
      ? [
          { id: 'unilever', nombre: 'Unilever', puntuacion: null },
          { id: 'colgate', nombre: 'Colgate-Palmolive', puntuacion: null },
          { id: 'haleon', nombre: 'Haleon', puntuacion: null },
          { id: 'genomma', nombre: 'Genomma Lab', puntuacion: null },
        ]
      : undefined,
  }))
);

const handleBrandScoreChange = (bloqueId: AuditBloqueId, brandId: string, score: number) => {
  setBloques(prev =>
    prev.map(b =>
      b.id === bloqueId && b.subItems
        ? {
            ...b,
            subItems: b.subItems.map(sub =>
              sub.id === brandId ? { ...sub, puntuacion: score } : sub
            ),
          }
        : b
    )
  );
};

// En JSX:
<AuditBlocksPanelAdvanced
  bloques={bloques}
  activeBloque={activeBloque}
  onSelectBloque={setActiveBloque}
  onScoreChange={handleScoreChange}
  onBrandScoreChange={handleBrandScoreChange}
/>
```

---

## 💬 2. WhatsAppAuditFlow.tsx

Mejora de flujo post-sucursal para elegir entre **Web** o **WhatsApp**:

### Ubicación
```
Sucursal Detail Page
├─ [Información de sucursal]
├─ [Auditoría Perfumería - botón]
└─ Click → Abre WhatsAppAuditFlow
```

### Interfaz

```
╔══════════════════════════════════════════════════════╗
║          FARMACIA CENTRO - ZONA NORTE                ║
║     Responsable: Juan García                         ║
╚══════════════════════════════════════════════════════╝

FLUJO DE AUDITORÍA
  1. ✓ Sucursal seleccionada
  2. ⭕ Responder cuestionario
  3. ⭕ Enviar fotos de desvíos
  4. ⭕ Auditoría completada

═══════════════════════════════════════════════════════

💬 OPCIÓN: Auditoría por WhatsApp
   Responde directamente en WhatsApp
   [Iniciar auditoría por WhatsApp]

🌐 OPCIÓN: Auditoría Web
   Interfaz mejorada en esta plataforma
   [Iniciar auditoría Web]
```

### Props

```typescript
interface WhatsAppAuditFlowProps {
  sucursal: Sucursal;
  onStartAudit: () => void;        // Abre AuditPerfumeriaV2
  steps?: AuditStep[];              // Pasos customizados
}
```

### Uso

```typescript
import { WhatsAppAuditFlow } from '../components/WhatsAppAuditFlow';

// En SucursalDetail.tsx
const [showAuditOptions, setShowAuditOptions] = useState(false);

{showAuditOptions && (
  <WhatsAppAuditFlow
    sucursal={sucursal}
    onStartAudit={() => {
      setShowAuditOptions(false);
      navigate(`/sucursales/${sucursal.id}/audit-perfumeria`);
    }}
  />
)}
```

### WhatsApp Message Template

El botón WhatsApp envía mensaje pre-poblado:
```
Hola, quiero hacer la auditoría de 
[SUCURSAL_NAME] ([SUCURSAL_ID]). 
¿Cómo procedo?
```

Coordinador recibe y puede responder con:
```
✓ Paso 1: Responde scores de áreas (1-5)
✓ Paso 2: Envía fotos de problemas
✓ Paso 3: Confirma auditoría completa
```

---

## ✅ 3. CompletionCheckmark.tsx

3 componentes para feedback visual de progreso:

### A) **CompletionCheckmark** (simple)
Muestra checkmark animado cuando algo se completa:

```typescript
<CompletionCheckmark
  completed={allScored}
  label="Todas las áreas puntuadas"
  animated={true}
/>
```

**Output**:
```
✓ Todas las áreas puntuadas
```

### B) **CompletionList** (lista con progreso)
Muestra lista de items con barra de progreso:

```typescript
const items = [
  { id: 'score-limpieza', label: 'Limpieza (5/5)', completed: true },
  { id: 'score-stock', label: 'Stock (4/5)', completed: true },
  { id: 'score-ofertas', label: 'Ofertas (3/5)', completed: true },
  { id: 'score-burbujas', label: 'Burbujas (?)', completed: false },
  { id: 'evidence', label: 'Evidencia capturada', completed: false },
];

<CompletionList
  items={items}
  title="Checklist de Auditoría"
/>
```

**Output**:
```
Checklist de Auditoría                    3/5

[████░░░░░░] 60% completado

 ✓ Limpieza (5/5)               ✓
 ✓ Stock (4/5)                  ✓
 ✓ Ofertas (3/5)                ✓
 ⭕ Burbujas (?)
 ⭕ Evidencia capturada
```

### C) **StepChecker** (pasos con animación)
Muestra progreso de pasos con líneas conectoras:

```typescript
const steps = [
  { id: 'step1', label: 'Puntuar áreas', status: 'completed' as const },
  { id: 'step2', label: 'Capturar evidencia', status: 'in-progress' as const },
  { id: 'step3', label: 'Revisar y enviar', status: 'pending' as const },
];

<StepChecker steps={steps} />
```

**Output**:
```
 ✓ Puntuar áreas
 │
 ◆ Capturar evidencia (pulsando)
 │
 ① Revisar y enviar

✓ 1/3 pasos completados • Actualmente: Capturar evidencia
```

---

## 🔧 Integración en AuditPerfumeriaV2

### Paso 1: Scoring (con checkmarks)
```typescript
import { CompletionCheckmark, CompletionList } from '../components/CompletionCheckmark';

// En Step 1:
<AuditBlocksPanelAdvanced
  bloques={bloques}
  onBrandScoreChange={handleBrandScoreChange}
/>

{allScored && (
  <CompletionCheckmark
    completed={true}
    label="Todas las áreas puntuadas ✓"
  />
)}
```

### Paso 2: Evidence (con StepChecker)
```typescript
import { StepChecker } from '../components/CompletionCheckmark';

const steps = [
  { id: 's1', label: 'Puntuar áreas', status: 'completed' },
  { id: 's2', label: 'Capturar evidencia', status: 'in-progress' },
  { id: 's3', label: 'Revisar y enviar', status: 'pending' },
];

<StepChecker steps={steps} />
<EvidenceCaptureGuided onAddEvidence={handleAddEvidence} />
```

### Paso 3: Summary (con CompletionList)
```typescript
<CompletionList
  items={bloques.map(b => ({
    id: b.id,
    label: `${b.nombre} - ${b.puntuacion}/5`,
    completed: b.puntuacion !== null,
  }))}
  title="Áreas Auditadas"
/>

{totalDesvios > 0 && (
  <CompletionList
    items={desviosAsItems}
    title={`Desvíos Encontrados (${completedDesvios}/${totalDesvios})`}
  />
)}
```

---

## 📱 SucursalDetail: Opción de Flujo

```typescript
// En SucursalDetail.tsx

const [auditMode, setAuditMode] = useState<'none' | 'web' | 'whatsapp'>('none');

// Render
{auditMode === 'none' && (
  <div className="flex gap-3">
    <Button onClick={() => setAuditMode('web')}>
      🌐 Auditoría Web
    </Button>
    <Button onClick={() => setAuditMode('whatsapp')}>
      💬 Auditoría WhatsApp
    </Button>
  </div>
)}

{auditMode === 'whatsapp' && (
  <WhatsAppAuditFlow
    sucursal={sucursal}
    onStartAudit={() => {
      setAuditMode('web');
    }}
  />
)}

{auditMode === 'web' && (
  <AuditPerfumeriaV2 sucursal={sucursal} />
)}
```

---

## 📊 Comparativa: Antes vs Después

| Aspecto | Antes | Después |
|---------|-------|---------|
| **OFERTAS** | Un bloque único | 4 marcas evaluadas por separado |
| **Audio de marcas** | No hay feedback | Checkmark cuando cada marca puntúa |
| **Flujo WhatsApp** | Solo mensaje | UI con opciones claras (Web vs WA) |
| **Progreso visual** | Progreso bar general | Checkmarks en cada subtarea |
| **Feedback** | Implícito | Explícito y animado |

---

## 🚀 Plan de Implementación

### Fase 1: Componentes Base
- ✅ AuditBlocksPanelAdvanced.tsx
- ✅ WhatsAppAuditFlow.tsx
- ✅ CompletionCheckmark.tsx

### Fase 2: Integración
- [ ] Actualizar AuditPerfumeriaV2.tsx para usar AuditBlocksPanelAdvanced
- [ ] Agregar CompletionCheckmark en cada paso
- [ ] Actualizar SucursalDetail para mostrar WhatsAppAuditFlow

### Fase 3: Testing
- [ ] Scoring de marcas funciona
- [ ] WhatsApp link envía mensaje correcto
- [ ] Checkmarks animan correctamente
- [ ] Responsive en móvil

### Fase 4: Deploy
- [ ] Merge a main
- [ ] Deploy a producción

---

## 💡 Ventajas Adicionales

### Para Auditor
- ✅ Visibilidad clara de que debe evaluar por marca
- ✅ Feedback visual instantáneo
- ✅ Opción de flujo preferido (Web vs WhatsApp)

### Para Gerente
- ✅ Datos más granulares (score por marca)
- ✅ Identificar marcas con problemas específicos
- ✅ Mejor seguimiento de exhibición

### Para Sistema
- ✅ Mejora experiencia sin cambios de BD
- ✅ Compatible con API existente
- ✅ Escalable (fácil agregar más marcas)

---

## 🎨 Estilos Utilizados

Todos los componentes usan **TailwindCSS** + **Lucide Icons**:

```css
/* Checkmark animado */
.animate-in { animation: slideInFromBottom 200ms ease-out; }

/* Progress bar smooth */
.transition-all { transition: all 0.5s ease-out; }

/* Pulse para "en progreso" */
.animate-pulse { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
```

---

## 📝 Archivos Modificados vs Nuevos

```diff
+ AuditBlocksPanelAdvanced.tsx (NUEVO)
+ WhatsAppAuditFlow.tsx (NUEVO)
+ CompletionCheckmark.tsx (NUEVO)
~ AuditPerfumeriaV2.tsx (MODIFICAR - usar Advanced panel)
~ SucursalDetail.tsx (MODIFICAR - agregar opciones de flujo)
```

---

**Status**: Ready for implementation  
**Complexity**: Medium  
**Impact**: High UX improvement  
**Backward Compatible**: Yes

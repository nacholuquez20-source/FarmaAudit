# Interfaz de Votación/Selección - Auditor

**Status**: ✅ Diseño propuesto  
**Contextos**: WhatsApp + Web  

---

## 🎯 Dos Escenarios

### 1. **WhatsApp Voting** (Auditoría por WhatsApp)
### 2. **Web Voting** (Auditoría Web en plataforma)

---

## 📱 ESCENARIO 1: WhatsApp Voting

### Flujo Completo

```
COORDINADOR INICIA AUDITORÍA
╔════════════════════════════════════════╗
║ ¡Hola Juan! Vamos a auditar           ║
║ Farmacia Centro (SC-001)              ║
║                                        ║
║ Paso 1: Puntúa cada área (1-5)        ║
║ Paso 2: Envía fotos de desvíos        ║
║ Paso 3: Confirma cuando termines      ║
╚════════════════════════════════════════╝

───────────────────────────────────────────

PREGUNTA 1: Limpieza & Organización
Estado de góndolas, orden general, polvo

  ◯ 1 (Muy malo)         0 votos
  ◯ 2 (Malo)             0 votos
  ◯ 3 (Regular)          0 votos
  ◯ 4 (Bueno)            0 votos
  ◯ 5 (Excelente)        0 votos

[Ver detalles]                    1:55 p.m.

───────────────────────────────────────────

AUDITOR SELECCIONA:
  → Toca "4 (Bueno)"

╔════════════════════════════════════════╗
║ ✓ Limpieza: 4/5 registrada             ║
║                                        ║
║ Siguiente: Stock & Inventario         ║
║ Niveles, productos vencidos, reposición║
║                                        ║
║  ◯ 1 (Muy malo)                       ║
║  ◯ 2 (Malo)                           ║
║  ◯ 3 (Regular)                        ║
║  ◯ 4 (Bueno)                          ║
║  ◯ 5 (Excelente)                      ║
╚════════════════════════════════════════╝

───────────────────────────────────────────

[Después de 4 puntuaciones]

COORDINADOR:
╔════════════════════════════════════════╗
║ ✓ Limpieza: 4/5                        ║
║ ✓ Stock: 3/5                           ║
║ ✓ Ofertas: 2/5 ⚠️ Desvío detectado     ║
║ ✓ Burbujas: 5/5                        ║
║                                        ║
║ ¡Perfecto! Ahora necesito fotos       ║
║ del área Ofertas que tiene problemas  ║
║                                        ║
║ 📸 Por favor, envía foto de:          ║
║    - Precios no actualizados          ║
║    - Promociones vencidas             ║
║    - Carencias de stock visible       ║
║                                        ║
║ 💬 O describe el problema             ║
╚════════════════════════════════════════╝

───────────────────────────────────────────

AUDITOR ENVÍA EVIDENCIA:
  → Foto 1: [IMG]
  → Foto 2: [IMG]
  → Texto: "Las promociones vencidas están desde ayer"

───────────────────────────────────────────

COORDINADOR CONFIRMA:
╔════════════════════════════════════════╗
║ ✓ Auditoría Completada                 ║
║                                        ║
║ Resumen:                               ║
║  • 4 áreas puntuadas                   ║
║  • 2 desvíos detectados                ║
║  • 2 fotos evidencia                   ║
║  • Severidad: Media                    ║
║                                        ║
║ Status: Enviada a revisión             ║
║                                        ║
║ El gerente la revisará pronto          ║
╚════════════════════════════════════════╝
```

---

## 🌐 ESCENARIO 2: Web Voting (Mejorado)

Versión elegante en la plataforma web:

### PASO 1: Scoring

```
╔═══════════════════════════════════════════════════════════════╗
║ AUDITORÍA PERFUMERÍA - Farmacia Centro                        ║
║                                                               ║
║ Progreso: ████░░░░░░ 33% | Paso 1: Puntuar Áreas            ║
╚═══════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────┐
│                                                               │
│  LIMPIEZA & ORGANIZACIÓN                            4/5 ✓   │
│  Estado de góndolas, orden general, polvo                    │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 1       2       3       4       5                   │    │
│  │ Muy     Malo    Regular Bueno   Excelente          │    │
│  │ malo                                                │    │
│  │ [_]    [_]     [_]     [✓]     [_]               │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                                                               │
│  STOCK & INVENTARIO                                 3/5 ✓   │
│  Niveles de inventario, productos vencidos, reposición      │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 1       2       3       4       5                   │    │
│  │ [_]    [_]     [✓]     [_]     [_]               │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
└─────────────────────────────────────────────────────────────┘

[Continuar →]
```

### PASO 2: Scoring con Marcas (OFERTAS)

```
┌─────────────────────────────────────────────────────────────┐
│                                                               │
│  OFERTAS & EXHIBICIÓN DE MARCAS                     2/5 ⚠️  │
│  Precios, promociones, exhibición por marca                  │
│                                                               │
│  PUNTUACIÓN GENERAL:                                        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 1       2       3       4       5                   │    │
│  │ [_]    [✓]     [_]     [_]     [_]               │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  DESGLOSE POR MARCA:                                        │
│                                                               │
│  ┌─ Unilever                                        ✓ 4/5 ─┐
│  │ ┌──────────────────────────────────────────────┐         │
│  │ │ [_]  [_]  [_]  [✓]  [_]                    │         │
│  │ └──────────────────────────────────────────────┘         │
│  └──────────────────────────────────────────────────────────┘
│
│  ┌─ Colgate-Palmolive                                   ? ─┐
│  │ ┌──────────────────────────────────────────────┐         │
│  │ │ [_]  [_]  [✓]  [_]  [_]                    │         │
│  │ └──────────────────────────────────────────────┘         │
│  └──────────────────────────────────────────────────────────┘
│
│  ┌─ Haleon                                            ? ─┐
│  │ ┌──────────────────────────────────────────────┐       │
│  │ │ [_]  [_]  [_]  [✓]  [_]                    │       │
│  │ └──────────────────────────────────────────────┘       │
│  └──────────────────────────────────────────────────────────┘
│
│  ┌─ Genomma Lab                                     2/5 ✓ ─┐
│  │ ┌──────────────────────────────────────────────┐         │
│  │ │ [_]  [✓]  [_]  [_]  [_]                    │         │
│  │ └──────────────────────────────────────────────┘         │
│  └──────────────────────────────────────────────────────────┘
│                                                               │
└─────────────────────────────────────────────────────────────┘

[Atrás] [Continuar →]
```

### PASO 2: Captura de Evidencia

```
┌─────────────────────────────────────────────────────────────┐
│ AUDITORÍA - Paso 2: Capturar Evidencia               66%    │
└─────────────────────────────────────────────────────────────┘

OFERTAS & EXHIBICIÓN tiene problemas (2/5)

Selecciona una opción para agregar evidencia:

  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
  │  │    📷       │  │    🎤       │  │    ✏️       │ │
  │  │    FOTO     │  │    AUDIO    │  │    TEXTO    │ │
  │  └─────────────┘  └─────────────┘  └─────────────┘ │
  │                                                     │
  └─────────────────────────────────────────────────────┘

O completa sin agregar más evidencia ↓

Desvíos Detectados en OFERTAS:
  ✓ Precio incorrecto (foto)
  ✓ Promoción vencida (foto)
  ⭕ Exposición Genomma (sin descripción aún)

[Atrás] [Revisar y enviar →]
```

### PASO 3: Resumen/Votación Final

```
┌─────────────────────────────────────────────────────────────┐
│ AUDITORÍA - Paso 3: Revisar y Enviar                100%    │
└─────────────────────────────────────────────────────────────┘

RESUMEN DE AUDITORÍA - Farmacia Centro

PUNTUACIONES:
  ┌────────────────────────────────────┐
  │ Limpieza        │████████░░│ 4/5 ✓ │
  │ Stock           │██████░░░░│ 3/5 ✓ │
  │ Ofertas         │██░░░░░░░░│ 2/5 ✓ │
  │ Burbujas        │██████████│ 5/5 ✓ │
  └────────────────────────────────────┘

DESVÍOS ENCONTRADOS (2/2):
  ✓ Ofertas → Precio incorrecto
    📷 Foto capturada
    
  ✓ Ofertas → Promoción vencida
    📷 Foto capturada

═══════════════════════════════════════

¿ESTÁS SEGURO DE ENVIAR?

  [Atrás - Editar]  [✓ Enviar Auditoría]

Al enviar:
  • El gerente recibirá la auditoría
  • Se crearán tareas para desvíos
  • El responsable recibe WhatsApp
```

---

## 🎨 Comparativa: WhatsApp vs Web

| Aspecto | WhatsApp | Web |
|---------|----------|-----|
| **Interfaz** | Lista de opciones (1,2,3,4,5) | Botones grandes + visual |
| **Confirmación** | Automática al tocar | Checkmark animado |
| **Evidencia** | Foto o texto directo | Modal guiado paso a paso |
| **Progreso** | Checkmark anterior | Barra + indicador visual |
| **Resumen** | Corto (texto) | Completo (tablas, gráficos) |
| **Marcas** | Preguntas separadas | Desglose visual |
| **Mejor para** | Rápido, móvil, tráfico | Completo, calidad, auditoría |

---

## 💡 Interactividad en Web

### Voting Button States

```
ESTADO 1: NO SELECCIONADO
  ┌─────────────────┐
  │   1: Muy malo   │
  │  (gris claro)   │
  └─────────────────┘

ESTADO 2: HOVER (sobre el botón)
  ┌─────────────────┐
  │   1: Muy malo   │
  │  (gris más claro) border azul
  └─────────────────┘

ESTADO 3: SELECCIONADO
  ┌─────────────────┐
  │ ✓ 1: Muy malo   │
  │  (azul oscuro)  │
  └─────────────────┘

ESTADO 4: COMPLETO (after all 4 areas)
  ┌─────────────────┐
  │ ✓ 1: Muy malo   │
  │ (verde)         │
  └─────────────────┘
```

### Animaciones

```
1. SELECCIONAR OPCIÓN
   → Enlarge button (110%)
   → Color change (gray → blue)
   → Checkmark slides in
   → Bounce animation

2. COMPLETAR BLOQUE
   → All buttons turn green
   → Checkmark animation
   → Next section slides up

3. COMPLETAR TODO
   → Confetti animation
   → "Ready to submit" badge
   → Button glow effect
```

---

## 📊 UX Flow: Voting Decision Tree

```
¿Dónde vota el auditor?

    ├─ WhatsApp (Rápido)
    │  ├─ Coordinador: "Puntúa Limpieza"
    │  ├─ Auditor: toca "4" en la lista
    │  ├─ Coordinador: "✓ Registrado. Siguiente: Stock"
    │  └─ Repeat...
    │
    └─ Web (Completo)
       ├─ Paso 1: Puntúa 4 áreas (5 botones cada una)
       ├─ Paso 2: Captura evidencia
       │  └─ Foto/Audio/Texto por desvío
       ├─ Paso 3: Resumen visual completo
       └─ Enviar → Sistema registra todo
```

---

## ✨ Mejoras Visuales por Contexto

### WhatsApp (Limitaciones)
✅ Lista simple (1, 2, 3, 4, 5)
✅ Emojis para feedback (✓ ⚠️ 🎤 📷)
✅ Mensajes cortos y claros
✅ Links a plataforma si necesita más detalle

### Web (Full Experience)
✅ Botones grandes y coloridos
✅ Animaciones suaves
✅ Iconos descriptivos
✅ Desglose por marca (OFERTAS)
✅ Indicadores de progreso
✅ Preview de fotos
✅ Resumen antes de enviar

---

## 🎯 Recomendación

**Para auditor en terreno (rápido)**:
→ WhatsApp (simple, directo, sin distracciones)

**Para auditor en oficina/sucursal (cuidadoso)**:
→ Web (visual, completo, con evidencia clara)

**Permítele elegir** en el flujo de inicio:
```
┌──────────────────────────────┐
│ ¿Cómo prefieres auditar?     │
│                              │
│ [💬 WhatsApp - Rápido]      │
│ [🌐 Web - Completo]         │
└──────────────────────────────┘
```

---

**Status**: Diseño validado  
**Complexity**: Moderate  
**Implementation**: Ready with WhatsAppAuditFlow component

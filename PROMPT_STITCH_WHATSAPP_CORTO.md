# FarmaAudit - Flujo WhatsApp (Versión Corta para Stitch)

## El Flujo en 3 Pasos

### 1️⃣ AUDITOR (WhatsApp)
- Encuentra desvio en sucursal
- Envía: "Medicamento ABC vencido en vidriera"
- Bot parsea con Claude, propone severidad/área
- Auditor confirma: "SI"
- Desvio creado y **responsable notificado**

### 2️⃣ RESPONSABLE (WhatsApp + App)
- Recibe notificación del desvio
- Inicia plan de acción
- **Envía fotos de la solución**
- Escribe comentario: "Problema resuelto, stock verificado"
- Estado cambia a "En_proceso" → "Resuelta"

### 3️⃣ AUDITOR (App Web)
- Ve notificación: "Nuevas fotos en FAR-001"
- Abre detalles del desvio
- **Revisa fotos + comentarios**
- Aprueba → Cerrada ✅
- O rechaza → responsable debe completar

---

## Estados de un Desvio

```
ABIERTA → EN_PROCESO (responsable inicia) → RESUELTA (envía fotos) → CERRADA (auditor aprueba)
```

---

## Componentes Frontend Necesarios

### 1. Chat Integrado (en Detalles Desvio)
- Mensajes auditor (azul, derecha)
- Mensajes responsable vía bot (gris, izquierda)
- Fotos inline con preview
- Timestamps relativos ("hace 15 min")
- Input para auditor comentar

### 2. Galería de Fotos
- Grid de thumbnails
- Click → Lightbox
- Metadata: quién, cuándo, descripción
- Foto "cargándose..." mientras se descarga

### 3. Timeline de Eventos
- Eventos visuales (creación, estado, fotos, cierre)
- Con iconos y timestamps
- Ejemplo: "Juan M. envió fotos (hace 1h) [Ver]"

### 4. Badge de Estado
- Coloreado por estado (Abierta=azul, En_proceso=naranja, Resuelta=verde, Cerrada=gris)
- Muestra plazo restante ("24h, vence en 12h")
- Icono de "Responsable activo ✓"

### 5. Botones Contextuales
- Si estado=Resuelta: [✓ Aprobar] [✗ Rechazar]
- Si auditor: [💬 Comentar] [☎️ Contactar por WA]
- Si responsable: [📷 Subir fotos] [Marcar en proceso]

### 6. Notificación Real-Time
- Toast cuando llegan fotos: "Juan M. envió 2 fotos"
- Actualización automática del chat sin refrescar

---

## Flujo Técnico: WhatsApp → Supabase → Frontend

```
Responsable envía foto en WA
       ↓
Meta Cloud API → Backend
       ↓
Backend descarga foto, guarda en Drive
       ↓
Crea evento "evidencia" en Supabase
       ↓
Frontend recibe actualización (real-time)
       ↓
Foto aparece en galería automáticamente
       ↓
Auditor recibe notificación toast
```

---

## Datos que el Frontend Recibe

Tabla `Eventos` con filas como:
```json
{
  "id": "evt-123",
  "id_gestion": "FAR-001",
  "tipo": "evidencia",
  "comentario": "Foto de solución",
  "actor_nombre": "Juan M.",
  "actor_id": "user-456",
  "timestamp": "2026-06-03T14:30:00Z",
  "metadata": {
    "foto_url": "https://drive.google.com/...",
    "foto_local_filename": "medicamento-retirado.jpg"
  }
}
```

---

## UX Improvements

✅ Chat integrado (no modal separado)
✅ Fotos se ven inmediatamente al llegar
✅ Timeline clara de todo lo que pasó
✅ Botones grandes y claros para acciones
✅ Colores + iconos para estados (no solo color)
✅ Timestamps "hace X minutos" actualizado
✅ Responsable info siempre visible (nombre, tel, sucursal)
✅ Link directo WhatsApp para contactar
✅ Notificaciones toast para eventos importantes
✅ Responsive mobile para ver desde WhatsApp

---

## Componentes Reutilizables

```
<ChatMessage actor="responsable" text="..." timestamp="..." />
<PhotoGallery eventos={eventos} />
<Timeline eventos={eventos} />
<EstadoBadge estado="En_proceso" tiempoRestante={12h} />
<DesvioCard estado="Resuelta" evidencia={true} />
<NotificationToast type="info" message="Nuevas fotos" />
```

---

## Testing Checklist

- [ ] Foto enviada en WA aparece en galería en <3s
- [ ] Chat se actualiza sin refrescar página
- [ ] Botones de acción solo aparecen si corresponde (rol + estado)
- [ ] Timeline muestra eventos en orden cronológico
- [ ] Mobile: fotos legibles en teléfono
- [ ] Accesibilidad: colores + iconos, no solo color

---

## Tech Stack para Implementar

- **Real-time**: Supabase real-time subscriptions (no polling)
- **State**: React Query para refrescar datos
- **UI**: Tailwind + componentes custom
- **Photos**: Lazy load, lightbox library
- **Notifs**: Sonner toasts
- **Sync**: useEffect + cleanup para subscripciones

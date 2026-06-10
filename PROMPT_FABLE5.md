# PROMPT PARA ANÁLISIS Y MEJORAS — FarmaAudit

Copia desde aquí hacia abajo:

---

Eres un consultor senior en producto + arquitectura de software especializado en sistemas de gestión de calidad y automatización conversacional. Te voy a describir en detalle mi aplicación en producción. Tu tarea final está al pie del documento.

# 1. QUÉ ES FARMAAUDIT

**FarmaAudit (AuditBot)** es un sistema de auditorías operativas de calidad para una cadena de **25 farmacias/perfumerías "Plazoleta"** en Tucumán, Argentina. Su objetivo NO es castigar con puntajes, sino **gestión de mejora continua**: cada problema detectado (desvío) genera un plan de acción con responsable, plazo y seguimiento hasta su cierre.

**El diferencial clave**: los auditores NO usan planillas de papel ni apps complicadas. Hacen TODA la auditoría conversando por **WhatsApp** con un bot, enviando fotos, audios y textos mientras caminan por la sucursal. El sistema estructura automáticamente esa información desordenada en registros de calidad formales.

## Usuarios y roles
1. **Auditores** (cuadrillas de Farmacia y Perfumería): recorren sucursales, auditan por WhatsApp
2. **Encargados de sucursal**: reciben notificaciones de desvíos por WhatsApp, responden con evidencia de resolución
3. **Coordinadores/Gerencia**: panel web con dashboard, gestión de desvíos, fichas PDF
4. **Admin**: gestión de usuarios del panel

# 2. STACK TÉCNICO

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3 + FastAPI + Uvicorn, deploy en Railway |
| Base de datos | Supabase (PostgreSQL + RLS + Storage) |
| Mensajería | Meta WhatsApp Cloud API (webhooks, media download, mensajes interactivos: list messages + quick reply buttons) |
| Frontend | React + TypeScript + Material UI (panel web) |
| IA | Claude API (parseo de hallazgos en lenguaje natural a registros estructurados) |
| PDF | ReportLab (fichas de auditoría) |
| Storage docs | Google Drive (PDFs de fichas) |
| Jobs | APScheduler (timeouts, recordatorios, resumen diario, limpieza de sesiones) |
| Validación de fotos | PIL puro: dimensiones mín 320x320, máx 10MB, MIME jpeg/png, detección de blur por varianza Laplaciana (umbral 80) |

# 3. FLUJO PRINCIPAL: AUDITORÍA DE PERFUMERÍA v2 (WhatsApp)

Máquina de estados en memoria (sesión por teléfono, TTL 24h):

```
IDLE → SCORING → BLOQUE_EVIDENCE_COLLECTION → (SCORING_BRANDS solo para OFERTAS) → SUMMARY → DONE
```

**Paso a paso real:**
1. Auditor escribe "hola" → menú de 25 sucursales numeradas → responde con número
2. Se crea sesión v2 en estado SCORING. Bot envía **list message interactivo** (UI nativa de WhatsApp) para puntuar el primer bloque
3. **4 bloques en orden**: LIMPIEZA (góndolas, orden, polvo) → STOCK (niveles, vencidos, reposición) → OFERTAS (precios, promociones, exhibición) → BURBUJAS (displays, señalización)
4. Puntuación 1-5 por bloque seleccionando de lista: 1=Muy malo, 2=Malo, 3=Regular, 4=Bueno, 5=Excelente
5. Tras puntuar, se muestra **comparación histórica** vs auditoría anterior de esa sucursal (⬆️ +1, ⬇️ -1, ➡️ igual)
6. Entra en modo **recolección de evidencia libre**: el auditor envía fotos (se validan automáticamente, se rechazan borrosas), audios y textos EN CUALQUIER ORDEN; todo queda vinculado al bloque actual. Tras cada foto se ofrecen **notas predefinidas** por bloque (ej. "Góndolas desorganizadas", "Productos vencidos") para estandarizar terminología
7. El auditor controla el ritmo: escribe **"SIGUIENTE"** cuando termina el bloque → resumen de evidencia recolectada (X fotos, Y audios, Z notas) → siguiente bloque
8. **OFERTAS tiene desglose por marca**: tras la puntuación general, puntúa individualmente Unilever, Colgate-Palmolive, Haleon y Genomma Lab (1-5 cada una)
9. Al terminar los 4 bloques → **RESUMEN completo** (puntuaciones, desvíos, fotos) → confirmación con **quick reply buttons** [✅ Sí, enviar] [❌ No, editar]
10. Al confirmar: se guarda en BD, si hay desvíos pregunta **"¿A nombre de quién se registran los desvíos?"** (responsable), genera **ficha PDF**, notifica al gerente por WhatsApp, ofrece [📄 Ficha] [❌ No]

# 4. MODELO DE DATOS (Supabase)

- **reportes**: hallazgo individual (área, descripción, auditor, foto_url, severidad, timestamp)
- **gestiones**: plan de acción por desvío (id_reporte, estado: Abierta/En_proceso/Resuelta/Cerrada/Vencida, severidad: Alta/Media/Baja, responsable, tel_responsable, plazo_fecha, plan_accion, fecha_cierre, cerrado_por)
- **desvio_eventos**: timeline de cada gestión (tipo de evento, actor, comentario, evidencia, timestamp) — trazabilidad completa
- **audit_fiches**: metadata de PDFs (sucursal, auditor, responsable_desvios, fecha, url_pdf, google_drive_id, desvios_count, fotos_count, puntuacion_promedio)
- **sucursales** (25), **auditores**, **conversaciones** (estado conversacional), **sesiones_auditoria** (flujo viejo de farmacia), **checklist_perfumeria**, **webhook_dedup** (anti-duplicados de Meta)

**Mapeo score→severidad**: 1-2 = ALTA, 3 = MEDIA, 4-5 = BAJA

# 5. CICLO DE VIDA DEL DESVÍO (post-auditoría)

1. Auditoría confirmada → se crea Gestion (Abierta) + Reporte + DesvioEvento por cada desvío
2. Encargado de sucursal recibe WhatsApp con el desvío y plazo
3. Encargado puede responder por WhatsApp con texto/foto de resolución
4. Coordinador ve todo en panel web: puede marcar En_proceso, Resuelta, Cerrada, agregar comentarios y evidencia
5. Job automático marca Vencida si pasa el plazo
6. Timeline completo visible en la web (quién hizo qué y cuándo)

# 6. PANEL WEB (React)

- **Dashboard** de desvíos con filtros por estado/severidad/sucursal
- **Detalle de desvío**: info, responsable, panel de resolución, timeline con iconos, lightbox de fotos, botón contactar por WhatsApp, notificar encargado
- **Galería de fichas PDF**: grid de tarjetas con badge de puntuación coloreado (verde ≥4, amarillo ≥3, rojo <3), filtros por sucursal + auditor + rango de fechas (desde/hasta), paginación, modal de detalle, descarga de PDF desde Google Drive
- **Mis desvíos**: vista para encargados
- **Admin**: gestión de usuarios del panel

# 7. API PRINCIPAL

- `POST /webhook` — entrada de mensajes de WhatsApp (con dedup, locks por teléfono, routing por sesión activa v2 vs flujo legado)
- `GET /api/audit-fiches/list?sucursal_id&fecha_desde&fecha_hasta&auditor_nombre&limit&offset`
- `GET /api/audit-fiches/sucursales`
- `GET /api/audit-fiches/{id}`
- `POST /api/gestion/{id}/mensajes`, `POST /api/send-encargado-notification`
- `GET/POST/PATCH /api/admin/panel-users`

# 8. DECISIONES DE DISEÑO IMPORTANTES

- **Filosofía no punitiva**: el lenguaje del bot y los reportes enfatizan mejora, no castigo
- **El auditor controla el ritmo** (keyword SIGUIENTE), porque en la sucursal real registran muchas cosas seguidas de un mismo bloque
- **Mensajes interactivos nativos** (listas y botones) en vez de "responde 1-5" para minimizar errores de tipeo
- **Validación de fotos en el momento**: una foto borrosa se rechaza al instante, no se descubre después
- **Sesiones en memoria** (riesgo conocido: se pierden con redeploy; Redis es upgrade pendiente)
- **Dos sistemas conviven**: flujo viejo de farmacia (checklist 8 bloques, BD) y flujo v2 de perfumería (state machine, memoria)
- **Locks por teléfono** para evitar condiciones de carrera con webhooks duplicados de Meta

# 9. LIMITACIONES CONOCIDAS / DEUDA TÉCNICA

- Sesiones v2 en memoria (sin Redis) — se pierden al redeploy
- Audios se guardan como "[AUDIO] sin transcripción" — no hay speech-to-text todavía
- El PDF se genera pero el envío del archivo por WhatsApp está pendiente (hoy se envía link/confirmación)
- No hay modo offline (sucursales con mala señal)
- No hay edición de auditoría tras el resumen (el botón "No, editar" solo pregunta qué cambiar)
- Analytics básicos: no hay dashboard de tendencias por sucursal/bloque/tiempo

---

# TU TAREA

Con todo este contexto, quiero que generes **mejoras ÚNICAS y de alto impacto** — no me repitas lo obvio (Redis, transcripción, offline ya lo sé). Específicamente:

1. **3 features diferenciales** que ningún sistema de auditoría típico tiene, aprovechando que TODO pasa por WhatsApp y que tenemos historial de puntuaciones, fotos y desvíos por sucursal. Piensa en: gamificación para encargados, IA sobre el historial, detección de patrones, comparación entre sucursales, predicción de problemas.

2. **1 mejora de UX conversacional** que haga la auditoría más rápida o más confiable para el auditor en piso (hoy tarda ~10 min por sucursal).

3. **1 mejora para gerencia** que convierta los datos acumulados en decisiones (ranking, alertas inteligentes, reportes automáticos semanales, etc.).

4. Para CADA propuesta: nombre, problema que resuelve, cómo funcionaría (flujo concreto), esfuerzo estimado (S/M/L), y qué tabla/endpoint/componente nuevo requeriría sobre el stack descrito.

5. Elegí UNA de tus propuestas como "la apuesta" y justificá por qué empezarías por esa.

Sé concreto y accionable: quiero poder implementar tu propuesta directamente sobre esta arquitectura.

# Arquitectura — Módulo Desvíos por Farmacia + Módulo Campañas

> **v2 — versión superadora.** Documento consolidado a partir de los veredictos de 6 agentes:
> **UX/UI**, **Meta/WhatsApp**, **Procesos**, **Usos y Costumbres**, **Especialista en Farmacias/Perfumería** y el **Sintetizador** (2026-07-27).
> Es la especificación para la implementación (fase de desarrollo con Sonnet).
> Fuente de verdad de convenciones: el código (`router.py`, `models.py`, `supabase_manager.py`, `frontend/src/lib`), NO los `.md` viejos de la raíz.
> Los agregados de esta versión están marcados **(v2 — especialista)** para que sean rastreables contra la v1.

---

## Resumen de veredictos

| Agente | Veredicto | Hallazgo central |
|---|---|---|
| UX/UI | Aprobado con condiciones | La tabla agrupada por sucursal YA existe (`DesviosGestion.tsx`, vista "Por sucursal"). El gap real es el badge de fila "corregido, pendiente de revisión" + panel aprobar/rechazar. |
| Meta/WhatsApp | Viable con condiciones | Corrección de desvío por WhatsApp ya construida al 90% (`router.py:407-571`). Campañas requiere templates UTILITY aprobados por Meta y nuevos estados conversacionales. Riesgo serio: un solo `estado_actual` por teléfono en `conversaciones`. |
| Procesos | Aprobado con condiciones | Falta la transición rechazar→reabrir (no existe en `GestionState`). Máquinas de estado definidas abajo. Decisión de negocio pendiente: quién aprueba insumos. |
| Usos y Costumbres | Aprobado con condiciones | No reconstruir el Módulo 1. Colisión de nombre: el bloque de auditoría `BURBUJAS` ≠ "burbuja de descuento" de campañas. Tablas sin ñ: `campanias`. Vocabulario del rubro: exhibición, material POP, cartelería, puntera, burbuja de precio. |
| **Especialista Farmacias/Perfumería (v2)** | Aprobado con cambios obligatorios | Valida la base (no reconstruir Módulo 1, rechazo sin estado persistente, escalamiento al 3er rechazo, colisión BURBUJAS, multi-campaña paralela, polling, templates UTILITY, diferir WhatsApp en auditoría activa). Corrige el modelo de negocio: el material POP lo trae el laboratorio (no la cadena), falta SLA del lado auditor, el bot puede saturar al encargado, falta un estado para causas ajenas al encargado, "descuento en caja" no es lo mismo que "cartelería de precio", y el sistema mide compliance pero no venta real. |
| **Sintetizador (v2)** | Integrado | Este documento incorpora los 10 cambios obligatorios del especialista sobre la base ya aprobada por los 4 agentes anteriores; no se descarta ninguna decisión previa. |

---

## MÓDULO 1 — Desvíos por Farmacia (ciclo de corrección/revisión)

### 1.1 Qué ya existe (NO reconstruir)

- Tabla agrupada por sucursal: `frontend/src/pages/DesviosGestion.tsx` (toggle "Vista → Por sucursal", `GroupHeader`).
- El encargado responde por WhatsApp con texto+foto: `router.py:407-571` (estados `ENCARGADO_SELECCIONANDO_DESVIO` / `ENCARGADO_ESPERANDO_RESPUESTA`), evidencia a bucket `desvio-evidencias` (`supabase_manager.py:908`), evento en `desvio_eventos` (`save_encargado_evento`, línea 1057).
- Notificación in-app a auditores: `create_notifications_for_auditors` → `desvio_notificaciones` tipo `encargado_respondio`; campanita global con polling 30s (`useNotificaciones.ts`, `AppLayout.tsx:162-174`).
- Timeline y detalle: `DesvioTimeline.tsx`, `DesvioResponsibleCard.tsx`, `ImageLightbox.tsx`.

### 1.2 Qué falta (trabajo real)

1. **Estado `En_revision`** en `gestion` (extender enum `GestionState` en `models.py:61-68` + check constraint SQL). Se setea cuando el encargado envía su corrección (hoy `_handle_encargado_respuesta` no toca `gestion.estado`).
2. **Acción Aprobar / Rechazar** para auditor/admin:
   - **Aprobar** → `estado = 'Resuelta'` (o directo `Cerrada`, según flujo actual de `handleClose`) + evento `cierre` + marcar notificación como leída (`marcarNotificacionLeida`, `api.ts:363`).
   - **Rechazar** → NO crear estado "Rechazada": transición momentánea que vuelve a `En_proceso` + evento nuevo `tipo='rechazo'` con `comentario` (motivo) **obligatorio** + nueva `plazo_fecha` (+48h configurable, preservando `plazo_fecha_original`) + contador `veces_rechazado++` + WhatsApp al encargado. Mismo patrón que `_mark_persiste()` (evento sin estado persistente).
3. **Badge de fila** en la tabla: cuando `estado === 'En_revision'`, reemplazar `EstadoBadge` por badge clicable `[🟢 CORREGIDO ●n]` (contador de notificaciones `encargado_respondio` no leídas de ese `id_gestion`). Click abre el drawer directo en la tab nueva **"Revisión"**.
4. **Tab "Revisión"** en el `DetailDrawer` de `DesviosGestion.tsx`: respuesta del encargado + fotos reales + botones Aprobar/Rechazar (con textarea de motivo). Componente nuevo: `components/desvio-detail/DesvioCorrectionReviewPanel.tsx`.
5. **Fix obligatorio**: el tab "Evidencias" del drawer (`DesviosGestion.tsx:447-463`) es un placeholder decorativo — reemplazar por `ImageLightbox` + URL firmada real (patrón `EvidenceThumb` de `RevisionDesvios.tsx:35-86`).
6. **Feedback WhatsApp al encargado** tras la revisión:
   - Dentro de ventana de 24h: `send_text` ("✅ Corrección aprobada…" / "❌ Rechazada: {motivo}…" reabriendo el flujo `ENCARGADO_*`).
   - Fuera de ventana: template UTILITY `desvio_correccion_revisada` (ver §3.3 → ahora §2.4).
   - Endpoint FastAPI nuevo: `POST /api/gestion/{id_gestion}/revision` con body `{accion: 'aprobar'|'rechazar', motivo?, actor_id}`.
7. **(v2 — especialista) SLA de revisión del auditor**: el ciclo actual solo pone plazos al encargado; el desvío puede quedar en `En_revision` indefinidamente sin que la auditora lo mire. Campo `gestion.en_revision_desde timestamptz` (se setea al entrar a `En_revision`). Job `remind_sla_auditor_revision` (§2.6) alerta a auditor/coordinador si supera **72h** sin resolución. En el filtro "Pendiente de revisión" (§1.4) mostrar antigüedad ("hace 4 días esperando revisión"), ordenado por más antiguo primero.
8. **(v2 — especialista) Estado `En_gestion_terceros`**: hay desvíos que no se pueden corregir en 48h por causas ajenas al encargado (falta de droguería, obra, personal). La auditora puede setear este estado manualmente desde el panel de revisión/detalle. Mientras está en `En_gestion_terceros`: no cuenta como incumplimiento, no escala al encargado, no dispara los jobs de vencimiento (§2.6/§3). Requiere comentario obligatorio. Vuelve a `En_proceso` cuando la auditora lo desbloquea manualmente (no hay transición automática).

### 1.3 Máquina de estados del desvío (final, v2)

```
Abierta → En_proceso → [encargado envía corrección+foto] → En_revision (en_revision_desde = now())
En_revision --aprobar (auditor)--> Resuelta → Cerrada (terminal)
En_revision --rechazar (auditor, motivo obligatorio)--> En_proceso
             (nueva plazo_fecha, veces_rechazado++, WhatsApp al encargado)
{Abierta, En_proceso, En_revision} --auditor marca "depende de terceros" (v2, motivo obligatorio)--> En_gestion_terceros
En_gestion_terceros --auditor desbloquea manualmente--> En_proceso
                     (no escala, no cuenta incumplimiento, no vence mientras está en este estado)
{Abierta, En_proceso, En_revision} --plazo vencido (job 15min)--> Vencida
Vencida --retoma--> En_proceso / En_revision
En_revision --SLA auditor > 72h sin resolver (v2, job)--> alerta a auditor/coordinador (no cambia de estado)
```

Campos nuevos en `gestion`: `plazo_fecha_original date`, `veces_rechazado int default 0`, `en_revision_desde timestamptz` **(v2 — especialista)**.
Regla de escalamiento: al 3er rechazo, alerta a `coordinador_tel` (mismo mecanismo que `SEVERITY_ESCALATION`).
Nuevo valor en `DesvioEventoTipo` (frontend `types/index.ts:13`): `'rechazo'`.
Nuevo valor en `GestionState`: `'En_gestion_terceros'` **(v2 — especialista)**.

### 1.4 UX

- Filtro `FilterChip` "Pendiente de revisión" como vista default cuando hay notificaciones `encargado_respondio` sin leer, ordenado por más antiguo primero y con antigüedad visible por fila **(v2 — especialista)**.
- Chip "N pendientes de revisión" en el `GroupHeader` de cada farmacia.
- Diferenciar visualmente origen de la resolución (WhatsApp del encargado vs. auto-resuelto por el auditor desde el panel) usando `DesvioEvento.metadata`.
- Badge distinto para `En_gestion_terceros` (color neutro, no de alarma) **(v2 — especialista)**, para que no se lea como incumplimiento del encargado.
- Polling: mantener el patrón existente (15–20s en esta vista); NO introducir Supabase Realtime como segundo paradigma salvo que se extiendan los hooks realtime ya existentes (`useEvidenciaRealtimeUpdates`).

---

## MÓDULO 2 — Campañas (nuevo, desde cero)

### 2.1 Modelo de datos (tablas nuevas — sin ñ, español snake_case)

```sql
marcas               (id, nombre, activo bool, created_at)          -- catálogo CRUD desde Admin

campanias            (id, nombre, marca_id → marcas,
                      estado: Borrador|Activa|En_seguimiento|Finalizada|Cancelada,
                      fecha_inicio, fecha_fin, creado_por → profiles,
                      vigencia_acuerdo daterange,                    -- (v2 — especialista) vigencia del acuerdo comercial labo↔cadena
                      contraprestacion text)                         -- (v2 — especialista) qué recibe la cadena a cambio (texto libre alcanza)

campania_acciones    (id, campania_id, tipo: exhibicion|material_pop|burbuja_precio|descuento_caja|custom,
                      -- (v2 — especialista) "burbuja_descuento" (v1) se separa en dos acciones distintas:
                      --   burbuja_precio: cartelería física en el mueble/puntera, verificable por foto del encargado
                      --   descuento_caja: activación del descuento en el sistema de caja, depende de OTRO sistema/área,
                      --                   NO la verifica el encargado con una foto
                      descripcion, requiere_foto bool,
                      verificable_por_foto bool default true)        -- (v2 — especialista) false para descuento_caja: acción informativa/administrativa

campania_tareas      (id, campania_id, accion_id → campania_acciones,
                      id_sucursal → sucursales, responsable, tel_responsable,  -- desnormalizado como gestion
                      estado: Pendiente|Completada|Bloqueada_por_insumo|Verificada,
                      -- (v2 — especialista) se elimina "En_ejecucion" como estado persistente (ver §2.2)
                      vista_at timestamptz,                          -- (v2 — especialista) primer visto del encargado → deriva "En ejecución" en UI/bot
                      plazo_fecha, evidencia_path, updated_at)

campania_eventos     (id, tarea_id, tipo, comentario, actor_id, actor_nombre, metadata jsonb)
                      -- análoga a desvio_eventos; NO meter tareas en desvio_eventos
campania_notificaciones (id, tarea_id, user_id, tipo, leida)        -- análoga a desvio_notificaciones

solicitudes_insumo   (id, tarea_id → campania_tareas,
                      tipo_insumo: carteleria|material_pop|stock|otro, detalle, cantidad,
                      proveedor: laboratorio_apm|cadena,             -- (v2 — especialista) OBLIGATORIO, define la bifurcación del flujo (ver §2.2)
                      estado: Solicitado|Escalado_a_labo|Aprobado|Rechazado|Enviado|Recibido,
                      -- (v2 — especialista) Escalado_a_labo reemplaza aprobar→enviar cuando proveedor = laboratorio_apm
                      contacto_trade text,                           -- (v2 — especialista) contacto comercial/trade de la cadena para reclamar al labo/APM
                      aprobado_por → profiles, created_at, updated_at)

campania_resultados  (id, campania_id → campanias, id_sucursal → sucursales,   -- (v2 — especialista)
                      venta_periodo_campania numeric, venta_periodo_base numeric,
                      unidad: unidades|pesos, cargado_por → profiles, created_at)
                      -- carga manual mínima de sell-out (venta período campaña vs. período base); integración POS es fase futura

-- ALTER a tabla existente (sucursales ya existe):
ALTER TABLE sucursales ADD COLUMN categoria char(1);                 -- (v2 — especialista) A|B|C
ALTER TABLE sucursales ADD COLUMN tiene_perfumeria boolean DEFAULT false;  -- (v2 — especialista)
-- usados por el paso "Alcance" del wizard (§2.5) para no depender de la memoria del admin
```

⚠️ **Colisión de vocabulario**: el bloque de auditoría existente `BURBUJAS` (`audit_session.py:64`) significa "Displays & Señalización". Las acciones de campaña se llaman `burbuja_precio` / `descuento_caja` en el modelo de datos — nunca `BURBUJAS` — para no romper reportes que filtran por bloque.

### 2.2 Máquinas de estado

**Campaña**: `Borrador → Activa (genera campania_tareas + dispara WhatsApp) → En_seguimiento → Finalizada` (100% tareas verificadas o cierre manual admin). `Cancelada` desde cualquier estado (admin).

**Tarea por sucursal (v2 — especialista, simplificada)**:
```
Pendiente --[encargado abre la tarea por WhatsApp/web]--> vista_at = now()
           (en UI/bot se muestra como "En ejecución"; es un estado DERIVADO, no persistido:
            vista_at IS NOT NULL AND estado = 'Pendiente')
Pendiente --botón real "✅ Completada"--> Completada → Verificada (terminal)
Pendiente --botón real "📦 Falta insumo"--> Bloqueada_por_insumo --(insumo Recibido)--> Pendiente
Completada --auditor reabre (mismo patrón rechazo de desvíos)--> Pendiente
```
Nota: en la v1 el encargado "declaraba" `En_ejecucion`; en la operación real nadie avisa que va a empezar una tarea. Se elimina ese paso: los únicos botones reales del bot son **Completada** y **Falta insumo** (ver §2.3).

**Solicitud de insumo (v2 — especialista, bifurcada por `proveedor`)**:
```
Solicitado
  --proveedor = cadena--> Aprobado → Enviado → Recibido (trigger: tarea vuelve a Pendiente)
                       └-> Rechazado con motivo (tarea sigue bloqueada, se puede re-solicitar)
  --proveedor = laboratorio_apm--> Escalado_a_labo
        (notifica al contacto_trade de la cadena para reclamar al laboratorio/APM;
         NO existe un botón interno "aprobar y enviar": la cadena no controla ese material)
        --> Recibido (marcado manual cuando el material POP llega) → tarea vuelve a Pendiente
```
Sin esta bifurcación se generan expectativas falsas desde el día 1: cartelería, exhibidores y testers los trae el APM/repositor del laboratorio, no el admin de la cadena.

**Regla de unificación**: la revisión Completada→Verificada/reabrir usa EL MISMO componente frontend (`AprobarRechazarPanel` genérico) y el mismo helper de backend que el ciclo de revisión de desvíos del Módulo 1. No duplicar el patrón de aprobación.

**Aprobador de insumos**: por defecto rol `admin`, y solo aplica a `proveedor = cadena` (⚠️ decisión de negocio pendiente). Para `proveedor = laboratorio_apm` no hay "aprobación" interna: es un escalamiento/reclamo, y falta definir quién es el `contacto_trade` por defecto **(v2 — especialista, ver §4)**.

### 2.3 Flujo WhatsApp (bot)

Estados nuevos en `ConversationState` (`models.py`), **cableados explícitamente** en el dispatcher de `handle_encargado_message` (`router.py:407`) — si no se agregan al if/elif, caen al fallback de desvíos y rompen el flujo silenciosamente:

- `CAMPANIA_LISTANDO_TAREAS` — **(v2 — especialista) digest agregado**: el bot NO manda un mensaje por tarea ni por campaña; usa `send_list_message` con TODAS las tareas pendientes de TODAS las campañas activas de esa sucursal, agrupadas por campaña dentro de la misma lista.
- `CAMPANIA_TAREA_ACTIVA` — `send_quick_reply` con **2 botones reales (v2)**: `✅ Completada` / `📦 Falta insumo` (se elimina "⏳ Aún no" de la v1: no aporta información y suma ruido — ver simplificación de estado en §2.2).
- `CAMPANIA_ESPERANDO_EVIDENCIA` — pide foto; descarga con `download_media_with_metadata` (¡explícito en el handler, los media_id de Meta expiran!) + `PhotoValidator.validate_media_bytes` + upload a bucket. Solo aplica a acciones con `verificable_por_foto = true` **(v2)** — `descuento_caja` no pide foto.
- `CAMPANIA_SOLICITANDO_INSUMO` — texto libre "¿Qué insumo falta y cuánto?" + selección `proveedor` **(v2 — especialista)** (si no es evidente por el tipo de acción/marca); crea fila en `solicitudes_insumo` con bifurcación según §2.2 + notifica admin/auditor (o `contacto_trade` si es `laboratorio_apm`).

**(v2 — especialista) Franjas horarias y digest**: el encargado atiende mostrador; no se le pueden mandar mensajes sueltos por cada tarea/campaña. El digest de tareas pendientes y los recordatorios se envían **solo** en franjas fuera de pico: **13:30–16:00 o después de 20:00**. Máximo **1 recordatorio por día por sucursal** (agregado de todas las campañas, no por tarea). Ver job `remind_campania_tareas_pendientes` en §2.6.

Identidad del encargado: reusar `get_encargado_by_phone` (`supabase_manager.py:764`). Mensajería: reusar `send_list_message`, `send_quick_reply`, `send_text`, `send_file` de `meta_client.py`. Principio UX-WhatsApp: mensajes cortos + botones, nunca formularios largos.

### 2.4 Templates de Meta a registrar (BLOQUEANTE — 24-48h de aprobación)

| Nombre | Categoría | Variables | Uso |
|---|---|---|---|
| `campana_nueva_sucursal` | UTILITY | sucursal, marca, cant. tareas + botón "Ver tareas" | Disparo inicial (business-initiated, sin ventana 24h abierta) |
| `desvio_correccion_revisada` | UTILITY | desvío, resultado | Revisión fuera de ventana 24h (Módulo 1) |
| `campana_recordatorio_tareas` | UTILITY | sucursal, tareas pendientes (digest agregado, v2) | Cron de recordatorio, respeta franja horaria y máx. 1/día por sucursal (v2 — especialista) |
| `insumo_solicitud_confirmada` | UTILITY | insumo, ETA / o "escalado a laboratorio" (v2) | Confirmación de despacho o de escalamiento a labo/APM |
| `sla_auditor_revision_vencido` | UTILITY (interno, no a encargado) | desvío, antigüedad | **(v2 — especialista)** Alerta a auditor/coordinador cuando `En_revision` supera 72h — puede resolverse como notificación in-app en vez de WhatsApp si el destinatario es interno |

Redactar copy en tono operativo ("Tenés N tareas asignadas…"), NO promocional, para que Meta no lo reclasifique como MARKETING (costo mayor, opt-in requerido, riesgo de rechazo). Soporte `type: template` agregado en `meta_client.py` — `MetaClient.send_template(phone, template_name, language_code, body_params, button_params)` **(Fase 2, hecho)**.

**Envío masivo**: fan-out con throttling vía el scheduler existente (APScheduler), no loop síncrono — límites de tier de Meta (250/1K/10K contactos únicos/24h) y sin retry/backoff en `meta_client.py` hoy.

#### 2.4 bis — Copy exacto para dar de alta en Meta Business Manager (Fase 2)

Categoría **Utility** en los 5 casos (no Marketing). Idioma sugerido: `es_AR` (fallback `es` si Meta no distingue variante para tu WABA). Las variables `{{n}}` van en el orden en que se pasan a `body_params`.

**1. `campana_nueva_sucursal`**
```
Hola {{1}}, tenés {{2}} tareas nuevas asignadas para la campaña {{3}}. Respondé este mensaje para verlas.
```
`{{1}}` responsable/sucursal · `{{2}}` cantidad de tareas · `{{3}}` nombre de campaña/marca.
Botón sugerido (quick reply): "Ver tareas".

**2. `desvio_correccion_revisada`**
```
Hola, tu corrección del desvío "{{1}}" fue {{2}}. Respondé este mensaje para más detalles.
```
`{{1}}` descripción del desvío · `{{2}}` resultado, ej. "aprobada" o "rechazada — revisá el motivo en FarmaAudit".

**3. `campana_recordatorio_tareas`**
```
Hola {{1}}, tenés {{2}} tareas de campaña pendientes de completar. Respondé este mensaje para verlas.
```
`{{1}}` responsable · `{{2}}` cantidad de tareas pendientes (digest agregado, no por campaña individual — ver §2.3).

**4. `insumo_solicitud_confirmada`**
```
Hola, tu pedido de {{1}} fue registrado. Estado: {{2}}.
```
`{{1}}` insumo solicitado · `{{2}}` estado/ETA, o "escalado al laboratorio" cuando `proveedor = laboratorio_apm`.

**5. `sla_auditor_revision_vencido`** (interno — a `coordinador_tel`, no al encargado)
```
FarmaAudit: el desvío {{1}} ({{2}}) lleva más de 72hs esperando revisión del auditor.
```
`{{1}}` id_gestion · `{{2}}` sucursal.
Prioridad baja: hoy se manda como texto libre (`send_text`) porque el destinatario interno suele tener ventana de 24h abierta; solo hace falta el template si `coordinador_tel` deja de escribirle al bot regularmente.

### 2.5 Frontend

**Rutas nuevas** (`App.tsx`) y permisos (`permissions.ts` + `ModulePermission` en `types/index.ts`):

```
/campanias                → CampaniasBoard    (admin, auditor)  módulo 'campanias'
/campanias/nueva          → CampaniaWizard    (admin, auditor)
/campanias/:id            → CampaniaDetail    (admin, auditor)  tablero de seguimiento
/mis-campanias            → MisCampanias      (sucursal)        módulo 'mis_campanias'
/mis-campanias/:id        → MisCampaniaDetail (sucursal)
```

Nav en `AppLayout.tsx`: ícono `Megaphone`, entre "Desvíos" y "Sucursales". Mismo patrón espejo campanias↔auditor / mis_campanias↔sucursal que gestion_desvios/mis_desvios.

**Wizard de campaña** (3 pasos, v2 — se agrega carga del acuerdo comercial y se ajusta alcance/preview):
1. **Marca** — `BrandPicker` con búsqueda sobre tabla `marcas` (catálogo administrable; semilla: lista de `AuditBlocksPanelAdvanced.tsx:35-40`). CRUD de marcas como pestaña nueva en `Admin.tsx`. **(v2 — especialista)** Este paso también carga `vigencia_acuerdo` y `contraprestacion`: la campaña nace de un acuerdo comercial laboratorio↔cadena ya cerrado, el wizard es carga de lo pactado, no una decisión que tome quien lo completa.
2. **Acciones** — `ActionBubbleSelector`: burbujas multi-select (estilo `FilterChip` de `DesviosGestion.tsx:120-158`): Burbuja de precio / Descuento en caja **(v2 — separadas, ver §2.1)** / Exhibir productos / Exhibir publicidad (material POP) / + acción custom.
3. **Alcance y envío** — sucursales, con filtro rápido por `categoria` (A/B/C) y `tiene_perfumeria` además de selección manual **(v2 — especialista, evita depender de la memoria del admin)**; plazo; vista previa del mensaje WhatsApp **(v2: opcional/editable, con copy estandarizado por tipo de acción — deja de ser un paso obligatorio del wizard)**; botón "Enviar a N sucursales".

**Tablero de seguimiento** (`CampaniaDetail`): tabla agrupada por sucursal (mismo patrón `GroupHeader`), una celda-badge por acción (`✓` / `… pendiente` / `⚠ Falta insumo`), con celdas separadas para `burbuja_precio` (verificable, con foto) y `descuento_caja` (informativa, sin foto, se marca manualmente por quien gestiona el sistema de caja) **(v2 — especialista)**; el badge de insumo abre panel lateral con el pedido + bifurcación visible (interno vs. escalado a labo) + botón "Marcar insumo enviado/recibido". **(v2 — especialista) KPI central**: el `%` de tareas completadas es una métrica de compliance, no de negocio — deja de ser el KPI destacado y pasa a dato secundario de la tabla; el bloque principal (`VentaRealForm`, `campania_resultados`) muestra venta período campaña vs. venta período base por sucursal/campaña (carga manual; integración POS queda como fase futura).

**Vista del responsable** (`MisCampanias`): espejo de `MisDesvios.tsx` — cards con checklist de acciones, botones "Marcar hecho" (con `EvidenciaUploader`, solo para acciones `verificable_por_foto=true`) y "Falta insumo" (modal: textarea + foto opcional + selección de proveedor si aplica). Mobile-first (el encargado entra desde el celular).

**Componentes nuevos**: `campanias/BrandPicker.tsx`, `campanias/ActionBubbleSelector.tsx`, `campanias/CampaniaTaskCard.tsx`, `campanias/InsumoRequestPanel.tsx`, `campanias/VentaRealForm.tsx` **(v2)**, `campanias/SucursalSegmentFilter.tsx` **(v2)**, hooks `useCampanias.ts` / `useCampaniaDetail.ts`, y el genérico `AprobarRechazarPanel.tsx` compartido con desvíos.

**Componentes a reutilizar**: `AppLayout`, `FeedbackState`, `Button/Checkbox/Textarea/Select`, `ImageLightbox`, `EvidenciaUploader`, `EvidenciaGaleria`, `KPICard`, patrón `FilterChip`/`GroupHeader`.

**Endpoints FastAPI nuevos** (WhatsApp nunca se dispara desde el navegador — patrón `notificarEncargado`):
- `POST /api/campanias` (crear), `POST /api/campanias/{id}/activar` (genera tareas + fan-out WhatsApp, respetando franja horaria y sesión de auditoría activa)
- `POST /api/campanias/tareas/{id}/revision` (verificar/reabrir — helper compartido con desvíos)
- `POST /api/solicitudes-insumo/{id}/estado` (maneja la bifurcación `cadena`/`laboratorio_apm`)
- `POST /api/campanias/{id}/resultados` **(v2 — especialista)** — carga de `campania_resultados` (venta real por sucursal)
- Lecturas simples: `supabase-js` directo con RLS, como el resto de la app.

### 2.6 Jobs del scheduler (APScheduler, `main.py`)

- `remind_campania_tareas_pendientes` — recordatorio (template `campana_recordatorio_tareas`), **digest agregado por sucursal, respeta franja horaria (13:30-16h / después de 20h) y máx. 1/día (v2 — especialista, reemplaza el "máx 1/día por tarea" de la v1)**.
- `remind_gestiones_por_vencer` — recordatorio previo al vencimiento de desvíos (24h y 2h antes), hoy inexistente (el job actual es binario a tiempo/vencido). No aplica a desvíos en `En_gestion_terceros` **(v2)**.
- `remind_sla_auditor_revision` **(v2 — especialista)** — corre junto a los jobs de vencimiento; alerta a auditor/coordinador cuando `gestion.en_revision_desde` supera 72h sin resolución.
- Escalamiento por niveles: día 0 → responsable; +1 día → auditora; +2 días → `coordinador_tel`. No aplica mientras el desvío está en `En_gestion_terceros` **(v2)**.
- Chequeo previo al fan-out: si la sucursal tiene sesión de auditoría activa (`sesiones_auditoria`), **diferir** el envío del WhatsApp de campaña (no bloquear la creación de la tarea).

---

## 3. Riesgos técnicos transversales

1. **Colisión de estado conversacional (el más serio)**: `conversaciones` guarda UN solo `estado_actual` por teléfono. Un encargado con desvío + campaña activos se pisa a sí mismo. Mitigación fase 1: cola de flujos pendientes en el contexto JSON de `ultimo_mensaje` (al terminar un flujo, ofrecer el siguiente). Solución correcta (fase posterior): estado por `(telefono, tipo_flujo)` — cambio de schema no trivial.
2. **Ventana de 24h no modelada**: registrar `ultimo_mensaje_entrante_at` por conversación y decidir texto libre vs. template antes de cada envío business-initiated. (Bug latente ya existente en `send_alerta_coordinador`.)
3. **Sesiones en memoria**: `audit_session.py` usa dict en memoria — las campañas duran días, NO apoyarse en ese mecanismo; todo el estado de campaña vive en Supabase.
4. **Casos borde**: sucursal sin `tel_responsable` → fallback a notificación in-app + alerta coordinador (nunca fallar silencioso); corrección sin foto → exigir foto según tipo de acción (`requiere_foto`/`verificable_por_foto` parametrizado); multi-campaña activa en paralelo por sucursal (el rubro lo exige — nada de singleton).
5. **(v2 — especialista) Expectativas falsas de insumo**: sin distinguir `proveedor` (labo vs. cadena), el admin de la cadena promete un envío que no controla — el material POP lo trae el APM/repositor del laboratorio. Mitigado por `solicitudes_insumo.proveedor` + estado `Escalado_a_labo` (§2.1/§2.2).
6. **(v2 — especialista) Falsos "completada" en `descuento_caja`**: una foto de cartelería no prueba que el descuento esté activo en el sistema de caja — depende de otra área/sistema. Mitigado modelando `descuento_caja` como acción `verificable_por_foto = false`, de carácter informativo/administrativo, separada de `burbuja_precio` (§2.1).
7. **(v2 — especialista) Desvíos en limbo**: sin SLA del lado auditor, `En_revision` puede quedar sin resolución indefinidamente y el encargado pierde confianza en el sistema. Mitigado por `en_revision_desde` + job `remind_sla_auditor_revision` + antigüedad visible en el filtro (§1).

## 4. Decisiones de negocio pendientes (confirmar con la auditora/cliente)

1. **¿Quién aprueba las solicitudes de insumo con `proveedor = cadena`?** (default propuesto: admin; no existe rol logística). Para `proveedor = laboratorio_apm` ya no es "aprobación" sino escalamiento — falta definir **quién es el `contacto_trade` por defecto** (¿por marca, por laboratorio, un único contacto de la cadena?) **(v2 — especialista)**.
2. **¿El responsable opera campañas 100% por WhatsApp, o también tendrá la vista web `/mis-campanias`?** (propuesto: ambas, WhatsApp como canal primario).
3. **Lista inicial de marcas** para cargar el catálogo (y quién la mantiene).
4. **Plazo por defecto de reapertura tras rechazo** (propuesto: +48h) y **plazo default de tareas de campaña**.
5. **(v2 — especialista) SLA de revisión del auditor**: ¿72h es un valor fijo o debería ser configurable por severidad del desvío?
6. **(v2 — especialista) Venta real**: ¿unidad por defecto (unidades o pesos)? ¿quién carga `campania_resultados` (encargado, supervisor, admin) y con qué frecuencia (fin de campaña, semanal)?
7. **(v2 — especialista) Segmentación de sucursales**: ¿quién carga inicialmente `categoria`/`tiene_perfumeria` (carga manual puntual, import desde planilla existente)?
8. **(v2 — especialista) Criterio de `En_gestion_terceros`**: ¿queda 100% a criterio manual de la auditora, o se sugiere automáticamente pasado cierto número de días sin resolución?

## 5. Fases de implementación propuestas

**Fase 1 — Ciclo de revisión de desvíos** ✅ hecho (commit `2eb1d68`):
estado `En_revision` + campos nuevos en `gestion` (incluye `en_revision_desde` y estado `En_gestion_terceros`, **v2**) → endpoint `/api/gestion/{id}/revision` → badge de fila + tab "Revisión" + `AprobarRechazarPanel` → fix del placeholder de evidencias → feedback WhatsApp en ventana 24h → job `remind_sla_auditor_revision` **(v2)** → antigüedad visible en filtro "Pendiente de revisión" **(v2)**. Migración: `frontend/docs/sql/etapa-14-desvio-revision.sql`.

**Fase 2 — Infraestructura de campañas** ✅ hecho, migración corrida en Supabase:
tablas + RLS (incluye `solicitudes_insumo.proveedor`/`contacto_trade`, `campania_resultados`, `campanias.acuerdo_desde/acuerdo_hasta/contraprestacion`, ALTER `sucursales` `categoria`/`tiene_perfumeria`, todo **v2**) → CRUD de marcas en Admin → soporte `type: template` en `meta_client.py`. Migración: `frontend/docs/sql/etapa-15-campanias.sql`. Templates redactados en §2.4 bis — **sigue pendiente darlos de alta en Meta Business Manager (paso manual del usuario, 24-48h + posible rechazo)**.

**Fase 3 — Módulo Campañas web** ✅ hecho, falta correr `etapa-16` en Supabase:
wizard (carga de acuerdo comercial, filtro de alcance por segmentación, preview de WhatsApp opcional) → tablero de seguimiento (`CampaniaDetail`: celdas separadas por acción, verificar/reabrir, panel de insumos con bifurcación labo/cadena, venta real) → vista responsable (`MisCampanias`/`MisCampaniaDetail`, marcar hecho / falta insumo). Migración adicional: `frontend/docs/sql/etapa-16-campania-sucursal-rls.sql` (RLS scoped a sucursal para `campania_tareas`, y RLS abierta a cualquier autenticado para `campania_eventos`/`solicitudes_insumo`, mismo patrón que `desvio_eventos`) — **falta correrla en Supabase**.
Simplificaciones deliberadas de esta fase (documentadas para no perderlas de vista): `POST /api/campanias/{id}/resultados` del punteo original se resolvió como insert directo vía supabase-js (no hay lógica de negocio que justifique un endpoint); la resolución de tareas por el responsable (marcar hecho / falta insumo) se hace directo desde la web vía RLS, no por WhatsApp — el bot todavía no existe (Fase 4); no hay carga de foto obligatoria en el "marcar hecho" web (el campo `evidencia_path` queda listo en el schema, se completa cuando el bot de Fase 4 suba evidencia real).

**Fase 4 — Bot de campañas** ✅ hecho, con un cambio de enfoque deliberado:
estados `CAMPANIA_*` en el dispatcher de `router.py` (`handle_encargado_message`) → digest agregado (una sola lista con todas las tareas pendientes de todas las campañas activas de la sucursal, vía `send_list_message`) → botones reales limitados a Completada/Falta insumo sin declarar "En_ejecucion" → foto obligatoria solo para acciones `verificable_por_foto` → solicitud de insumo con bifurcación `laboratorio_apm`/`cadena` (auto-escala sin paso de aprobación cuando es del laboratorio).

**Cambio de enfoque vs. la v2 original**: el disparo proactivo del bot ("tenés tareas nuevas") requiere un template de Meta aprobado, que todavía no existe. En vez de bloquear toda la fase a que Meta apruebe, el bot quedó **pull-based**: nunca inicia la conversación de campaña — el encargado le escribe primero (como ya hace para desvíos) y ahí el bot le ofrece lo que tenga pendiente. Si tiene desvíos y campañas a la vez, se agrega un selector nuevo (`ENCARGADO_ELIGIENDO_MODULO`, botones "Desvíos"/"Campañas") antes de mostrar cualquiera de las dos listas. Las franjas horarias, el job de recordatorio automático (`campana_recordatorio_tareas`) y el escalamiento quedan diferidos: no tienen sentido sin un push proactivo, así que se retoman cuando el template esté aprobado (ver §2.4 bis). La mitigación de colisión de estados conversacionales (riesgo #1 de §3) sigue pendiente — con pull-based baja la probabilidad de choque (todo pasa dentro de un mismo mensaje-respuesta) pero no la elimina.
Validado con un smoke test manual mockeando `SupabaseManager`/`MetaClient` (pytest no corre en este entorno de desarrollo por un problema de terminal ajeno al código, `test_respuesta_recolectora.py` falla igual sin tocar nada de esta fase) — cubre digest con tareas mixtas, foto obligatoria vs. no, insumo con escalamiento a laboratorio, tarea bloqueada reapareciendo en el digest, y el selector cuando hay desvíos y campañas a la vez.

**Fase 5 — Futuro, fuera de este scope (v2 — especialista, validado como fase posterior, no descartado)**:
integración POS (reemplaza la carga manual de `campania_resultados`); rol logística dedicado (hoy los insumos `proveedor=cadena` los aprueba `admin`); planograma de referencia adjunto a la tarea (imagen de cómo debe quedar la exhibición, para comparar contra la foto de evidencia); cola de estados por `(telefono, tipo_flujo)` en `conversaciones` (solución de fondo al riesgo #1 de §3).

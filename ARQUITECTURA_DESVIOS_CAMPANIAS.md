# Arquitectura — Módulo Desvíos por Farmacia + Módulo Campañas

> **v2 — versión superadora.** Documento consolidado a partir de los veredictos de 6 agentes:
> **UX/UI**, **Meta/WhatsApp**, **Procesos**, **Usos y Costumbres**, **Especialista en Farmacias/Perfumería** y el **Sintetizador** (2026-07-27).
> Es la especificación para la implementación (fase de desarrollo con Sonnet).
> Fuente de verdad de convenciones: el código (`router.py`, `models.py`, `supabase_manager.py`, `frontend/src/lib`), NO los `.md` viejos de la raíz.
> Los agregados de esta versión están marcados **(v2 — especialista)** para que sean rastreables contra la v1.
>
> **v3 — 2026-08-24.** El Módulo 2 (Campañas) está **construido e íntegramente en `master`** (Fases 2-4, ver §7) —
> el pedido del dueño de agregar foto de referencia y un "Tour de Farmacias" es trabajo NUEVO sobre esa base ya
> viva, no un rediseño. Agregados marcados **(v3)**: §2.1/§2.3/§2.5 (foto de referencia en acciones comerciales)
> y el nuevo **MÓDULO 3** (Tour de Farmacias, reutiliza el motor de campañas en vez de duplicarlo).
>
> **v4 — 2026-08-24 (mismo día, aclaración del dueño).** La auditoría de sucursal (Módulo 0, no documentado
> acá porque es el producto base) **ya opera 100% por WhatsApp** para el auditor — `EN_AUDITORIA`/`EN_BLOQUE`/
> `STOCK_LOOP` en `router.py`, es el flujo guiado punto por punto que ya existe. Lo que el dueño aclaró que
> falta es que **crear y lanzar** una Campaña o un Tour también se pueda hacer por WhatsApp (hoy solo existe
> el wizard web, `CampaniaWizard.tsx`) — no solo que el encargado responda tareas por WhatsApp, que eso ya
> pasa. Agregado marcado **(v4)**: nuevo **MÓDULO 4** (creación de Campañas/Tour desde el chat del auditor).
>
> **v5 — 2026-08-24 (mismo día, auditoría por 4 agentes expertos).** Módulo 3 y 4 (v3/v4) fueron auditados por
> 4 especialistas independientes — Meta/WhatsApp, arquitectura backend/datos, UX conversacional, y operaciones
> de farmacia/perfumería — cruzando cada afirmación contra el código real, mismo criterio que la revisión de 6
> agentes que validó la v2 original. Los 4 dieron veredicto "Aprobado con condiciones/cambios": la base de
> diseño (reusar el motor de §2, prefijos de estado sin colisión, extracción de un helper compartido) es
> sólida, pero encontraron errores concretos y verificables — dos violaciones de límites duros de la API de
> Meta (`quick_reply` truncando botones y títulos en silencio), una colisión real de nombres de migración con
> trabajo no relacionado ya en el repo, una afirmación falsa sobre triggers que en realidad no existían
> todavía, un hueco de integridad en `campania_resultados`, falta de trazabilidad de quién crea una campaña
> por WhatsApp, y un gap de negocio real en el checklist del Tour (falta vidriera y cadena de frío). Todos los
> hallazgos que no requerían una decisión de negocio del dueño ya se corrigieron en este documento, marcados
> **(v5)**. Dos hallazgos SÍ contradicen decisiones explícitas que el dueño ya había tomado en esta misma
> sesión (menú de 3 opciones en el saludo; foto de referencia solo para campañas comerciales) — esos quedan
> señalados como tensión a resolver, no cambiados unilateralmente (ver notas **(v5 — a decidir)**).
>
> **v6 — 2026-08-24 (mismo día, "avancemos de la mejor manera posible").** El dueño autorizó resolver las dos
> tensiones de v5 con criterio propio. Resueltas en §6.13/§6.14: foto de referencia SÍ se habilita también en
> el Tour (costo ~cero, el campo ya es genérico, el hallazgo del especialista de farmacias era sólido); el
> menú de 3 opciones se mantiene SIEMPRE al saludar tal como el dueño lo pidió explícitamente (una fricción
> hipotética de UX no alcanza para revertir una instrucción deliberada y reciente). Con la spec ya sin puntos
> abiertos, arranca la implementación por la Fase 6 (foto de referencia) — es la pieza más chica, más
> independiente, y beneficia a Módulo 2 y 3 por igual al ser el mismo campo genérico.
>
> **v7 — 2026-08-24 (mismo día, implementación de Fase 6).** La corrección de numeración de migración de v5
> (`etapa-17/18` → `etapa-20/21`) también estaba mal: el arquitecto backend chequeó contra un listado
> desactualizado. El repo real ya llega hasta `etapa-30-sucursales-geo.sql` — la migración de Fase 6 terminó
> siendo `etapa-31-campania-referencia.sql`, verificado contra el listado real de `frontend/docs/sql/` al
> momento de escribirla, no contra lo que decía cualquier versión anterior de este documento. Fase 6 queda
> **implementada** (código + migración escrita, falta correrla en Supabase). Lección para las fases que
> vengan: no asumir un número de `etapa-N` por lo que diga el doc — listar el directorio real primero.
>
> **Mismo día, más tarde: Fase 7 (Tour de Farmacias) también implementada**, aplicando esa lección — migración
> verificada contra el listado real (`etapa-32-tour-farmacias.sql`). Refactor de paso: se extrajo
> `_enviar_prompt_evidencia()` en `router.py` como helper compartido entre el flujo comercial ("Completada") y
> el delta del tour, en vez de duplicar la lógica de mandar la foto de referencia + pedir evidencia. `creado_por_telefono`
> (parte de la spec de Fase 8) se sacó de la migración de Fase 7 y quedó pendiente para cuando se implemente
> Fase 8 — no tiene sentido agregar una columna sin nada que la use todavía.
>
> **v8 — 2026-08-24 (mismo día, más tarde todavía): Fase 8 (crear/lanzar Campañas y Tour desde WhatsApp)
> también implementada** — 9 estados `AUDITOR_CAMPANIA_*` nuevos, menú de 3 opciones al saludar, matching
> difuso para elegir sucursales por nombre, `campanias_service.py` nuevo con la función pura
> `activar_campania_core` (compartible entre el bot y el wizard web). Migración `etapa-33-campania-creado-por-
> telefono.sql`, verificada contra el listado real (llegaba a `etapa-32`). **Deliberadamente NO se tocó
> `main.py`**: otra sesión lo estaba editando en simultáneo (verificado con `git diff`, no una suposición) —
> el endpoint del wizard web sigue con su lógica inline por ahora, el bot ya usa el servicio compartido sin
> duplicar nada nuevo. El job de timeout de flujo abandonado y el wireo de `main.py` al servicio compartido
> quedan pendientes por el mismo motivo (ver detalle en Fase 8, §7). Con esto, **todo lo pedido en esta sesión
> quedó implementado**: auditoría por WhatsApp (ya existía), campañas y tours creables desde el panel web y
> desde WhatsApp, con foto de referencia opcional en ambos.
>
> **v9 — 2026-08-24 (mismo día, la otra sesión ya comiteó).** Con `main.py` limpio otra vez (`c0b02c4`), se
> completaron los dos pendientes que quedaban abiertos por la colisión: el endpoint `POST
> /api/campanias/{id}/activar` ahora usa `campanias_service.activar_campania_core` en vez de su lógica inline
> (mismo cambio que ya estaba preparado, aplicado recién cuando fue seguro) — el wizard web y el bot de
> WhatsApp comparten la misma lógica de fan-out, cero duplicación. Se agregó el job de timeout
> `check_auditor_campania_timeout` (24h, reusa `conversaciones.timestamp`, sin tabla nueva). Ambos validados
> con smoke tests nuevos, incluyendo uno que ejercita `activar_campania_core` contra un fake client con la
> forma real de supabase-py (no solo un stub). **Fases 6-8 quedan 100% completas, sin deuda pendiente.**

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
                      verificable_por_foto bool default true,        -- (v2 — especialista) false para descuento_caja: acción informativa/administrativa
                      imagen_referencia_path text)                   -- (v3) foto "así debe quedar" opcional, subida por el auditor en el wizard; bucket desvio-evidencias, prefijo campania-referencias/

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

**Aprobador de insumos**: por defecto rol `admin`, y solo aplica a `proveedor = cadena` (⚠️ decisión de negocio pendiente). Para `proveedor = laboratorio_apm` no hay "aprobación" interna: es un escalamiento/reclamo, y falta definir quién es el `contacto_trade` por defecto **(v2 — especialista, ver §6)**.

### 2.3 Flujo WhatsApp (bot)

Estados nuevos en `ConversationState` (`models.py`), **cableados explícitamente** en el dispatcher de `handle_encargado_message` (`router.py:407`) — si no se agregan al if/elif, caen al fallback de desvíos y rompen el flujo silenciosamente:

- `CAMPANIA_LISTANDO_TAREAS` — **(v2 — especialista) digest agregado**: el bot NO manda un mensaje por tarea ni por campaña; usa `send_list_message` con TODAS las tareas pendientes de TODAS las campañas activas de esa sucursal, agrupadas por campaña dentro de la misma lista.
- `CAMPANIA_TAREA_ACTIVA` — `send_quick_reply` con **2 botones reales (v2)**: `✅ Completada` / `📦 Falta insumo` (se elimina "⏳ Aún no" de la v1: no aporta información y suma ruido — ver simplificación de estado en §2.2).
- `CAMPANIA_ESPERANDO_EVIDENCIA` — pide foto; descarga con `download_media_with_metadata` (¡explícito en el handler, los media_id de Meta expiran!) + `PhotoValidator.validate_media_bytes` + upload a bucket. Solo aplica a acciones con `verificable_por_foto = true` **(v2)** — `descuento_caja` no pide foto. **(v3)** Si `accion.imagen_referencia_path` está seteado, ANTES de pedir la foto el bot manda la referencia con `send_image_by_url` (URL firmada) y caption `"Así debería quedar:"` — un solo mensaje extra, no un estado nuevo. El comentario del encargado ya viaja gratis: `_handle_campania_esperando_evidencia` ya usa el caption de la foto entrante como `comentario` del evento (`router.py:884`) si el encargado escribe algo junto con la imagen — no hace falta un paso de texto aparte.
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
2. **Acciones** — `ActionBubbleSelector`: burbujas multi-select (estilo `FilterChip` de `DesviosGestion.tsx:120-158`): Burbuja de precio / Descuento en caja **(v2 — separadas, ver §2.1)** / Exhibir productos / Exhibir publicidad (material POP) / + acción custom. **(v3)** Por cada acción con `verificable_por_foto = true`, input opcional "Foto de referencia" (reusa `EvidenciaUploader`) que sube a `imagen_referencia_path` — no bloquea el wizard si se omite.
3. **Alcance y envío** — sucursales, con filtro rápido por `categoria` (A/B/C) y `tiene_perfumeria` además de selección manual **(v2 — especialista, evita depender de la memoria del admin)**; plazo; vista previa del mensaje WhatsApp **(v2: opcional/editable, con copy estandarizado por tipo de acción — deja de ser un paso obligatorio del wizard)**; botón "Enviar a N sucursales".

**Tablero de seguimiento** (`CampaniaDetail`): tabla agrupada por sucursal (mismo patrón `GroupHeader`), una celda-badge por acción (`✓` / `… pendiente` / `⚠ Falta insumo`), con celdas separadas para `burbuja_precio` (verificable, con foto) y `descuento_caja` (informativa, sin foto, se marca manualmente por quien gestiona el sistema de caja) **(v2 — especialista)**; el badge de insumo abre panel lateral con el pedido + bifurcación visible (interno vs. escalado a labo) + botón "Marcar insumo enviado/recibido". **(v2 — especialista) KPI central**: el `%` de tareas completadas es una métrica de compliance, no de negocio — deja de ser el KPI destacado y pasa a dato secundario de la tabla; el bloque principal (`VentaRealForm`, `campania_resultados`) muestra venta período campaña vs. venta período base por sucursal/campaña (carga manual; integración POS queda como fase futura).

**Vista del responsable** (`MisCampanias`): espejo de `MisDesvios.tsx` — cards con checklist de acciones, botones "Marcar hecho" (con `EvidenciaUploader`, solo para acciones `verificable_por_foto=true`) y "Falta insumo" (modal: textarea + foto opcional + selección de proveedor si aplica). Mobile-first (el encargado entra desde el celular). **(v3)** Si la acción tiene `imagen_referencia_path`, la card la muestra arriba del uploader ("Así debería quedar") — misma referencia que ve el encargado por WhatsApp.

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

## MÓDULO 3 — Tour de Farmacias (v3, extiende Módulo 2, NO reconstruye)

Pedido del dueño: el auditor lanza un "tour" donde los encargados sacan fotos de puntos críticos de la
sucursal — iluminación (techo), góndolas, piso, limpieza — y si algo está mal lo marcan con foto + comentario.
Es una auditoría **interna** de infraestructura/orden, no una campaña comercial de marca: no tiene laboratorio
ni acuerdo comercial detrás. Aun así, mecánicamente es *casi idéntico* a una campaña — N puntos a controlar ×
sucursal, digest por WhatsApp, foto obligatoria, tablero de seguimiento — así que en vez de duplicar tablas,
RLS, bot y frontend, el Tour se modela como un **tercer tipo de campaña sin marca**, reusando todo el motor de
§2 con los mínimos deltas necesarios.

### 3.1 Modelo de datos (deltas sobre §2.1)

```sql
ALTER TABLE campanias ADD COLUMN tipo text NOT NULL DEFAULT 'comercial'
  CHECK (tipo IN ('comercial', 'tour_interno'));
ALTER TABLE campanias ALTER COLUMN marca_id DROP NOT NULL;
ALTER TABLE campanias ADD CONSTRAINT campanias_marca_segun_tipo CHECK (
  (tipo = 'comercial' AND marca_id IS NOT NULL) OR (tipo = 'tour_interno' AND marca_id IS NULL)
);

ALTER TABLE campania_acciones DROP CONSTRAINT IF EXISTS campania_acciones_tipo_check;
ALTER TABLE campania_acciones ADD CONSTRAINT campania_acciones_tipo_check CHECK (
  tipo IN ('exhibicion', 'material_pop', 'burbuja_precio', 'descuento_caja', 'custom',
           'iluminacion', 'gondola_orden', 'piso', 'limpieza',
           'vidriera', 'heladera_cadena_frio')  -- 6 nuevos, exclusivos de tour_interno (v5)
);
```

**(v5 — hallazgo del especialista de farmacias)** El checklist original (iluminación/góndolas/piso/limpieza)
tenía dos huecos reales: **`vidriera`** (exhibición de fachada — primer contacto del cliente, motor de venta
en perfumería, estándar en cualquier walk-through de imagen) y **`heladera_cadena_frio`** (control de cadena
de frío en heladeras con refrigerados/vacunas/insulina — a diferencia del resto del checklist, esto es un
incumplimiento **regulatorio**, no solo estético, y no había ningún punto del sistema que lo cubriera).
`heladera_cadena_frio` solo aplica a sucursales con refrigerados — condicionar su inclusión en el checklist
seedeado a un flag existente de la sucursal (ver decisión pendiente §6.12, nueva).

Se usa `DROP CONSTRAINT IF EXISTS`/`ADD COLUMN IF NOT EXISTS` en todo este delta **(v5)**: el resto de las
migraciones del repo (`etapa-15`, `etapa-19`) son idempotentes y este delta no lo era.

`campania_tareas`, `campania_eventos`, `campania_notificaciones`, `solicitudes_insumo` y sus RLS
(etapa-15/16) sirven tal cual — un tour genera filas en las mismas tablas que una campaña comercial, solo
que su `campania.marca_id` es `NULL` y sus `campania_acciones.tipo` son del set nuevo.

**(v5 — corrección) `campania_resultados` SÍ necesita un resguardo, no alcanza con que la UI no lo muestre.**
La carga es hoy un insert directo vía `supabase-js` (`createCampaniaResultado`, `frontend/src/lib/api.ts:1366`)
contra una policy `FOR ALL` abierta a cualquier admin/auditor, sin filtro de `tipo` — cualquiera puede insertar
"venta real" para un tour desde la consola o un bug de UI futuro. Falta un `CHECK`/trigger que valide
`campanias.tipo = 'comercial'` antes de aceptar una fila en `campania_resultados`; se agrega a la migración de
Fase 7 (§7).

**(v5 — regla dura de reporting, hallazgo del especialista de farmacias)** Cualquier vista, export o reporte
que agregue "% completado"/compliance por sucursal o período y pueda llegar a ojos de un laboratorio (directa
o indirectamente) **tiene que filtrar `tipo = 'comercial'` siempre, sin excepción** — nunca debe mezclarse con
datos de limpieza/orden interno de un Tour. No es solo un filtro de UI: dejarlo como regla explícita para
cualquier reporte nuevo que se agregue más adelante (dashboards, exports a Excel, etc.).

**Checklist inicial de acciones** (seedeado por el wizard/bot al crear un tour, editable — ver decisión
pendiente §6.9):
| tipo | descripcion | requiere_foto | verificable_por_foto |
|---|---|---|---|
| `vidriera` | Exhibición de vidriera/fachada | true | true |
| `iluminacion` | Techo/iluminación general | true | true |
| `gondola_orden` | Orden y limpieza de góndolas | true | true |
| `piso` | Estado del piso | true | true |
| `limpieza` | Limpieza general del local | true | true |
| `heladera_cadena_frio` | Cadena de frío de heladeras (solo si aplica, §6.12) | true | true |

**(v6 — resuelto, §6.13)** Foto de referencia también habilitada en el Tour: mismo campo genérico
`imagen_referencia_path` de §2.1/§2.3, opcional, mismo mecanismo de envío por el bot antes de pedir evidencia
(§3.3). Prioridad sugerida para cargarla, siguiendo el criterio del especialista de farmacias: `gondola_orden`
y `limpieza` (criterios subjetivos, se benefician más) por sobre `piso`/`iluminacion` (más objetivos).

### 3.2 Máquina de estados

Reusa **exactamente** la de §2.2 (`Pendiente → [vista_at] → Completada → Verificada`, reabrir = mismo patrón).
No hay estado nuevo. La única diferencia de comportamiento es de UX en el bot (§3.3), no de estado persistido.

### 3.3 Flujo WhatsApp — delta sobre §2.3

Un tour no tiene el concepto de "insumo faltante" (no hay cartelería ni stock de por medio) ni tiene sentido
preguntarle al encargado "¿Completada o Falta insumo?" antes de una foto de piso. Delta puntual en
`_handle_campania_listando_tareas` (`router.py:741`): si `tarea.campanias.tipo == 'tour_interno'`, **saltear**
`CAMPANIA_TAREA_ACTIVA` (el quick-reply Completada/Falta insumo de `router.py:773-780`) y pasar directo a
`CAMPANIA_ESPERANDO_EVIDENCIA` con el texto `"Sacá una foto de: {descripcion}. Si encontrás algo para
reportar, escribilo junto con la foto."` — reusa `_handle_campania_esperando_evidencia` sin tocarlo: el
caption de la foto ya se guarda como `comentario` del evento (mismo mecanismo que la foto de referencia en
§2.3 v3). "Todo bien" = foto sin caption; "hay un problema" = foto con caption. Cero estados nuevos, cero
botones nuevos. **(v6)** Si `accion.imagen_referencia_path` está seteado (habilitado también para tour desde
v6, §3.1), se manda ANTES del texto de arriba, mismo mecanismo que §2.3 v3 (`send_image_by_url` + caption
"Así debería quedar:").

El digest (`CAMPANIA_LISTANDO_TAREAS`, `send_list_message`) no cambia: un tour aparece como sus N puntos
agrupados bajo su nombre, igual que hoy aparece una campaña comercial con sus acciones — mismo digest agregado
si la sucursal tiene tour + campañas de marca en simultáneo. **(v5 — hallazgo Meta/WhatsApp, riesgo agravado
por el Tour)**: `_start_campania_flow` (`router.py:719`) ya trunca el digest a `tareas[:9]` en silencio, sin
paginación — un tour de 5-6 puntos sumado a campañas comerciales activas en la misma sucursal acerca mucho más
ese tope oculto (son 9 filas TOTALES, no por campaña). No es un problema nuevo introducido por el Tour, pero
el Tour lo hace más probable en la práctica; paginar o avisar cuando se trunca queda anotado como mejora
transversal (no bloquea Fase 7, pero sí conviene resolverlo antes de tener varias campañas + tour activos a la
vez en la misma sucursal).

### 3.4 Templates de Meta

**Ninguno nuevo.** El template `campana_nueva_sucursal` (§2.4) ya es genérico — `{{3}}` es "nombre de
campaña/marca", y para un tour ese parámetro simplemente lleva el nombre del tour (ej. "Tour de Farmacias —
agosto"). Mismo criterio para `campana_recordatorio_tareas`.

### 3.5 Frontend

**Reusa el wizard** (`CampaniaWizard.tsx`) con un selector de tipo como paso 0: "Campaña comercial" vs "Tour de
Farmacias". Si se elige tour:
- Paso 1 (Marca y acuerdo) se saltea entero — no hay `BrandPicker` ni `vigencia_acuerdo`/`contraprestacion`.
- Paso 2 (Acciones) arranca pre-cargado con las filas de §3.1 en vez de burbujas vacías (`heladera_cadena_frio`
  solo si la sucursal tiene el flag correspondiente, §6.12; editable: se puede sacar o agregar una fila custom,
  mismo componente `ActionBubbleSelector`).
- Paso 3 (Alcance y envío) sin cambios.

**Tablero** (`CampaniaDetail`): sin cambios estructurales — la fila "venta real" (`VentaRealForm`) se oculta
cuando `campania.tipo === 'tour_interno'` (no aplica). El resto (tabla por sucursal, badge por acción, foto de
evidencia + comentario) sirve igual.

**Nav**: mismo ícono `Megaphone`/ruta `/campanias` — un tour es una campaña más en el listado, distinguible por
un badge de tipo en la fila (no se agrega una ruta nueva para no fragmentar el tablero de seguimiento).

Fases de implementación: ver Fase 6 (foto de referencia) y Fase 7 (Tour) en §7.

---

## MÓDULO 4 — Crear y lanzar Campañas/Tour desde WhatsApp (v4, auditor)

Hoy el auditor arma una campaña o un tour solo desde el panel web (`CampaniaWizard.tsx`). El pedido es que
pueda hacerlo también por WhatsApp — igual que ya hace la auditoría de sucursal completa (`EN_AUDITORIA`).
Es el mismo motor de datos de §2/§3, un canal de creación más: no se tocan tablas, RLS ni el bot del
encargado (`CAMPANIA_*` existentes).

**Trigger — menú de entrada (v4, cambio de comportamiento del saludo)**: hoy `"hola"/"inicio"/"empezar"/
"comenzar"/"start"` saltan directo a `_iniciar_seleccion_sucursal` (`router.py:274-275`), es decir, el saludo
ya asume que el auditor quiere auditar. Se reemplaza ese salto directo por un menú explícito de 3 opciones,
estado `AUDITOR_ELIGIENDO_MODULO` (mismo nombre de patrón que `ENCARGADO_ELIGIENDO_MODULO`, que ya existe del
lado del encargado — ver §2.3/`models.py:36` **(v5 — cita corregida, era `router.py:36`)**): `send_quick_reply`
con **3 botones** — `"🔍 Auditar"` / `"📣 Campaña"` / `"🚶 Tour"` **(v5 — títulos acortados)**: `send_quick_reply`
trunca cada título a 20 caracteres en silencio (`meta_client.py:559`); `"🚶 Lanzar Tour de Farmacias"` medía
~26 y hubiera salido cortado en el chat real. El nombre completo va en el texto del cuerpo del mensaje, arriba
de los botones — los botones son solo la etiqueta corta.

- **Auditar sucursal** → sigue exactamente igual que hoy, llama a `_iniciar_seleccion_sucursal`.
- **Lanzar campaña** → arranca el flujo de creación con `tipo` ya resuelto en `'comercial'` (salta directo a
  `AUDITOR_CAMPANIA_ELIGIENDO_MARCA`, sin volver a preguntar "¿comercial o tour?" — el botón ya lo dijo).
- **Lanzar Tour de Farmacias** → arranca el flujo con `tipo = 'tour_interno'` (salta directo a
  `AUDITOR_CAMPANIA_NOMBRE`, sin paso de marca ni de acciones — usa el checklist fijo de §3.1).

**(v5 — corrección de un hecho falso)** La versión anterior de este documento decía que `"campaña"`/`"tour"`
"se mantienen como atajos... siguen funcionando en paralelo" — verificado contra `router.py:238-250`: eso es
**falso**, esos triggers no existen hoy (solo existen los de auditoría v2, `"desvios"/"desvíos"` y
`"pendientes"/"revision"`). Agregar `"campaña"`/`"campañas"`/`"tour"`/`"tour de farmacias"` como triggers de
texto libre es trabajo NUEVO de la Fase 8, en paralelo al menú — no algo que ya exista para "mantener".
`"campaña"`/`"campañas"` sin más contexto sigue siendo ambiguo (puede ser comercial o tour), así que ese atajo
puntual todavía necesita la pregunta de tipo (`AUDITOR_CAMPANIA_ELIGIENDO_TIPO`, estado 1 de la lista abajo);
`"tour"` como atajo directo ya resuelve el tipo igual que el botón del menú.

**(v5 — sin resolver, tensión con una decisión ya tomada)** El especialista en UX conversacional marcó que
insertar este menú en el saludo reordena la ruta de **mayor volumen diario** (auditar, que hoy es un solo
paso) detrás de un paso extra para beneficiar la de **menor volumen** (lanzar campaña/tour, esporádico), y
sugirió mantener el salto directo a auditoría en el saludo, mostrando el menú de 3 opciones solo ante un
mensaje ambiguo o un pedido explícito de "menú"/"opciones" (reusando `_is_help_intent`, `router.py:1158-1201`,
ya existente). Esto contradice el pedido explícito del dueño en esta misma sesión ("que le pregunte entre tres
opciones al hablar") — no se cambió acá, queda para que el dueño decida con este dato en la mano: ¿el menú va
en TODO saludo (como está specced) o solo cuando el mensaje es ambiguo?

**Estados nuevos** (`ConversationState`, prefijo `AUDITOR_CAMPANIA_` para no colisionar con los `CAMPANIA_*`
del encargado — son dos roles distintos hablándole al mismo bot):

0. `AUDITOR_ELIGIENDO_MODULO` — el menú de 3 opciones descripto arriba. Nuevo estado por defecto al saludar.
1. `AUDITOR_CAMPANIA_ELIGIENDO_TIPO` — quick_reply "Campaña de marca" / "Tour de Farmacias". Solo se llega acá
   por el atajo de texto ambiguo `"campaña"`; el menú y el atajo `"tour"` lo saltean porque ya vino resuelto.
2. `AUDITOR_CAMPANIA_ELIGIENDO_MARCA` — solo si comercial. `send_list_message` con marcas activas (tope duro
   de Meta: 10 filas por lista, ver nota abajo). Si no está en la lista: opción "Escribir el nombre" (texto
   libre) — busca por nombre y si no existe, la crea al vuelo en `marcas` (⚠️ decisión pendiente §6.11: si el
   auditor puede dar de alta marcas o eso queda reservado al admin).
3. `AUDITOR_CAMPANIA_NOMBRE` — texto libre. Para tour, sugerir `"Tour de Farmacias — {mes} {año}"` y permitir
   aceptar tal cual o reescribir.
4. `AUDITOR_CAMPANIA_AGREGANDO_ACCION` — solo comercial (el tour usa el checklist fijo de §3.1 directo, sin
   este paso). **(v5 — corrección dura de Meta/WhatsApp)** La versión anterior proponía un `quick_reply` con
   5 opciones de tipo (Exhibición/Material POP/Burbuja de precio/Descuento en caja/Custom); `send_quick_reply`
   trunca `buttons[:3]` en silencio (`meta_client.py:554`) — las opciones 4 y 5 se hubieran perdido sin error
   visible. Corregido a `send_list_message` (caben las 5 en una sola lista, tope real de 10 filas). Loop por
   acción: `send_list_message` tipo → texto libre descripción → quick_reply "¿Foto de referencia?" Sí/No
   (2 botones, dentro del límite) → si sí, espera imagen (`AUDITOR_CAMPANIA_ESPERANDO_REFERENCIA`) → quick_reply
   "¿Agregar otra acción?" Sí/No. **(v5 — alternativa a evaluar, hallazgo UX)** Con 4-5 acciones este loop son
   ~20-25 idas y vueltas antes de llegar a "alcance" — el especialista de UX conversacional sugirió permitir
   además un formato semi-estructurado de una línea por acción (ej. "Burbuja de precio: cartelería en puntera")
   parseado por líneas, dejando el loop uno-por-uno como fallback para quien prefiera ir despacio; no se
   descarta el loop, se anota como mejora a considerar en la implementación de Fase 8, no como bloqueante.
5. `AUDITOR_CAMPANIA_ALCANCE` — **(v5 — misma corrección de Meta/WhatsApp)** el `quick_reply` original tenía
   4 opciones (Todas/Por categoría/Con perfumería/Elegir por nombre), también arriba del límite de 3 botones;
   corregido a `send_list_message`. Si "Elegir por nombre": **texto libre**, no lista — con ~15-30+ sucursales
   activas no entran en el tope de 10 filas de una lista de Meta (`meta_client.py:612-617`, límite real ya
   documentado en el código). El auditor escribe nombres separados por coma, el bot hace matching difuso
   contra `sucursales.nombre` y confirma la lista resuelta antes de seguir. **(v5 — caso sin especificar,
   hallazgo UX)** Falta definir qué hace el bot si el matching no encuentra ninguna coincidencia para un
   nombre, o encuentra dos sucursales ambiguas con nombre parecido — sin esto especificado antes de programar,
   es el punto más probable donde el flujo se rompe en producción. Propuesta: si no hay match, listar el
   nombre no reconocido y pedir que lo reescriba o lo saque de la lista; si hay ambigüedad, mostrar las
   opciones candidatas (lista corta) para que el auditor elija.
6. `AUDITOR_CAMPANIA_PLAZO` — quick_reply defaults (7/14/30 días, 3 opciones — dentro del límite) o texto libre
   con otro número.
7. `AUDITOR_CAMPANIA_CONFIRMANDO` — resumen de todo lo cargado + quick_reply "Lanzar ahora" / "Guardar como
   borrador" / "Cancelar". **(v5 — refuerzo, hallazgo UX)** El resumen tiene que mostrar explícitamente la
   **cantidad y el listado de sucursales alcanzadas** (nunca solo un número), con especial énfasis cuando el
   alcance elegido fue "Todas las sucursales" — es el paso de mayor blast radius del flujo entero (un solo
   botón dispara WhatsApp real a todas las sucursales) y hoy no tiene más fricción que cualquier otro botón de
   confirmación del bot.

**Backend — no duplicar el fan-out**: la lógica de "crear `campania_tareas` + mandar `campana_nueva_sucursal`
por sucursal" vive hoy inline en el endpoint `activar_campania` (`main.py:791-876`). **(v5 — matiz del
arquitecto backend)** No es tan simple como "extraer una función": ese endpoint también depende de
`_require_admin_or_auditor(request)` (auth vía JWT del header `Authorization`, inaplicable al bot, que
identifica al auditor solo por teléfono) y lanza `HTTPException` inline en 3 puntos. La extracción correcta es
una función de servicio **pura** de dominio (ej. `activar_campania_core(client, campania_id, sucursal_ids,
plazo_dias)`) que levante excepciones de dominio propias, no `HTTPException` — cada caller (el endpoint
FastAPI, el handler del bot) resuelve su propia autenticación y su propio mapeo de error→respuesta por
separado. Creación de `campanias`/`campania_acciones` desde el bot usa `SupabaseManager` con service role
(como el resto del bot, bypassa RLS) en vez de PostgREST/RLS como hace el wizard web.

**(v5 — omisión real, hallazgo del arquitecto backend) `creado_por` sin resolución para creación por bot**:
`campanias.creado_por` es FK a `profiles(id)`, hoy lo llena el wizard web con el `user.id` de la sesión de
Supabase Auth. El bot identifica al auditor solo por teléfono contra la tabla `auditores` (`models.py:80-87`),
sin relación a `profiles`/`auth.uid()`. Si el bot crea la campaña vía `SupabaseManager`, `creado_por` queda
`NULL` y se pierde trazabilidad de qué auditor lanzó qué campaña por WhatsApp. Se agrega una columna
`creado_por_telefono text` (mismo patrón que `actor_nombre` en `campania_eventos`, que ya registra al actor
sin depender de `auth.uid()`) — va en la migración de Fase 7 junto con el resto de los cambios de `campanias`.

**Foto de referencia por WhatsApp**: mismo mecanismo que la evidencia del encargado —
`download_media_with_metadata` + upload a `desvio-evidencias/campania-referencias/` (mismo prefijo de la Fase
6) → guarda `imagen_referencia_path` en la fila de `campania_acciones` recién creada por el bot.

**UX — es un flujo largo para chat**: mensajes cortos, un dato a la vez, nunca formularios — mismo principio
que ya rige todo el bot (§2.3). **(v5 — corrección: esto ya existe, no es un gap)** La versión anterior de
este documento decía que faltaba inventar un handler de cancelación genérico. Falso: `router.py:1158-1201` ya
tiene `_is_cancel_intent`/`_is_help_intent`/`_is_summary_intent`, usados hoy en `EN_BLOQUE`/`STOCK_LOOP` con el
patrón CANCELAR/RESUMEN/AYUDA que la auditora ya usa a diario en la auditoría real. El trabajo de Fase 8 es
**extender ese helper existente** a los estados `AUDITOR_CAMPANIA_*`, no reimplementarlo desde cero.

**(v5 — gap real, sin solución existente) Timeout de un flujo abandonado**: si el auditor abandona el flujo a
mitad de camino (ej. queda en `AUDITOR_CAMPANIA_AGREGANDO_ACCION` con 2 de 5 acciones cargadas y no vuelve a
escribir), hoy no hay nada que lo saque de ese estado — a diferencia del riesgo de "cancelar" (que sí tenía
solución ya hecha), este es un gap real. Existe un patrón directamente aplicable: `check_incomplete_respuestas_
timeout` (`main.py:1303`) ya resetea a `IDLE` y avisa al usuario cuando expira un timeout en otro flujo — Fase
8 necesita un job análogo (24-48h) para `AUDITOR_CAMPANIA_*` que resetee a `IDLE` y ofrezca retomar/descartar
el borrador en vez de dejarlo trabado indefinidamente.

**Fase de implementación**: ver Fase 8 en §7. Depende de las Fases 6/7 (mismo modelo de datos, no agrega
tablas nuevas — solo un canal de creación adicional).

---

## 5. Riesgos técnicos transversales

1. **Colisión de estado conversacional (el más serio)**: `conversaciones` guarda UN solo `estado_actual` por teléfono. Un encargado con desvío + campaña activos se pisa a sí mismo. Mitigación fase 1: cola de flujos pendientes en el contexto JSON de `ultimo_mensaje` (al terminar un flujo, ofrecer el siguiente). Solución correcta (fase posterior): estado por `(telefono, tipo_flujo)` — cambio de schema no trivial.
2. **Ventana de 24h no modelada**: registrar `ultimo_mensaje_entrante_at` por conversación y decidir texto libre vs. template antes de cada envío business-initiated. (Bug latente ya existente en `send_alerta_coordinador`.)
3. **Sesiones en memoria**: `audit_session.py` usa dict en memoria — las campañas duran días, NO apoyarse en ese mecanismo; todo el estado de campaña vive en Supabase.
4. **Casos borde**: sucursal sin `tel_responsable` → fallback a notificación in-app + alerta coordinador (nunca fallar silencioso); corrección sin foto → exigir foto según tipo de acción (`requiere_foto`/`verificable_por_foto` parametrizado); multi-campaña activa en paralelo por sucursal (el rubro lo exige — nada de singleton).
5. **(v2 — especialista) Expectativas falsas de insumo**: sin distinguir `proveedor` (labo vs. cadena), el admin de la cadena promete un envío que no controla — el material POP lo trae el APM/repositor del laboratorio. Mitigado por `solicitudes_insumo.proveedor` + estado `Escalado_a_labo` (§2.1/§2.2).
6. **(v2 — especialista) Falsos "completada" en `descuento_caja`**: una foto de cartelería no prueba que el descuento esté activo en el sistema de caja — depende de otra área/sistema. Mitigado modelando `descuento_caja` como acción `verificable_por_foto = false`, de carácter informativo/administrativo, separada de `burbuja_precio` (§2.1).
7. **(v2 — especialista) Desvíos en limbo**: sin SLA del lado auditor, `En_revision` puede quedar sin resolución indefinidamente y el encargado pierde confianza en el sistema. Mitigado por `en_revision_desde` + job `remind_sla_auditor_revision` + antigüedad visible en el filtro (§1).

## 6. Decisiones de negocio pendientes (confirmar con la auditora/cliente)

1. **¿Quién aprueba las solicitudes de insumo con `proveedor = cadena`?** (default propuesto: admin; no existe rol logística). Para `proveedor = laboratorio_apm` ya no es "aprobación" sino escalamiento — falta definir **quién es el `contacto_trade` por defecto** (¿por marca, por laboratorio, un único contacto de la cadena?) **(v2 — especialista)**.
2. **¿El responsable opera campañas 100% por WhatsApp, o también tendrá la vista web `/mis-campanias`?** (propuesto: ambas, WhatsApp como canal primario).
3. **Lista inicial de marcas** para cargar el catálogo (y quién la mantiene).
4. **Plazo por defecto de reapertura tras rechazo** (propuesto: +48h) y **plazo default de tareas de campaña**.
5. **(v2 — especialista) SLA de revisión del auditor**: ¿72h es un valor fijo o debería ser configurable por severidad del desvío?
6. **(v2 — especialista) Venta real**: ¿unidad por defecto (unidades o pesos)? ¿quién carga `campania_resultados` (encargado, supervisor, admin) y con qué frecuencia (fin de campaña, semanal)?
7. **(v2 — especialista) Segmentación de sucursales**: ¿quién carga inicialmente `categoria`/`tiene_perfumeria` (carga manual puntual, import desde planilla existente)?
8. **(v2 — especialista) Criterio de `En_gestion_terceros`**: ¿queda 100% a criterio manual de la auditora, o se sugiere automáticamente pasado cierto número de días sin resolución?
9. **(v3, checklist actualizado en v5) Checklist del Tour de Farmacias**: ¿las 6 acciones fijas (vidriera, iluminación, góndolas, piso, limpieza, cadena de frío condicional — §3.1) alcanzan siempre, o la auditora necesita agregar/sacar ítems por tour puntual? (propuesto: precargado pero editable en el wizard, mismo criterio que el resto de §2.5 — no bloquea el desarrollo, es config del paso 2).
10. **(v3) Problema reportado en un Tour**: cuando el encargado marca "algo está mal" (foto + comentario en un ítem del tour), ¿alcanza con que quede visible en el tablero de campañas para que la auditora actúe manualmente, o tiene que generar automáticamente un desvío (`gestion`) para heredar el ciclo completo de revisión/SLA/escalamiento del Módulo 1? (propuesto: visible en el tablero primero — es la opción de menor esfuerzo; evaluar el auto-desvío como mejora si en la práctica los problemas de tour se pierden sin seguimiento).
11. **(v4) Alta de marcas desde WhatsApp**: ¿el auditor puede crear una marca nueva al vuelo durante el flujo de creación por chat (§Módulo 4, paso 2), o toda marca nueva tiene que cargarse primero desde el CRUD de Admin en el panel web? (propuesto: reservado al admin — evita duplicados/typos de nombre de marca sin un paso de validación).
12. **(v5) Cadena de frío condicional**: ¿qué flag de `sucursales` determina si `heladera_cadena_frio` entra en el checklist seedeado de un tour — el `tiene_perfumeria` que ya existe, uno nuevo (`tiene_refrigerados`), o carga manual por sucursal al momento de crear el tour? (no bloquea Fase 7 si se elige el default más simple: incluirlo siempre y dejar que la auditora lo saque si no aplica).
13. ~~**(v5) Foto de referencia en el Tour**~~ — **RESUELTO (v6, 2026-08-24)**: SÍ, también en el Tour. El mecanismo (`imagen_referencia_path`) ya es genérico a nivel de schema, el costo de habilitarlo es prácticamente cero, y el hallazgo del especialista de farmacias es correcto: `gondola_orden`/`limpieza` son justo los criterios más subjetivos del sistema, los que más se benefician de un "así debe quedar". Se habilita como campo opcional en las 6 acciones del checklist de tour, igual que en comerciales — no obligatorio, la auditora lo carga si quiere. Ver §3.1.
14. ~~**(v5) Menú de 3 opciones vs. salto directo a auditar**~~ — **RESUELTO (v6, 2026-08-24)**: se mantiene el menú SIEMPRE al saludar, tal como lo pidió el dueño explícitamente en esta sesión. El hallazgo de UX es válido como observación de fricción, pero no alcanza para revertir una instrucción explícita y deliberada del dueño solo por una hipótesis de volumen de uso — eso lo mide el uso real, no una auditoría de spec. Si en la práctica se confirma que agrega fricción real, se reconsidera con datos de uso, no antes.

## 7. Fases de implementación propuestas

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
integración POS (reemplaza la carga manual de `campania_resultados`); rol logística dedicado (hoy los insumos `proveedor=cadena` los aprueba `admin`); ~~planograma de referencia adjunto a la tarea~~ **promovido a Fase 6 (v3), ver abajo — ya no es futuro**; cola de estados por `(telefono, tipo_flujo)` en `conversaciones` (solución de fondo al riesgo #1 de §5).

**Fase 6 — Foto de referencia (v3/v6)** ✅ **implementado 2026-08-24**: columna `imagen_referencia_path` en `campania_acciones` (habilitada también para tour, v6) + input opcional en el wizard (`CampaniaWizard.tsx`, paso 2) + envío por el bot antes de pedir evidencia (`_handle_campania_tarea_activa`, `router.py`) + visible en `MisCampaniaDetail.tsx`. Migración: `frontend/docs/sql/etapa-31-campania-referencia.sql` — **(v7 — corrección de numeración)** ni `etapa-17`/`etapa-18` (propuesta original) ni `etapa-20`/`etapa-21` (corrección v5) estaban libres: el repo real llega hasta `etapa-30-sucursales-geo.sql`, verificado al momento de escribir la migración. Validado con smoke test manual (mismo criterio que `test_respuesta_recolectora.py`: fakes de `SupabaseManager`/`MetaClient`, sin DB real) — cubre el caso con foto de referencia (se manda `send_image_by_url` con caption "Así debería quedar:" ANTES del texto de evidencia) y sin ella (no se llama `send_image_by_url`, solo el texto). `tsc -b` y `eslint` limpios en los archivos tocados. **Falta correr la migración en Supabase** — acción del dueño, no técnica.

**Fase 7 — Tour de Farmacias (v3)** ✅ **implementado 2026-08-24**: ver MÓDULO 3 completo (§3) — `campanias.tipo`/`marca_id` nullable, 6 acciones de checklist fijas (vidriera, iluminación, góndolas, piso, limpieza, cadena de frío, **v5**), guarda de integridad en `campania_resultados` vía trigger (**v5**, solo `tipo='comercial'`), delta del bot en `_handle_campania_listando_tareas` (saltea el chooser Completada/Falta insumo, vía un helper `_enviar_prompt_evidencia` compartido con el flujo comercial), wizard con selector de tipo + checklist precargado (`CampaniaWizard.tsx`), tablero oculta "venta real" cuando `tipo='tour_interno'` (`CampaniaDetail.tsx`), badge de tipo en el listado (`Campanias.tsx`). Sin templates nuevos de Meta. `creado_por_telefono` (**v5**) se difirió a la Fase 8 — no tiene consumidor hasta que exista creación por bot, agregarla ahora sería schema muerto. Migración: `frontend/docs/sql/etapa-32-tour-farmacias.sql`, verificada contra el listado real del directorio (llegaba a `etapa-31` en ese momento). Validado: `tsc -b`/`eslint` limpios, `python -m py_compile` limpio, smoke test manual (mismo patrón que Fase 6) confirmando que un tour saltea directo a "mandame la foto" y una campaña comercial sigue mostrando el chooser Completada/Falta insumo sin cambios. **Falta correr la migración en Supabase.**

**Fase 8 — Crear y lanzar Campañas/Tour desde WhatsApp (v4)** ✅ **implementado 2026-08-24**: ver MÓDULO 4
completo — menú de entrada `AUDITOR_ELIGIENDO_MODULO` (3 botones: Auditar / Campaña / Tour, reemplaza el salto
directo a selección de sucursal en el saludo — títulos acortados por el límite de 20 caracteres de Meta) +
triggers de texto nuevos `"campaña"`/`"tour"` + 9 estados `AUDITOR_CAMPANIA_*` en el dispatcher (`router.py`),
con `send_list_message` en vez de `quick_reply` en cualquier paso con más de 3 opciones (tipo de acción, 5;
alcance, 6) + cancelación reusando `_is_cancel_intent` en cada paso + `campanias_service.py` nuevo (función
pura `activar_campania_core`, sin `HTTPException`/`Request`) + columna `campanias.creado_por_telefono`
(migración `etapa-33-campania-creado-por-telefono.sql`, verificada contra el listado real — llegaba a
`etapa-32`) + selección de alcance por texto libre con matching difuso (`difflib` + substring) y manejo
explícito de ambiguo/no-encontrado + subida de foto de referencia por WhatsApp durante el loop de acciones.
Validado: `python -m py_compile` limpio, smoke test manual con 5 casos (menú→auditar, campaña comercial
completa con foto de referencia, tour completo con checklist de 6 ítems precargado, cancelar a mitad de
flujo, alcance por nombre con ambigüedad y no-encontrado) — todos pasan sin DB real, mismo criterio que Fases
6/7.

**(v8 — simplificaciones deliberadas de esta fase, documentadas para no perderlas de vista)**:
- ~~`main.py` NO se tocó~~ — **RESUELTO (v9, 2026-08-24, mismo día).** La otra sesión comiteó su trabajo
  (`c0b02c4`); una vez que `main.py` quedó limpio otra vez se hizo el wireo pendiente: el endpoint `POST
  /api/campanias/{id}/activar` ahora delega en `campanias_service.activar_campania_core` (mismo cambio
  quirúrgico que ya estaba preparado, aplicado recién cuando fue seguro). Validado con un smoke test nuevo que
  ejercita `activar_campania_core` contra un fake client con la forma real de supabase-py (`.table().select()
  .eq()/.in_()/.execute()`), no solo mockeado como en los smoke tests de router.py — cubre el camino feliz y
  las 3 excepciones de dominio (`CampaniaNoEncontradaError`/`CampaniaSinAccionesError`/`SinSucursalesValidasError`).
- ~~Job de timeout de flujo abandonado no implementado~~ — **RESUELTO (v9)**, mismo motivo. Job nuevo
  `check_auditor_campania_timeout` (`main.py`, interval 1h, `AUDITOR_CAMPANIA_TIMEOUT_HORAS = 24`) + método
  `SupabaseManager.get_conversaciones_en_estados()` (mismo patrón que `get_conversacion`: trae todas las filas
  de `conversaciones` y filtra en Python, no hay índice por estado). Reusa `conversaciones.timestamp`, que ya
  se actualiza en cada paso del flujo — no hizo falta tabla ni columna nueva. Validado con smoke test: resetea
  a `IDLE` solo la conversación vencida (>24h sin actividad en estado `AUDITOR_CAMPANIA_*`), deja intacta una
  reciente y una en un estado no relacionado (`EN_AUDITORIA`).
- **Sin "Guardar como borrador".** La spec original (§Módulo 4) mencionaba `Borrador` como tercera opción en
  la confirmación final; se implementó solo `Lanzar ahora`/`Cancelar` — guardar un borrador por WhatsApp sin
  una forma de retomarlo después agregaba complejidad sin valor claro. Si hace falta, es una fase chica aparte.
- **La confirmación final hace doble función**: además de pedir el "Lanzar ahora", muestra la lista completa
  de sucursales resueltas — así se cubre en un solo paso tanto el refuerzo de UX de v5 ("mostrar sucursales
  explícitas antes de lanzar, no solo un conteo") como la confirmación del matching difuso del paso "elegir
  por nombre", en vez de agregar un paso intermedio extra solo para ese caso.

# 03 — Capa Frontend

> Análisis de coherencia sobre `frontend/` (React 19 + TypeScript + Vite 8 + Tailwind v4, deploy en Vercel,
> habla directo a Supabase vía PostgREST).
> Insumo vinculante: [`00-cimientos.md`](00-cimientos.md).
> Todas las citas de este documento fueron verificadas leyendo el archivo. Ver nota de trazabilidad al final.

---

## La pregunta que ordena todo lo demás

Los otros dos especialistas analizan una capa cuyo propósito no cambió. El frontend sí cambió de propósito.

Con **WhatsApp como canal de captura**, el frontend deja de ser una herramienta de trabajo del auditor y pasa a
ser el **lugar donde el trabajo capturado se vuelve legible y gestionable**. Eso reordena la prioridad de todo:

- Lo que **gana** peso: que lo que se muestra sea verdad. Un panel de lectura que miente es peor que no tenerlo,
  porque dirección toma decisiones sobre él sin manera de detectar el error.
- Lo que **pierde** peso: la ergonomía de captura en el navegador. Autosave, offline, cámara directa, responsive
  del formulario de auditoría — todo eso deja de ser deuda urgente porque el flujo se va a WhatsApp.

Por eso este documento pone **la falla silenciosa (E4) por encima de todo lo demás**, y no la duplicación
estética. El hallazgo más grave del frontend no es que haya cuatro sistemas de tokens: es que
**`getDashboardStats` inventa datos cuando la base viene vacía**, y ese es exactamente el modo de falla que un
panel de lectura no puede permitirse.

---

## E1 — Duplicación

### 1.1 El semáforo, contaminado desde el cliente (contrato B)

`frontend/src/lib/api.ts:703-713` define `computeBranchScore`, un score 0-100 que resta 15 por desvío vencido,
12 por crítico activo y hasta 36 por abiertos. `api.ts:715-724` define `resolveSemaforo`, que devuelve
`rojo / amarillo / verde`.

Ninguno de los dos mira la **puntuación de la auditoría** ni la **antigüedad** — solo cuenta desvíos. La vista
SQL sí las mira: umbrales de 3.0 y 4.0 de puntuación, y de 15 y 30 días de antigüedad
(`frontend/docs/sql/etapa-18-sucursales-dashboard.sql:73-84`).

La consecuencia práctica es que **`/dashboard` y `/sucursales` pueden pintar la misma sucursal de colores
distintos el mismo día**. Una sucursal auditada hace 40 días con cero desvíos abiertos sale *crítica* en el grid
(por antigüedad) y *verde* en el dashboard (porque no cuenta antigüedad). No hay ningún mecanismo que detecte la
contradicción; simplemente son dos pantallas que no se hablan.

**Sobrevive el SQL.** El plan de retiro está en E6/F2.

### 1.2 Tres funciones para el mismo umbral de score

| Función | Archivo | Devuelve |
|---|---|---|
| `scoreClasses` | `SucursalesDashboard.tsx:39` | clases de color |
| `scoreColor` | `SucursalDetail.tsx:56` | clases de color |
| `scoreBadgeClasses` | `AuditFichesGallery.tsx:41` | clases de badge |

Las tres codifican el mismo corte conceptual (bien / regular / mal sobre una escala 1-5) en tres lugares. Cambiar
el criterio de "score aceptable" hoy exige acordarse de tres archivos.

### 1.3 `SALUD_META` duplicado, y con formas distintas

- `SucursalesDashboard.tsx:32` — `Record<EstadoSalud, { dot, border, icon, label }>`
- `SucursalDetail.tsx:49` — `Record<EstadoSalud, { dot, pill, label }>`

Mismo concepto, mismos cuatro estados, **estructuras incompatibles**. La versión del grid incluye `icon`, que es
lo que da accesibilidad daltónica (estado codificado por forma además de color); la del detalle no lo tiene. O
sea que la duplicación no es solo redundante: **degradó silenciosamente la accesibilidad en una de las dos
pantallas**.

### 1.4 Dos helpers de WhatsApp conviviendo

- `utils.ts:3` `getWhatsappUrl(gestion)` — el legacy, usado en `DesvioDetail.tsx:19,49` y `DesviosGestion.tsx:16,901`.
- `utils.ts:99` `whatsappLink(tel, mensaje)` — el nuevo, con normalización de teléfonos argentinos (quita el 0
  de trunk, antepone 54, descarta números de menos de 10 dígitos).

El legacy **no normaliza**. Con WhatsApp como canal del producto, tener dos generadores de links donde uno
produce links rotos para ciertos formatos de teléfono deja de ser un detalle.

### 1.5 Cuatro fuentes de tokens de diseño

Verificado que **`index.css` no contiene ninguna directiva `@config`** (el archivo entero son 42 líneas, leídas).
Eso confirma que Tailwind v4 **no carga `tailwind.config.ts`**: sus 130 líneas de paletas son código muerto que
además engaña a quien lo lea buscando la fuente de verdad.

| # | Fuente | Estado real |
|---|---|---|
| 1 | `index.css:3-33` bloque `@theme` | **Vivo.** 7 variables de color + 2 animaciones. Es lo único que genera clases. |
| 2 | `tailwind.config.ts` | **Muerto.** v4 no lo lee sin `@config`. |
| 3 | `lib/design-tokens.ts` | **Casi muerto.** Solo 2 importadores: `StatusBadge.tsx:1` y `SeverityBadge.tsx:2`. |
| 4 | `tokens` hardcodeado por página | **Vivo y disperso.** `DesviosGestion.tsx:37` y `RevisionDesvios.tsx:12-21`, con hex duplicados entre sí (`#1E3A6D`, `#F15A29`, `#2A9D5F` y el mismo mapa de severidad Alta/Media/Baja). |

Los hex de la fuente 4 son los mismos valores que las variables de la fuente 1, escritos a mano otra vez. Un
cambio de marca hoy requiere tocar cuatro lugares y ninguno de los cuatro se entera de los otros.

### 1.6 Tres patrones de acceso a datos

1. **Hooks finos** (`hooks/useSucursales.ts`, `useGestion.ts`, `useReportes.ts`, …) que envuelven `api.ts` con
   `useState`/`useEffect` a mano.
2. **`lib/api.ts`** (1.401 líneas), la capa de servicio de facto.
3. **`supabase` directo desde la página**, salteándose las otras dos. Verificado en `Hoy.tsx:62`
   (`supabase.from('gestion').select('id_sucursal').eq('estado','En_revision')`), y presente también en
   `Dashboard.tsx`, `SucursalDetail.tsx` y `AuditFichesGallery.tsx`.

El costo concreto: no hay un solo lugar donde poner caché, reintento, o manejo uniforme de error. Cada pantalla
reimplementa su propio `loading`/`error`.

---

## E2 — Estado que se pierde

### 2.1 Nada que perder, y eso es la conclusión importante

El frontend **no es dueño de ningún estado** que no esté en la base. No hay borradores locales que sobrevivan al
refresh, no hay cola de envío, no hay caché persistente.

La única excepción relevante es `AuditPerfumeriaV2.tsx`: todo el estado de la auditoría en curso vive en
`useState`, sin autosave, así que un refresh pierde la auditoría entera. **Bajo la decisión de canal, esto deja
de ser un problema a resolver y pasa a ser un argumento para retirar la pantalla** (ver E5).

### 2.2 `@tanstack/react-query` instalado y sin usar

`package.json:14` declara `@tanstack/react-query ^5.100.5` y `package.json:15` `@tanstack/react-table ^8.21.3`.
Verificado por grep sobre todo `frontend/src`: **cero imports de `@tanstack`**. También `shadcn-ui ^0.9.5` en
devDependencies (`package.json:37`) sin un solo componente shadcn en el repo.

**Tomo posición: se borran las tres.** El argumento para adoptar react-query sería el caché y la
revalidación, pero bajo la decisión de canal el frontend es un panel de lectura con datos que cambian por
WhatsApp, no por interacción del usuario. Lo que necesita no es caché de cliente: es que **el servidor le dé
agregados listos** (movimiento B7 del backend). Adoptar react-query ahora agregaría una cuarta forma de traer
datos a las tres que ya existen — exactamente lo contrario del norte de esta ronda.

---

## E3 — Contratos

### Contrato A — Identidad de sucursal (**consumo**)

Consumo `sucursal_id` sin poder verificar que exista. Pero el hallazgo del frontend es más específico y agrava
lo que reportó backend:

**`SucursalDetail.tsx:570-573` lee `ficha.score_limpieza`, `ficha.score_stock`, `ficha.score_ofertas` y
`ficha.score_burbujas`** — las cuatro columnas del *schema drift*. El DDL del repo
(`migration_audit_fiches.sql`) no las define.

O sea: el frontend **ya renderiza una tabla completa de scores por bloque** que, si las columnas no existen en
Supabase, muestra `—` en las cuatro celdas de cada fila y nadie lo reporta como error, porque el propio código
tiene el fallback `ficha.score_limpieza != null ? ... : '—'`. **Un guión es indistinguible de "no hay dato" y de
"la columna no existe".**

*Necesito de backend*: que B2 resuelva el drift, y que me diga cuál es el nombre definitivo de esas columnas.
Hasta entonces esa tabla es decorativa.

### Contrato B — Estado de salud (**consumo, y contamino**)

Contamino con `computeBranchScore`/`resolveSemaforo` (E1.1). Me comprometo a retirarlos.

*Necesito de backend*: que la vista `sucursales_dashboard` exponga lo que hoy calculo yo y ella no da — en
particular el conteo de severidad Alta activa, que es lo que alimenta `criticos_activos` en el dashboard. El
movimiento B7 ya lo contempla.

**Además hay una divergencia de zona horaria que debe resolverse en este contrato.** `utils.ts:115 diasDesde` y
`utils.ts:126 esMesActual` calculan con la hora **local del navegador**; la vista SQL usa
`AT TIME ZONE 'America/Argentina/Buenos_Aires'` explícita. Coinciden solo mientras el navegador esté en
Argentina. El comentario de `utils.ts:112-114` reconoce el supuesto por escrito. Con dirección mirando el panel
desde cualquier lado, ese supuesto es frágil: la solución correcta es que la fecha venga resuelta desde SQL y el
cliente no la recalcule.

### Contrato C — Evidencia (**consumo**)

Muestro fotos por URL firmada. Si el bot nunca las sube a Storage (contrato C roto del lado de WhatsApp), yo
muestro vacío sin distinguirlo de "esta auditoría no tuvo fotos".

*Necesito de WhatsApp*: que W2 llene `foto_url` desde `storage_path`. *Me comprometo a*: distinguir visualmente
"sin evidencia" de "evidencia no disponible".

### Contrato D — Desvío → gestión (**consumo**)

Es el contrato que mejor funciona y el que más uso: `/desvios`, `/mis-desvios` y todo el ciclo de revisión viven
acá. No tengo objeciones estructurales.

### Contrato E — Permisos de módulo (**co-dueño del problema**)

Confirmado leyendo ambos lados: `permissions.ts:7-16` conoce 8 módulos (incluidos `campanias` y `mis_campanias`);
`main.py:135-142` conoce 6. Asignar `campanias` desde el panel devuelve HTTP 400.

Hay un **segundo defecto, solo del lado del frontend**: `permissions.ts:49-50` hace que `firstAllowedPath`
devuelva `/gestion-desvios` y `/revision-desvios`, que hoy son **redirects** a `/desvios?v=...`. El usuario que
cae ahí al loguearse pierde el query param y aterriza en el tab por defecto, no en el que le corresponde por
permiso. Es deriva de rutas tras la unificación de las dos pantallas en tabs.

*Posición*: la fuente única debe estar del lado del servidor (movimiento B6). El frontend consume, no define.

---

## E4 — Falla silenciosa

**Esta es la sección más importante del documento.** Un panel de lectura falla de una sola manera grave: mostrar
algo falso con la misma confianza con que muestra algo cierto.

### 4.1 Datos inventados en producción — el peor defecto del frontend

`api.ts:726` define `getDemoData()`, que devuelve una `DashboardStats` completa y verosímil: 48 reportes, 12
desvíos, 5 gestiones abiertas, 2 vencidas, sucursales ficticias. `api.ts:833-835` la devuelve **cuando las tres
queries vuelven vacías**.

El problema es que "las tres queries vuelven vacías" es exactamente lo que pasa cuando:

- una política RLS bloquea el acceso del rol,
- el token expiró y PostgREST devuelve conjunto vacío en vez de error,
- la conexión a Supabase está mal configurada tras un cambio de env var,
- o efectivamente no hay datos.

**Los cuatro casos se ven idénticos: un dashboard poblado y sano.** Dirección no tiene ninguna señal de que está
mirando ficción. Y el caso "efectivamente no hay datos" es *precisamente el estado actual del sistema* según
`HANDOFF.md:35`, que reporta 25 sucursales sin fichas que matcheen.

No es una hipótesis remota: es el estado más probable hoy.

*Corrección*: borrar `getDemoData` por completo. Un estado vacío honesto ("todavía no hay auditorías cargadas")
es infinitamente más útil que números plausibles.

### 4.2 El guión que oculta tres causas distintas

Ya descrito en E3/contrato A: `SucursalDetail.tsx:570-573` renderiza `—` indistintamente para "no hay dato",
"el valor es null" y "la columna no existe en la base". Mismo patrón de fondo que 4.1: **el frontend degrada a
un estado plausible en vez de a un estado honesto**.

### 4.3 Errores que pierden su causa

`api.ts:1038` envuelve cualquier fallo de `getDashboardStats` en un `Error('Failed to fetch dashboard stats')`
genérico y en inglés. Preserva `cause`, lo cual está bien, pero la UI muestra el mensaje de arriba. El operador
ve "falló" sin saber si fue permisos, red o datos.

### 4.4 Una ruta sin control de módulo

`App.tsx:248-253`: la ruta `/auditorias` está protegida solo por `allowRoles={['admin','auditor']}`, **sin
`module=`**, mientras rutas comparables sí lo tienen (`/campanias` en `App.tsx:265-269` usa
`module="campanias"`). Lo mismo en `/sucursales/:id/auditoria` (`App.tsx:256-263`). No existe un
`ModulePermission` para auditorías, así que el permiso fino no es asignable ahí. Es una inconsistencia del
modelo de permisos, no un agujero grave — pero es exactamente el tipo de deriva que el contrato E debería
prevenir.

### 4.5 Cero tests

`package.json` no incluye vitest, jest, ni testing-library — verificado leyendo el archivo completo. **No hay un
solo test de frontend.** Y lo que está sin cubrir no es cosmética: es `computeBranchScore`, la priorización de
buckets del Panel Hoy (`Hoy.tsx`), y `normalizeModulePermissions`. Las tres son lógica de negocio pura,
trivialmente testeable, y las tres deciden lo que el usuario ve.

---

## E5 — Superficie a borrar

Cada ítem verificado por grep sobre `frontend/src` antes de listarlo.

### Muerto confirmado (cero referencias)

| Qué | Evidencia |
|---|---|
| `components/WhatsAppAuditFlow.tsx` (178 líneas) | Cero imports. Irónicamente, una simulación del flujo de WhatsApp en React — justo lo que la decisión de canal vuelve definitivamente innecesario. |
| `components/CompletionCheckmark.tsx` (163 líneas) | Cero imports. |
| `tailwind.config.ts` (130 líneas) | `index.css` no tiene `@config`; v4 no lo lee. |
| `@tanstack/react-query`, `@tanstack/react-table`, `shadcn-ui` | Cero imports de `@tanstack`; ningún componente shadcn. |
| `export default DesviosGestion` (`DesviosGestion.tsx:1124`) y `export default RevisionDesvios` (`RevisionDesvios.tsx:503`) | Huérfanos tras la unificación en tabs; las páginas se montan como paneles. |

### Vivo solo a través del barrel

`components/Checkbox.tsx` y `components/Radio.tsx` se exportan desde `components/index.ts:4` y `:12` pero
**ningún archivo los consume**. Están vivos solo en el sentido de que el barrel los reexporta.

### La decisión grande: `AuditPerfumeriaV2.tsx`

**No es código muerto — está ruteado y es alcanzable.** Verificado: `App.tsx:18` lo importa con `lazy`, y
`App.tsx:256-263` lo monta en `/sucursales/:id/auditoria` para roles `auditor` y `admin`. Además hay un botón
"iniciar auditoría" en el grid de `SucursalesDashboard.tsx` que lleva ahí.

Arrastra siete archivos: la página más `AuditBlocksPanel`, `EvidenceCaptureGuided`, `AuditSummary`,
`DesvioCreationDialog`, `ProgressIndicator` y `ScoreSelector`.

**Mi posición: retirarlo, pero no todavía, y no a ciegas.** El razonamiento:

- *A favor de retirarlo*: duplica exactamente el flujo del bot (los mismos cuatro bloques LIMPIEZA/STOCK/
  OFERTAS/BURBUJAS, el mismo scoring 1-5), y lo duplica **peor** — sin persistencia, sin responsive, y enviando a
  un endpoint distinto del que usa el bot. Es una segunda implementación de la captura, que es justo lo que la
  decisión de canal vino a eliminar. Mantenerlo significa que cada cambio en el modelo de auditoría hay que
  hacerlo dos veces.
- *En contra de retirarlo ya*: es el **único fallback** si el bot se cae, y el bot hoy pierde las sesiones en
  cada redeploy (`audit_session.py:307`). Retirar el plan B antes de arreglar el plan A deja al sistema sin
  ninguna vía de captura durante los deploys.

**Por eso el retiro debe depender de W1** (persistir la sesión v2). Antes de eso, retirarlo es imprudente.
Y antes de decidir, hay que mirar el dato que no está en el código: **cuántas auditorías reales entraron por esta
pantalla**. Se responde contando en `audit_fiches` las fichas cuyo origen sea el endpoint web
(`/api/auditorias-completadas/perfumeria`) contra las del bot. Si el número es cero, la decisión se vuelve obvia.

---

## E6 — Propuesta

### F1 — Borrar los datos demo y hacer honestos los estados vacíos

Eliminar `getDemoData` (`api.ts:726`) y el fallback de `api.ts:833-835`. Reemplazar por un estado vacío
explícito, y distinguir en la UI tres casos hoy indistinguibles: sin datos, sin permiso, y error de carga. Propagar
la causa real en vez del `Error` genérico de `api.ts:1038`.

Es el movimiento de mejor relación impacto/esfuerzo de todo el frontend: es borrar código, y cierra el modo de
falla más peligroso de un panel de lectura.

### F2 — Retirar el semáforo del cliente (contrato B)

Borrar `computeBranchScore` y `resolveSemaforo` (`api.ts:703-724`) y hacer que `Dashboard.tsx` consuma los mismos
agregados que `/sucursales`. Requiere que backend exponga primero los conteos que hoy calculo yo (B7).

Efecto secundario grande: hoy `getDashboardStats` descarga `reportes` y `gestion` **completas** y agrega ~236
líneas en el navegador, con un N+1 cuadrático en el cálculo por zona — `api.ts:981-984` hace, por cada zona, un
`filter` sobre todas las sucursales y dentro un `find` por cada una. Retirar el semáforo del cliente es lo que
habilita mover esa agregación a SQL.

### F3 — Una sola fuente de tokens

Consolidar en el `@theme` de `index.css`: mover ahí las variables que faltan (severidad Media y Baja, estados de
gestión), borrar `tailwind.config.ts`, reemplazar los `style={{}}` inline de `DesviosGestion.tsx:37-70` y
`RevisionDesvios.tsx:12-21` por clases, y decidir el destino de `design-tokens.ts` (o se absorbe en `@theme`, o
queda como la API tipada que consume `StatusBadge`/`SeverityBadge` **leyendo** de las variables CSS — pero no
definiendo valores propios).

En el mismo movimiento: unificar `SALUD_META` en un solo módulo compartido conservando el campo `icon` (el que da
la accesibilidad daltónica), y las tres funciones de umbral de score en una.

### F4 — Un solo camino a los datos

Prohibir `supabase` directo desde páginas; todo pasa por `lib/api.ts`. Empezar por los cuatro casos conocidos
(`Hoy.tsx:62`, `Dashboard.tsx`, `SucursalDetail.tsx`, `AuditFichesGallery.tsx`). Borrar las tres dependencias sin
usar. No adoptar react-query (justificación en E2.2).

`api.ts` con 1.401 líneas debería partirse por dominio en el mismo movimiento, pero eso es consecuencia, no
objetivo.

### F5 — Tests de la lógica que decide lo que se ve

Introducir vitest y cubrir, en este orden: la priorización de buckets del Panel Hoy, `normalizeModulePermissions`,
y los helpers de fecha (`diasDesde`, `esMesActual`) contra la definición de la vista SQL — este último es el que
detectaría la divergencia de zona horaria del contrato B.

No propongo tests de componentes. El objetivo acá es blindar reglas de negocio, no renders.

### F6 — Retirar la captura web (depende de W1)

Con la sesión del bot ya persistida, retirar `AuditPerfumeriaV2` y sus seis componentes de apoyo, la ruta
`App.tsx:256-263`, y el botón de inicio del grid. Antes de ejecutar: contar auditorías reales entradas por esa vía
(ver E5).

En el mismo movimiento, la limpieza de código muerto de E5 y el arreglo de `firstAllowedPath`
(`permissions.ts:49-50`) para que apunte a `/desvios?v=...` en vez de a los redirects.

---

## Tabla de movimientos

| ID | Movimiento | Impacto | Esfuerzo | Riesgo | Depende de |
|----|-----------|---------|----------|--------|------------|
| F1 | Borrar `getDemoData` y los datos demo en producción; distinguir sin-datos / sin-permiso / error; propagar la causa real | Alto | Bajo | Bajo | — |
| F2 | Retirar `computeBranchScore`/`resolveSemaforo` (contrato B) y mover la agregación del dashboard a SQL, eliminando el N+1 por zona | Alto | Medio | Bajo | B7, B4 |
| F3 | Una sola fuente de tokens en `@theme`; unificar `SALUD_META` (conservando `icon`) y las tres funciones de umbral de score | Medio | Medio | Bajo | — |
| F4 | Un solo camino a los datos (todo por `api.ts`), borrar `@tanstack/*` y `shadcn-ui`, partir `api.ts` por dominio | Medio | Medio | Bajo | — |
| F5 | Tests (vitest) de priorización del Panel Hoy, `normalizeModulePermissions` y helpers de fecha vs. la definición SQL | Medio | Bajo | Bajo | — |
| F6 | Retirar la captura web (`AuditPerfumeriaV2` + 6 componentes + ruta), limpiar código muerto y corregir `firstAllowedPath` | Medio | Bajo | Medio | **W1**, B6 |

---

## Nota de trazabilidad

Verificado leyendo el archivo completo: `index.css` (42 líneas, sin `@config`), `package.json` (sin herramientas
de test, con las tres dependencias sin usar), `permissions.ts`, `utils.ts:90-133`.

Verificado por lectura del fragmento citado: `api.ts:694-733` y `:970-1009`, `App.tsx:248-269`,
`RevisionDesvios.tsx:10-23`, `Hoy.tsx:55-74`, `migration_audit_fiches.sql` completo.

Verificado por grep sobre `frontend/src`: cero imports de `@tanstack`; `design-tokens` importado solo en
`StatusBadge.tsx:1` y `SeverityBadge.tsx:2`; `Checkbox`/`Radio` referenciados solo desde el barrel
`components/index.ts:4,12`; `WhatsAppAuditFlow` y `CompletionCheckmark` sin ninguna referencia;
`AuditPerfumeriaV2` referenciado en `App.tsx:18,260`; `getWhatsappUrl` en `DesvioDetail.tsx` y `DesviosGestion.tsx`.

**No verificado, declarado como pendiente**: si las columnas `score_limpieza/stock/ofertas/burbujas` existen o no
en el Supabase real. Sin acceso a la base viva. De eso depende si la tabla de scores por bloque de
`SucursalDetail.tsx:570-573` muestra datos o guiones. Se resuelve con la consulta del anexo de
[`02-backend.md`](02-backend.md).

**No verificado**: el conteo de auditorías reales capturadas por la vía web contra la vía bot. Es el dato que
debe decidir F6 y no está en el código.

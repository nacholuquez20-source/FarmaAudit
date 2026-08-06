# 04 — Roadmap unificado

> Integración de los tres análisis especializados ([01-whatsapp](01-whatsapp.md),
> [02-backend](02-backend.md), [03-frontend](03-frontend.md)) contra los [cimientos](00-cimientos.md).
> Fecha: 2026-08-06 · Rama `master` · Ningún archivo de código fue modificado en esta ronda.

---

## Lo que hay que saber si solo se lee una sección

Los tres especialistas trabajaron en paralelo sobre la misma rejilla y llegaron, por caminos independientes, al
mismo diagnóstico de fondo: **el sistema no falla, degrada**. Casi ningún defecto encontrado produce un error
visible. Producen un resultado plausible y equivocado.

- El dashboard **inventa datos** cuando la base viene vacía (`api.ts:833-835`), y "vacía" es indistinguible de
  "sin permisos" o "mal configurado".
- La evidencia fotográfica de las auditorías **se evapora sola** a los ~30 días, porque nunca se sube a Storage
  (`audit_handlers.py:1158-1184`).
- Las gestiones se marcan vencidas **un día antes de tiempo** por una comparación en UTC contra una fecha
  argentina (`supabase_manager.py:866,871`).
- Una auditoría en curso **se pierde entera** en cada redeploy de Railway (`audit_session.py:308`).
- Los cuatro scores por bloque que muestra el detalle de sucursal probablemente sean **guiones permanentes**,
  porque leen columnas que el esquema del repositorio no define.

Ninguna de estas cinco cosas emite un error. Todas se ven como funcionamiento normal.

**La consecuencia para el orden de trabajo**: la primera tanda no es la más ambiciosa, es la que hace que el
sistema deje de mentir. Sale barata —tres de sus cuatro movimientos son de esfuerzo bajo, y uno consiste en
borrar código— y es la que vuelve confiable todo lo que se mida después.

---

## 1. Conflictos entre especialistas

Aparecieron tres. Uno es un error de los cimientos y se corrige acá.

### C1 — `determine_severity` no se retira (los cimientos estaban mal)

**El conflicto.** Cimientos §2.2 listó `determine_severity` (`audit_database.py:14`) entre lo que se retira en
favor de la vista SQL. Backend objetó explícitamente (02, E1.1) y WhatsApp lo confirmó desde el otro lado
(01, E1.5).

**Quién tiene razón: los especialistas.** `determine_severity` no es un semáforo de sucursal. Es el mapeo
`score del bloque → severidad del desvío`, que se persiste en `reportes.severidad` y `gestion.severidad`
(`audit_database.py:66,90,101-112`) y que después la vista SQL **consume como input**
(`etapa-18-sucursales-dashboard.sql:38-44`). Retirarla en favor de la vista sería circular: dejaría al pipeline
sin nadie que asigne severidad.

**Resolución.** Se corrige el documento de cimientos. `determine_severity` **no se borra, se muda**: pasa a ser
una definición única en la base (función SQL o columna generada) que Python invoca en vez de reimplementar. Lo
que sí se retira sin reemplazo es `computeBranchScore` y `resolveSemaforo` (`api.ts:703-724`), que son
duplicación pura.

Vale la pena registrar por qué pasó: los cimientos agruparon bajo "el semáforo" tres funciones que responden
preguntas distintas. **Que el mecanismo de coherencia haya producido la objeción en vez de tapar el error es
exactamente lo que se esperaba de él.**

### C2 — El orden entre W1 y B1 parecía un bloqueo y no lo es

WhatsApp declaró que W1 (persistir la sesión v2) depende de que backend entregue primero el runner de
migraciones (B1). Leído de golpe suena a que el movimiento más urgente del producto queda bloqueado detrás de
una tarea de infraestructura.

**Resolución.** No es un bloqueo, es una precedencia de una sola tanda. B1 es esfuerzo Medio / riesgo Bajo y
habilita a otros seis movimientos. Va en la primera tanda; W1 en la segunda.

### C3 — La zona horaria es el mismo defecto en dos capas, y ninguno de los dos lo vio entero

Backend encontró que `get_overdue_gestiones` compara `plazo_fecha` (columna `date`) contra
`datetime.now(timezone.utc)` (`supabase_manager.py:866,871`), lo que marca vencida una gestión a las 21:00 ART
del día anterior. Frontend encontró que `diasDesde` y `esMesActual` (`utils.ts:115,126`) calculan con la hora
local del navegador mientras la vista SQL usa `America/Argentina/Buenos_Aires` explícita.

Son la misma enfermedad: **tres capas calculando "hoy" con tres relojes distintos**. Ninguno de los dos lo
declaró como contrato porque cada uno vio solo su mitad.

**Resolución.** Se eleva a decisión transversal: *"hoy" se calcula una sola vez, en SQL, en zona horaria
argentina; ninguna otra capa lo recalcula*. B4 y la parte de fechas de F2 se ejecutan juntos, no por separado.

---

## 2. Dependencias

```
                    ┌─────────────────────────────────┐
   TANDA 0          │  Verificar contra Supabase      │
   (información)    │  + correr etapa-18 y etapa-16   │
                    └────────────┬────────────────────┘
                                 │ desbloquea B2 (y con él, todo el contrato A)
                    ┌────────────▼────────────────────┐
   TANDA 1          │  F1   B5   W2        B1         │
   (dejar de        │  ─────────────       │          │
    mentir)         │  sin dependencias    │ habilita │
                    └──────────────────────┼──────────┘
                                 ┌─────────┴──────────┐
   TANDA 2          │  W1 ◄── B1        W4        W5 ◄── B1  │
   (el canal)       └─────────┬──────────────────────────────┘
                              │ W1 habilita F6
   TANDA 3          │  B2 ◄── T0,B1    B3    B4 ─┬─► F2 ◄── B7  │
   (coherencia)     │  B6    B7 ─────────────────┘              │
                              │
   TANDA 4          │  F6 ◄── W1,B6    W3 ──► W6    F3   F4   F5   B8  │
   (simplificar)
```

Dependencias que cruzan capas, todas declaradas por ambos lados (el mecanismo funcionó):

| Movimiento | Necesita | Declarado por |
|---|---|---|
| W1 persistir sesión | B1 runner de migraciones | ambos |
| W2 evidencia a Storage | B política de buckets · F consumo de URLs firmadas | ambos |
| W5 fiabilidad Meta | B1 tabla `whatsapp_entregas` · **externo**: aprobación de plantillas en Meta | WhatsApp |
| F2 retirar semáforo cliente | B7 vistas de dashboard · B4 definición de vencida | ambos |
| F6 retirar captura web | **W1** (no retirar el plan B antes de arreglar el plan A) · B6 permisos | Frontend |
| B2 drift de `audit_fiches` | Tanda 0 (saber qué columnas existen realmente) | Backend |

---

## 3. Las tandas

### Tanda 0 — Verificación (no es código, es información)

Varias tandas están construidas sobre suposiciones que solo la base viva puede confirmar. **Ninguno de los tres
especialistas tuvo acceso a Supabase**, y los tres lo declararon.

1. **Correr `etapa-18` y `etapa-16`.** Son pendientes ya documentadas en `HANDOFF.md:5-15` y
   `ARQUITECTURA_DESVIOS_CAMPANIAS.md:299`. Sin la 18 el estado "sin datos" no existe y las sucursales nunca
   auditadas siguen saliendo en rojo; sin la 16, `/mis-campanias` devuelve cero filas por RLS.
2. **Responder si existen las columnas `score_limpieza/stock/ofertas/burbujas` y `total_desvios`** en
   `audit_fiches`. De esto depende si los cinco agentes de IA corren a ciegas y si la tabla de scores de
   `SucursalDetail.tsx:570-573` muestra datos o guiones permanentes. Consulta lista en el anexo de
   [02-backend](02-backend.md).
3. **Inventariar qué tablas existen realmente** contra las que el código consulta (el repo define ~19, el
   código Python consulta ≥24). Es el insumo del baseline de B1.
4. **Contar auditorías entradas por la vía web contra la vía bot.** Es el dato que decide F6 y no está en el
   código.

Esfuerzo real: una sesión con el SQL Editor abierto.

### Tanda 1 — Que el sistema deje de mentir

| Mov. | Qué | Por qué acá |
|---|---|---|
| **F1** | Borrar `getDemoData` y los datos demo en producción | Impacto Alto, esfuerzo Bajo, sin dependencias. Consiste en **borrar código**. Cierra el peor modo de falla de un panel de lectura. |
| **B5** | Seguridad: trigger anti-escalado de rol, CORS, quitar `GET` de endpoints que mutan, `META_APP_SECRET` obligatorio | Alto/Bajo/Bajo. La policy `profiles_role_protected` es SQL inválido y **nunca se creó**: hoy no hay anti-escalado de rol. |
| **W2** | Cerrar el contrato C: subir la evidencia a Storage, transcribir el audio | Alto/Bajo/Bajo. Los bytes **ya están en memoria** en ese mismo bloque, y el patrón correcto ya existe 500 líneas antes en el mismo archivo (`audit_handlers.py:651`). Cada día que pasa se pierde evidencia que no vuelve. |
| **B1** | Baseline del esquema real + runner de migraciones | Alto/Medio/Bajo. Habilita seis movimientos posteriores. Hoy la base **no es reproducible desde el repo**. |

**Prueba de fuego**: ninguno de los cuatro depende de nada de las tandas 2, 3 o 4. Verificado contra las tres
tablas de movimientos.

### Tanda 2 — Hacer confiable el canal

Acá se paga la decisión de canal: WhatsApp pasa a ser la columna vertebral y tiene que aguantarlo.

| Mov. | Qué |
|---|---|
| **W1** | Persistir la sesión v2 en Postgres reusando `to_dict`/`from_dict`, que **ya existen y están testeados** y nadie usa. Conectar `is_expired` a un job real y avisar al auditor cuando su sesión vence. |
| **W4** | Endurecer la entrada: menú completo de sucursales (hoy solo se ofrecen 10 de 25), matcheo exacto en decisiones destructivas, confirmación antes de crear desvíos, salida del estado `DONE`, y la invariante "ningún handler se calla". |
| **W5** | Fiabilidad Meta: firma obligatoria, procesar el batch completo, consumir `statuses`, modelar la ventana de 24 h. |

> **Arrancar el trámite de plantillas de Meta en la Tanda 0, no acá.** La aprobación es un proceso externo con
> latencia propia; si se pide recién al llegar a W5, la tanda se bloquea esperando a un tercero.

### Tanda 3 — Coherencia de datos

Es donde se cierran los cinco contratos.

| Mov. | Qué | Contrato |
|---|---|---|
| **B2** | Resolver el drift de `audit_fiches`, unificar nombres de columnas, agregar la FK a `sucursales` | A |
| **B3** | Función `crear_desvio` transaccional (reporte + gestión + evento en una sola operación), FK `gestion.id_reporte`. Elimina los **tres** caminos de creación con criterios distintos de severidad y plazo | D |
| **B4 + fechas de F2** | Una sola definición de "vencida" y un solo reloj para "hoy" (ver C3) | B |
| **B6** | Permisos de módulo: fuente única del lado del servidor | E |
| **B7** | Vistas de dashboard e índices | B |
| **F2** | Retirar `computeBranchScore`/`resolveSemaforo` y mover la agregación a SQL | B |

Al terminar esta tanda, la FK del contrato A debería resolver el síntoma de `HANDOFF.md:35` (25 sucursales
"sin auditar") o probar que el problema es de datos y no de esquema. Las dos respuestas sirven.

### Tanda 4 — Simplificar

Con el sistema ya confiable, se reduce superficie.

| Mov. | Qué |
|---|---|
| **F6** | Retirar la captura web (`AuditPerfumeriaV2` + 6 componentes + ruta) — **solo después de W1** |
| **W3** | Un único punto de entrada conversacional y separación formal de los tres dominios |
| **W6** | Partir `router.py` (6.937 líneas) y extraer un módulo `llm.py` con structured outputs — depende de W3 |
| **F3 · F4 · F5** | Tokens unificados · un solo camino a los datos · tests de la lógica de negocio |
| **B8** | Persistir el análisis multi-agente (hoy se re-paga Claude en cada consulta) |

> **W3 puede promoverse a la Tanda 2** si en el uso real se observa el síntoma que describe 01/E1.1: el auditor
> terminando una auditoría v2 y quedando dentro de un flujo v1 que no pidió. Es un bug de producto reproducible;
> hoy está en tanda 4 solo porque W4 mitiga parte del daño.

---

## 4. Lo que se decide no hacer

Tan importante como lo anterior. Cada descarte tiene su razón.

**No adoptar `@tanstack/react-query`; borrarlo.** Está instalado con cero imports. El argumento para adoptarlo
sería el caché de cliente, pero bajo la decisión de canal el frontend es un panel de lectura cuyos datos cambian
por WhatsApp, no por interacción del usuario. Lo que necesita es que el servidor le dé agregados listos (B7).
Adoptarlo agregaría un cuarto patrón de acceso a datos a los tres que ya existen — lo contrario del norte.

**No construir modo offline, PWA ni "modo campo mobile" para la captura web.** Estaba en el roadmap de
`HANDOFF.md:40`. La decisión de canal lo vuelve innecesario: esa ergonomía ahora la da WhatsApp, que funciona
offline por diseño. Invertir ahí sería mejorar la pantalla que F6 propone retirar.

**No reescribir `router.py`, solo partirlo, y recién en la tanda 4.** Son 6.937 líneas que hoy funcionan. Partir
por dominio conversacional después de W3 es reversible; reescribir no lo es.

**No unificar las dos máquinas de estado en una sola.** WhatsApp propuso algo mejor (W3): separarlas
formalmente por dominio con un único punto de entrada. Fusionar `ConversationState` (29 estados) con
`AuditState` (9) produciría una máquina de 38 estados que nadie puede razonar.

**No hacer scoring por marca de perfumería ni reportes de compliance.** Están en el roadmap estratégico
(`HANDOFF.md:41`) y tienen valor de monetización real, pero quedan fuera: el norte de esta ronda es coherencia.
Construir features de valor sobre datos que hoy pueden ser inventados (F1) o guiones permanentes (B2) es
construir sobre arena. **Después de la tanda 3, esto pasa a ser el candidato natural para la ronda siguiente.**

**No migrar el frontend de Supabase directo a una API propia.** Sería un cambio de arquitectura mayor sin
relación con el norte.

---

## 5. Estado de la verificación

Los tres documentos cumplen los criterios que fijó el plan:

- **Trazabilidad.** Se muestrearon citas de los tres documentos contra el código real. En 01 y 02 se verificaron
  `router.py:229-232`, `router.py:237`, `supabase_manager.py:859-877`, `audit_handlers.py:1158-1184` y
  `main.py:978`: las cinco verifican exactamente. El documento 03 fue escrito con verificación directa de cada
  cita (los agentes de frontend se cortaron por límite de gasto).
- **Cobertura de la rejilla.** Los tres responden E1 a E6 sin secciones vacías.
- **Cobertura de contratos.** Los cinco aparecen en al menos dos documentos, y las declaraciones cruzadas se
  corresponden. Apareció además un **sexto contrato no previsto** —el reloj compartido, C3— que se documenta acá
  y debería incorporarse a los cimientos.
- **Formato fusionable.** Las tres tablas de movimientos tienen columnas idénticas: 20 movimientos en total
  (6 W, 8 B, 6 F).
- **Prueba de fuego.** Los cuatro movimientos de la Tanda 1 no dependen de nada posterior.

### Pendientes declarados

1. ~~**Si las columnas `score_*` existen en el Supabase real.**~~ → **RESUELTO, ver §6.**
2. **Cuántas auditorías reales entraron por la web contra el bot.** Condiciona F6. Sigue pendiente.

---

## 6. Confirmación del drift de `audit_fiches` (2026-08-06)

Se obtuvo una fila real de la tabla en producción. La lista de columnas del `INSERT` tiene exactamente 14 y
coincide al pie con `migration_audit_fiches.sql`. **Confirmado: no existen `score_limpieza`, `score_stock`,
`score_ofertas`, `score_burbujas`, `total_desvios` ni `total_fotos`.**

La hipótesis del análisis era "los consumidores reciben `null`". **Era incorrecta, y la realidad es peor:** hay
**dos defectos distintos** con consecuencias opuestas, y hay que separarlos porque se arreglan distinto.

### Defecto 1 — Nombres divergentes: la UI muestra cero desvíos donde hay cinco

La base guarda `desvios_count` y `fotos_count`. El código lee `total_desvios` y `total_fotos`. Los consumidores
que usan `select('*')` **no fallan**: reciben el objeto sin esas claves, y `undefined` se propaga en silencio.

En la fila real, con `desvios_count = 5` y `fotos_count = 4`:

| Dónde | Código | Qué se renderiza |
|---|---|---|
| Galería de auditorías | `AuditFichesGallery.tsx:365,370` | `undefined > 0` es falso → **badge verde** con el texto `desvios` y ningún número |
| Detalle de sucursal | `SucursalDetail.tsx:575-576` | idem → celda **verde y vacía** |
| Detalle de sucursal | `SucursalDetail.tsx:570-573` | `undefined != null` es falso → **`—` permanente** en las cuatro columnas de score |

**Una auditoría que encontró 5 desvíos se muestra como una auditoría limpia, en verde.** No es un dato faltante
que se vea como faltante: es un dato correcto en la base que la UI convierte en su opuesto. Es el caso más puro
de la tesis de este roadmap —el sistema no falla, degrada— y ahora está confirmado con una fila real.

### Defecto 2 — Columnas inexistentes: dos consultas que fallan con 400

Los consumidores que nombran las columnas explícitamente **no degradan, revientan**. PostgREST devuelve
`400` (`42703, column does not exist`) ante una columna desconocida en el `select`:

- **`analysis_agents.py:105-113`** pide las cuatro `score_*` y `total_desvios` para el histórico de las últimas
  5 fichas. La consulta se ejecuta siempre que la ficha tenga `sucursal_id` (la fila real lo tiene). Es decir:
  **el endpoint `/api/analisis/ficha/{ficha_id}` está caído**, no corriendo a ciegas. Los cinco agentes de
  Claude nunca llegan a ejecutarse.
- **`Dashboard.tsx:42`** pide `total_desvios` explícitamente → el panel de fichas del dashboard falla.

Nota: el prompt de `_agente_campo` (`analysis_agents.py:139-143`) sí imprimiría `None` en los scores, porque lee
del dict de la ficha principal. Pero nunca se llega ahí: la consulta del histórico corta antes.

### Consecuencia para el orden de trabajo

**B2 sube de la Tanda 3 a la Tanda 1.** Ya no es "investigar un drift posible": es un defecto confirmado, con un
arreglo acotado y de riesgo bajo. Decidir un solo nombre por concepto (`desvios_count` / `fotos_count`, que es
lo que la base ya tiene) y corregir los seis call sites es esfuerzo Bajo.

Los cuatro `score_*` son una decisión aparte y más grande: **la base nunca los guardó**. El bot calcula el
promedio de bloques (`audit_fiches_manager.py:97`) pero descarta los scores individuales. Recuperarlos exige
agregar columnas y persistirlos desde el bot — es una funcionalidad que se diseñó y quedó a medio construir, no
un bug. Mientras tanto, las cuatro columnas de `SucursalDetail` y la galería deberían **ocultarse**, no mostrar
guiones que parecen datos faltantes.

### Ejecutado el 2026-08-06

Se aplicaron los arreglos confirmados. `tsc --noEmit` y `npm run build` pasan; `analysis_agents.py` compila.

**B2a — nombres unificados** (`total_desvios` → `desvios_count`, `total_fotos` → `fotos_count`):
`AuditFichesGallery.tsx`, `SucursalDetail.tsx`, `Dashboard.tsx` (interfaz, consulta y render) y
`analysis_agents.py`. La galería y el detalle de sucursal vuelven a mostrar el número real de desvíos en vez de
un badge verde vacío.

> Cuidado al releer: sobreviven a propósito `DashboardStats.total_desvios` (`types/index.ts:249`) y
> `ZonaResumen.total_desvios` (`types/index.ts:301`). **No son la columna de `audit_fiches`**: se calculan de
> `gestiones.length` (`api.ts:757`). Mismo nombre, otro concepto — vale la pena renombrarlos algún día para que
> no se confundan.

**B2b parcial — las dos consultas que devolvían 400**: se quitaron las columnas inexistentes del `select` de
`analysis_agents.py:107` y de `Dashboard.tsx:42`. El endpoint `/api/analisis/ficha/{ficha_id}` vuelve a
funcionar. Los prompts de los agentes de campo, calidad y negocio dejaron de enviar `Limpieza: None | Stock:
None | ...` y ahora mandan solo el promedio, que es el único score que la base realmente tiene.

**F1 — datos demo eliminados**: se borró `getDemoData` (78 líneas, con `Math.random()` en la tendencia de 30
días), su disparador en `getDashboardStats`, y el flag `isDemoData` del tipo. Dato que agrava el hallazgo
original: **ninguna pantalla leía `isDemoData`**, así que los datos inventados se mostraban sin ningún
indicador. Ahora una base vacía se ve vacía.

**Lo que NO se tocó, y por qué.** Las cuatro columnas `score_*` siguen en las interfaces de TypeScript y sus
paneles siguen renderizando `—`. No es un olvido: **la base nunca las guardó**, y decidir entre ocultar los
paneles o persistir los scores desde el bot (`audit_fiches_manager.py:97` calcula el promedio y descarta los
individuales) es una decisión de producto, no una limpieza. Queda abierta.

### F6 ejecutado el 2026-08-06 — la captura web se retiró

Decisión del dueño del producto: **la auditoría se hace solo por WhatsApp**. Se ejecutó F6 sin esperar a W1
(ver la advertencia al final). `tsc --noEmit` y `npm run build` pasan; `main.py` compila y `test_imports.py` da
verde.

**Borrado** (10 archivos): `AuditPerfumeriaV2.tsx` y sus seis componentes de apoyo (`AuditBlocksPanel`,
`EvidenceCaptureGuided`, `AuditSummary`, `DesvioCreationDialog`, `ProgressIndicator`, `ScoreSelector`), el hook
`useAudioRecorder`, y los dos componentes muertos que E5 ya había marcado (`WhatsAppAuditFlow`,
`CompletionCheckmark`). Además: la ruta `/sucursales/:id/auditoria`, tres exports del barrel,
`submitPerfumeriaAudit` en `api.ts`, y los cinco tipos del formulario en `types/index.ts`.

**Backend**: se eliminó el endpoint `POST /api/auditorias-completadas/perfumeria` y sus tres modelos Pydantic
(160 líneas de `main.py`). Esto **cierra uno de los tres caminos de creación de desvíos** que identificó E1.3 —
justamente el peor: hardcodeaba `severidad = "Media"`, usaba plazo fijo de 7 días, e insertaba un teléfono en
`desvio_eventos.actor_id`, que es `uuid`. B3 queda con dos caminos por unificar en vez de tres.

**Los cinco CTA ahora abren WhatsApp.** Un detalle que casi se pasa por alto: `WhatsAppAuditFlow.tsx` (el
componente muerto) tenía un mensaje pre-armado `"Hola, quiero hacer la auditoría de X. ¿Cómo procedo?"` que
**no habría disparado el bot**: `router.py:237` compara por igualdad exacta contra `V2_TRIGGERS`, y esa frase no
matchea ni la lista exacta ni la de substrings. El texto pre-cargado tiene que ser exactamente `auditoria`.
Quedó centralizado en `whatsappAuditLink()` (`utils.ts`), junto con el número del bot, para que el disparador
viva en un solo lugar. `VITE_WHATSAPP_PHONE` se documentó en `frontend/.env.example`.

> **Riesgo aceptado, sin mitigar.** El roadmap ataba F6 a W1 porque el bot pierde la sesión en cada redeploy de
> Railway (`audit_session.py:308`). Ya no hay ninguna vía de captura alternativa: si el bot se cae, no se audita.
> **W1 sube a ser el trabajo más urgente del sistema.**
>
> Efecto secundario a tener en cuenta: el auditor ahora llega al bot sin contexto de sucursal, así que la elige
> dentro de WhatsApp — y ese menú hoy ofrece **solo 10 de las 25** (`audit_handlers.py:838-841`). Las demás se
> alcanzan escribiendo parte del nombre, pero no es obvio. **W4 también sube de prioridad.**

### W1 y W4 ejecutados el 2026-08-06 — el bot deja de perder auditorías

Los dos movimientos que F6 había vuelto urgentes. **17 tests nuevos
(`test_audit_hardening.py`) y regresión verde en los 9 archivos de test de auditoría.**

> ✅ **`etapa-19-sesiones-whatsapp.sql` corrida y verificada el 2026-08-06.** Se hizo un round-trip real contra
> Supabase (escribir sesión con scores + foto + desvío → vaciar el cache en memoria → recuperar): 11/11 checks
> OK. Sobreviven estado, scores, fotos, desvíos y auditor. La fila de prueba se borró; la tabla quedó en 0 filas.

**W1 — la sesión sobrevive al redeploy.** Resultó tan barato como estimaba el análisis: `audit_session.py` ya
tenía `to_dict`/`from_dict` completos y testeados, y expone cinco funciones que son el único punto por donde los
handlers tocan el almacenamiento. Se convirtieron en *cache-aside* sobre la nueva tabla `sesiones_whatsapp`
(PK por teléfono, que expresa en el esquema la invariante "un auditor, una auditoría en curso").
**Ningún handler cambió.**

Tres decisiones de diseño que vale la pena registrar:

- **Degradación explícita**: si Supabase no responde, se loguea y se sigue en memoria. El bot nunca se cae por
  esto. Efecto secundario útil: toda la suite de tests corre sin base y sin modificarse.
- **`from_dict` ahora ignora campos desconocidos.** Antes reventaba con `TypeError`. Ahora que las sesiones
  cruzan deploys, una fila escrita por la versión anterior tiene que seguir siendo legible por la nueva — si no,
  el primer deploy con un campo nuevo perdería todas las auditorías en curso, que es justo lo que veníamos a
  arreglar.
- **`inactivity_notice_at` vive en el JSON, no en una columna.** La migración lo tenía como columna hasta que
  caí en que eso creaba una segunda fuente de verdad para el mismo dato. Se corrigió antes de escribirla.

El job `check_expired_audit_sessions_v2` (cada 15 min) avisa a las 2 h de inactividad y cierra a las 24 h,
avisando siempre. Hasta ahora `expires_at` existía y **no lo miraba nadie**.

**W4 — la entrada del auditor.** Seis arreglos, todos con test:

| Qué pasaba | Ahora |
|---|---|
| El menú ofrecía 10 de 25 sucursales (`chunk = sucursales[:10]` con una condición siempre verdadera) | Texto numerado cuando no entran en una lista de Meta, igual que el flujo v1 |
| Un sticker iniciaba auditoría sobre la primera sucursal alfabética (`"" in nombre` es `True`) | Se pide una elección explícita |
| `"no sirve"` confirmaba la auditoría (`"si"` está dentro de `"sirve"`) | Match por token exacto, con la negativa evaluada primero |
| Cualquier texto en `DONE` se guardaba como responsable — **el origen del `'Ch'` de tu base** | Se valida largo y se rechazan acuses de recibo |
| `DONE` sin desvíos no contestaba nada y la sesión quedaba viva para siempre | Siempre responde, y hay salida explícita |
| Un `"ok"` durante la evidencia creaba un desvío real en `gestion` | Flag `awaiting_note_text` distingue descripción de acuse de recibo |
| Documento/video/ubicación dejaban al bot mudo | Contesta explicando qué espera |

También se eliminó el atajo muerto de plantillas. **`NOTES_TEMPLATES` no se tocó**: se usa de verdad después de
cada foto y cada audio. Lo único inalcanzable era escribir la palabra "problema", y ese bloque era además la
cabeza de la cadena `if/elif` que contiene el manejo de fotos — borrarlo sin convertir el primer `elif` en `if`
habría roto la captura de evidencia.

### Hallazgos secundarios de la misma fila

- **`url_pdf` guarda una URL firmada ya vencida.** El token tiene `exp` a 24 h de su emisión (2026-07-29); la
  columna es permanente. Todo enlace guardado sirve un link muerto para siempre. Por eso existe
  `create_signed_ficha_url`, pero la URL vieja quedó persistida igual. Debería guardarse solo el path
  (que ya está en `google_drive_id`) y firmar al momento de servir.
- **`responsable_desvios` = `'Ch'`.** Tiene toda la forma del defecto que describe 01/E4.4: en el estado `DONE`,
  cualquier texto que no sea keyword se toma como nombre del responsable. Es evidencia de que W4 no es
  hipotético.
- **`sucursal_id` = `'SUC025'` tiene el formato correcto.** Esta fila **debilita** la hipótesis de que el
  "25 sucursales sin auditar" de `HANDOFF.md:35` sea un desajuste de formato en el contrato A. Con
  `fecha_auditoria` del 2026-07-28, SUC025 debería aparecer en verde. Conviene revisar cuántas filas tiene
  realmente `audit_fiches`: la explicación más simple es que solo unas pocas sucursales fueron auditadas.

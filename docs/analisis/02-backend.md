# 02 — Backend y datos

> Especialista: backend / base de datos. Rejilla E1-E6 según `docs/analisis/00-cimientos.md`.
> Fecha: 2026-08-05 · Rama: `master` · Ningún archivo de código fue modificado.

---

## Nota previa: qué pude verificar y qué no

Todo lo que sigue está verificado **leyendo el repositorio**. No tengo acceso a la base de
datos viva de Supabase. Eso importa mucho más de lo que parece, porque el hallazgo central de
este informe es justamente que **el repositorio y la base de datos real divergieron**, y no
existe ninguna forma de saber cuánto sin conectarse.

Cuando una afirmación depende del estado real de Supabase lo digo explícitamente y propongo
cómo verificarla. Hay una consulta de diagnóstico al final de la sección E3 pensada para eso.

Un dato de calibración: `supabase_setup.sql` define 7 tablas y `frontend/docs/sql/` agrega
otras 12 aproximadamente. El código Python consulta al menos 24 tablas distintas. La brecha
no es un detalle de higiene: es el tema de este documento.

---

## E1 — Duplicación

### 1.1 El semáforo, por tercera vez (contrato B)

Ya está diagnosticado en cimientos §4-B y lo confirmo desde mi lado. Las tres implementaciones:

- **SQL** — `frontend/docs/sql/etapa-18-sucursales-dashboard.sql:73-84`: cuatro estados
  (`critica`/`atencion`/`ok`/`sin_datos`), umbrales de puntuación 3.0 y 4.0, umbrales de días
  15 y 30, y cálculo de "hoy" en `America/Argentina/Buenos_Aires`
  (`etapa-18-sucursales-dashboard.sql:31-33`).
- **TypeScript** — `frontend/src/lib/api.ts:703-722`: `computeBranchScore` resta 15 por
  vencido, 12 por crítico activo y 3 por abierto (con tope de 36); `resolveSemaforo` devuelve
  tres estados y **no mira ni puntuación ni antigüedad**.
- **Python** — `audit_database.py:14-21`: `determine_severity` mapea el score de bloque 1-5 a
  `Alta`/`Media`/`Baja`; `audit_database.py:24-37` hace lo mismo con el promedio.

Sobrevive el SQL, según lo decidido. Pero conviene ser preciso sobre **qué** se retira, porque
las tres funciones no responden la misma pregunta:

`determine_severity` no es un semáforo de sucursal — es el mapeo `score del bloque → severidad
del desvío` que se persiste en `reportes.severidad` y `gestion.severidad`
(`audit_database.py:66`, `audit_database.py:90`, `audit_database.py:101-112`). Esa severidad
es un **input** de la vista SQL (`etapa-18-sucursales-dashboard.sql:38-44` cuenta desvíos por
estado, y el front filtra por severidad). Retirar `determine_severity` a favor de la vista
sería circular. Lo que corresponde es distinto: **no borrarla, sino moverla a la base como
única definición** —una columna generada o una función `sql` invocable— para que Python y SQL
no puedan discrepar. Lo señalo como desacuerdo parcial con cimientos §2.2: la fila de la
tabla dice "se retira `determine_severity`" y eso, leído literalmente, deja el pipeline sin
quién asigne severidad.

`computeBranchScore` y `resolveSemaforo` sí son duplicación pura y sí se retiran sin
reemplazo propio. Plan concreto en E3.

### 1.2 Dos definiciones de "vencida" que no coinciden

Esta es la duplicación que más daño hace y no estaba en cimientos.

- El job de fondo `check_overdue_gestion` (`main.py:1539-1579`) escribe `estado = 'Vencida'`
  en la tabla cada 15 minutos (`main.py:1560`), sobre lo que devuelve
  `get_overdue_gestiones` (`supabase_manager.py:859-877`).
- La vista SQL calcula vencido **de nuevo y por su cuenta**:
  `estado = 'Vencida' OR plazo_fecha < (SELECT d FROM hoy_ar)`
  (`etapa-18-sucursales-dashboard.sql:41-44`).
- El front calcula vencido **una tercera vez**, y solo por estado:
  `gestion.estado === 'Vencida'` (`frontend/src/lib/api.ts:844`, `api.ts:880`).

Los tres pueden dar resultados distintos sobre la misma fila, y hay un desfase real de zona
horaria: `get_overdue_gestiones` compara `plazo_fecha` (columna `date`, definida en
`supabase_setup.sql:46`) contra `datetime.now(timezone.utc).isoformat()`
(`supabase_manager.py:866,871`). Postgres castea la fecha a medianoche, así que una gestión
con plazo **hoy** se marca `Vencida` a las 00:00 UTC — o sea a las 21:00 ART del día
anterior. El responsable pierde el último día de plazo, y el semáforo se pone en rojo un día
antes de tiempo. La vista SQL, en cambio, sí usa la fecha argentina
(`etapa-18-sucursales-dashboard.sql:32`).

### 1.3 Dos caminos para crear reporte + gestión

El mismo par `reporte` + `gestion` + `desvio_eventos` se construye en tres lugares con
detalles distintos:

| Camino | Dónde | Severidad | Plazo | Evento |
|---|---|---|---|---|
| Bot v2 | `audit_database.py:79-131` | `determine_severity(score)` | fijo 7 días (`:99`) | `auditor_hallazgo` (`:119-131`) |
| Bot (extracción IA) | `supabase_manager.py:486-570` | de la IA, con fallback `Media` (`:504-507`) | según `severity_deadlines` (`:533-534`) | — |
| Endpoint web | `main.py:965-1049` | **hardcodeado `"Media"`** (`:978`, `:1003`) | fijo 7 días (`:1006`) | `creacion` (`:1028-1040`) |

Tres criterios de plazo, tres criterios de severidad. `config.py:54-58` define
`severity_deadlines` (Alta 24h / Media 72h / Baja 168h) y **solo uno de los tres caminos lo
usa**. Es exactamente el síntoma que describe cimientos §1: cambiar la regla exige tocar tres
archivos y acordarse de los tres.

### 1.4 Etapas SQL duplicadas entre sí

- **`etapa-6` y `etapa-7` son casi el mismo archivo.** Ambas crean `desvio_notificaciones`
  con el mismo DDL (`etapa-6-storage-mensajes.sql:12-19` vs
  `etapa-7-bot-encargado.sql:16-25`), ambas crean el bucket `desvio-evidencias`
  (`etapa-6:54-66` vs `etapa-7:59-71`) y ambas definen las mismas cuatro policies con los
  mismos nombres.
- **La 7 relaja lo que la 6 endurece.** La policy `storage_evidencias_upload` de la etapa 6
  exige `auth.uid() IS NOT NULL AND EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid())`
  (`etapa-6-storage-mensajes.sql:73-77`); la etapa 7 la vuelve a crear con solo
  `auth.uid() IS NOT NULL` (`etapa-7-bot-encargado.sql:77-80`). Como comparten nombre y la 7
  hace `DROP POLICY IF EXISTS` primero (`etapa-7:73`), **si se corrieron en orden, gana la
  versión débil**: cualquier usuario autenticado de Supabase Auth puede subir al bucket
  privado, tenga perfil en el panel o no. Lo mismo con `storage_evidencias_read`
  (`etapa-6:79-87` vs `etapa-7:82-89`).
- **Dos archivos con el número 8**: `etapa-8-respuesta-recolectora.sql` y
  `etapa-8-update-rls.sql`. No hay forma de saber cuál va primero salvo por el nombre.

---

## E2 — Estado que se pierde

### 2.1 El esquema de la base no existe en el repositorio

Este es el hallazgo de mayor gravedad de mi capa, y no es una exageración: **la base de datos
de FarmaAudit no se puede reconstruir desde el repositorio.**

`init_supabase.py:46-54` lista siete tablas que considera críticas. De esas, tres **no tienen
`CREATE TABLE` en ningún archivo del repo**: `checklist_perfumeria`, `conversaciones` y
`sesiones_auditoria`. Y cuando falta una, `init_supabase.py:62` loguea
`"run supabase_schema.sql manually"` — un archivo que **no existe** (verificado con `glob`
sobre todo el repositorio: cero coincidencias para `supabase_schema.sql`).

El inventario completo de tablas que el código usa sin DDL en el repo:

| Tabla | Dónde se usa | DDL en el repo |
|---|---|---|
| `conversaciones` | `supabase_manager.py:253`, `279` | no — solo un `ALTER` en `etapa-8-respuesta-recolectora.sql:93` |
| `sesiones_auditoria` | `supabase_manager.py:1432`, `1463`, `1526` | no — solo `ALTER` (`etapa-11:5-6`, `etapa-8-respuesta:88-89`) y FKs que la referencian (`etapa-9:9`, `etapa-12:6`) |
| `checklist_perfumeria` | `supabase_manager.py:1373`, `1422` | no |
| `checklist_plantillas` / `checklist` | `supabase_manager.py:1311`, `1338` | no |
| `areas` | `supabase_manager.py:229` | no |
| `pendientes` | `supabase_manager.py:339`, `367`, `396` | no |
| `maestro_auditores` | referenciada por RLS en `etapa-12:66`, `etapa-12:91` | no |
| `respuesta_pregunta` | `supabase_manager.py:1787-1891` | no — solo `ALTER ... IF EXISTS` (`etapa-8-update-rls.sql:4`) |
| `respuesta_pregunta_audit_log` | `supabase_manager.py:1876`, `1891` | no — solo `ALTER ... IF EXISTS` (`etapa-8-update-rls.sql:41`) |
| `desvios_borrador` | `supabase_manager.py:572-718` | sí — `etapa-10-desvios-borrador.sql` |

El patrón `ALTER TABLE IF EXISTS` de `etapa-8-update-rls.sql:4,8,11,14,19` es la prueba
documental del problema: el autor **sabía** que la tabla podía no existir y escribió el
script para no fallar en ese caso. Un runner de migraciones no habría permitido esa
ambigüedad.

**Gravedad real.** No es un problema estético ni "para cuando escalemos":

1. **No hay entorno de staging posible.** Levantar una segunda instancia de Supabase para
   probar un cambio antes de producción requiere reconstruir a mano un esquema que nadie
   escribió. En la práctica esto significa que **todo se prueba en producción**, que es
   exactamente lo que HANDOFF.md:49 documenta ("las queries corren y traen datos reales").
2. **No hay recuperación ante desastre.** Si la instancia de Supabase se pierde o se corrompe,
   el repositorio no alcanza para volver a levantarla. Los backups de Supabase mitigan esto,
   pero dependen de una configuración que el repositorio tampoco documenta.
3. **No hay revisión de cambios de esquema.** Un `ALTER TABLE` corrido a mano en el editor SQL
   no pasa por PR, no queda en el historial de git y no se puede revertir.
4. **El drift ya ocurrió y ya causó daño** — ver E3, contrato A.

Es, sin embargo, un problema **acotado y con salida clara**: la base viva es la fuente de
verdad actual, y `pg_dump --schema-only` la convierte en texto versionable en una tarde.

### 2.2 No hay runner de migraciones ni tabla de versiones

El estado "corrido / no corrido" de cada etapa vive **en prosa dentro de archivos markdown**.
`HANDOFF.md:5-15` dice, textualmente, que hay que volver a correr
`etapa-18-sucursales-dashboard.sql` porque la vista se modificó después de la última
ejecución. `MEMORY.md` (memoria del proyecto) registra `etapa-18` y `etapa-16` como
pendientes. Nada de eso lo puede verificar un programa.

Consecuencias verificadas:

- **`etapa-12` no compila.** `etapa-12-desvios-auditoria-perfumeria.sql:72` cierra la primera
  policy con `)` de más — la cláusula `USING (...)` ya cerró en la línea 71 — y lo mismo pasa
  en la línea 82 con la segunda. Postgres aborta el archivo entero ahí. La tercera policy
  (`:86-104`) está bien escrita pero nunca se ejecuta. Es decir: **la tabla
  `desvios_auditoria_perfumeria` o no existe, o existe con RLS habilitada
  (`etapa-12:58`) y cero policies, lo que la vuelve ilegible para todo el mundo salvo el
  service key.** Como además esa tabla es un "término muerto" según cimientos §3, el archivo
  entero está roto y nadie se enteró en dos meses.
- **`etapa-12` también depende de `maestro_auditores`** (`etapa-12:66`, `:91`), tabla sin DDL
  en el repo. Aunque se arreglaran los paréntesis, fallaría por eso.
- **Los números de etapa no son un orden.** Dos archivos comparten el 8, y `etapa-14` hace
  `ALTER TABLE desvio_notificaciones` (`etapa-14-desvio-revision.sql:32-37`) sobre una tabla
  que crean tanto la 6 como la 7 — si ninguna de las dos se corrió, la 14 falla a mitad de
  archivo, dejando aplicados los `ALTER` de `gestion` de las líneas 4-18 pero no los de
  `desvio_notificaciones`. **Ninguna etapa está envuelta en una transacción**, así que un
  fallo parcial deja la base en un estado intermedio que nadie registra.

### 2.3 El análisis multi-agente se tira a la basura y se vuelve a pagar

`frontend/docs/sql/etapa-17-analisis-agentes.sql:5-21` crea la tabla `analisis_auditoria` con
seis columnas JSONB, un índice único por `ficha_id` (`:24-25`) y RLS (`:32-35`). El comentario
de la línea 23 dice "Cada ficha tiene un análisis máximo (evita duplicados, los nuevos
reemplazan)". La intención está clarísima.

**Nadie escribe en esa tabla.** Un grep de `analisis_auditoria` sobre todos los `.py`, `.ts` y
`.tsx` del repositorio devuelve **cero coincidencias**. `AuditAnalysisOrchestrator.analizar`
(`analysis_agents.py:306-348`) construye el dict de resultado y lo devuelve; el endpoint
`main.py:1819-1838` lo serializa a la respuesta HTTP y termina. No hay `insert`, no hay
`upsert`.

El costo es concreto y medible: cada invocación de `POST /api/analisis/ficha/{ficha_id}`
dispara **seis llamadas a Claude** — cinco agentes en paralelo (`analysis_agents.py:313-320`)
más la síntesis (`analysis_agents.py:339`), cada una con `max_tokens=1024`
(`analysis_agents.py:56`). Si el usuario recarga la pantalla, se pagan seis llamadas de nuevo.
Si dos personas de dirección miran la misma ficha, doce. No hay caché de ningún tipo.

Además el análisis es **irreproducible**: no queda registro de qué dijeron los agentes sobre
una auditoría de hace tres meses, lo que anula el valor de auditoría del propio análisis.

### 2.4 Un `retry` que reintenta contra el vacío

`_claim_message_distributed` (`main.py:234-257`) devuelve `True` —o sea, "procesá el
mensaje"— en **tres** rutas de fallo distintas: cuando no hay cliente Supabase
(`main.py:239`), cuando la tabla `webhook_dedup` no existe (`main.py:255`) y ante cualquier
otra excepción (`main.py:257`). El comentario de la línea 256 lo llama "falling back to
in-memory only", lo cual es honesto pero incompleto: con dos instancias en Railway, la
deduplicación en memoria (`main.py:127-130`) no comparte estado, y un reintento de Meta
procesado por la otra instancia crea el desvío dos veces.

---

## E3 — Contratos

Toco los cinco. Detallo qué asumo de otras capas y qué necesito.

### Contrato A — Identidad de sucursal · **roto, y peor de lo que parece**

**Confirmado.** `migration_audit_fiches.sql:8` declara
`sucursal_id VARCHAR(50) NOT NULL` sin `REFERENCES sucursales(id)`, mientras que la línea 7
inmediatamente anterior sí declara
`id_reporte TEXT NOT NULL REFERENCES reportes(id) ON DELETE CASCADE`. La asimetría es visible
en dos líneas consecutivas del mismo `CREATE TABLE`.

Agrego contexto que matiza la conclusión de cimientos §4-A. Rastreé de dónde sale el valor
que escribe el bot:

- `audit_handlers.py:870` lee `sucursales` directamente
  (`db.client.table("sucursales").select("id, nombre")`), guarda los IDs en el menú de sesión
  (`audit_handlers.py:896`) y `audit_handlers.py:942` asigna
  `session.sucursal_id = elegida["id"]`. Ese valor **sí** viene de `sucursales.id`.
- `audit_fiches_manager.py:105` escribe ese mismo `session.sucursal_id` en la ficha.

O sea: **por el camino v2 del bot, la FK se cumpliría**. La ausencia de FK no es la causa
probada del "25 sucursales sin auditar" de `HANDOFF.md:35` — es la razón por la cual **no
podemos descartarla**, que es distinto y sigue siendo grave.

Hay un segundo camino, `audit_handlers.py:514`, que asigna
`session.sucursal_id = elegida["id_sucursal"]` — clave distinta, de otra fuente (el menú de
gestión de desvíos, construido desde `get_sucursales_con_pendientes`,
`supabase_manager.py:837`). Ese camino no crea fichas, pero la divergencia de nombre de clave
entre dos ramas del mismo campo es exactamente el tipo de cosa que una FK atrapa y la prosa
no. Sumo un detalle menor: `audit_session.py:111` documenta el formato como `# SC-001`
mientras que `HANDOFF.md:35` dice que el formato real es `SUC002`. El comentario está
desactualizado; no prueba nada sobre el runtime, pero es señal de que nadie tiene el formato
claro.

**Causa alternativa, más probable, para las fichas faltantes.** `generate_and_save_ficha`
sube el PDF a Storage **antes** de insertar la fila
(`audit_fiches_manager.py:89-93`), y si esa subida falla hace `return None` sin insertar nada.
El bucket destino es `desvio-evidencias` (`supabase_manager.py:1043-1051`), que tiene
`file_size_limit = 10485760` — 10 MB (`etapa-6-storage-mensajes.sql:59`,
`etapa-7-bot-encargado.sql:63`). Un PDF de auditoría con fotos embebidas
(`audit_fiches_manager.py:80-86` incrusta los bytes de cada foto) supera 10 MB con facilidad.
**Si el bucket rechaza el archivo, no queda ninguna fila en `audit_fiches` y el único rastro
es un `logger.warning`** (`audit_fiches_manager.py:92`). Esa hipótesis explica el síntoma tan
bien como el desajuste de IDs, y es verificable.

**Qué necesito de otras capas.** Del bot (capa W): que garantice que `session.sucursal_id`
sale siempre de `sucursales.id` y nunca de un menú con otra clave. Del front (capa F): nada —
solo consume.

**Cómo verificar cuál de las dos causas es** (una sola consulta, en el editor SQL de
Supabase, sin efectos):

```sql
-- 1) ¿Hay fichas con sucursal_id huérfano?  (si devuelve filas → contrato A roto de verdad)
SELECT af.sucursal_id, count(*) AS fichas
FROM audit_fiches af
LEFT JOIN sucursales s ON s.id = af.sucursal_id
WHERE s.id IS NULL
GROUP BY 1;

-- 2) ¿Cuántas fichas hay en total?  (si es 0 o casi → la causa es el guardado, no el ID)
SELECT count(*) AS total_fichas, min(created_at), max(created_at) FROM audit_fiches;

-- 3) ¿Cuántas sesiones de auditoría terminaron sin ficha?
SELECT count(*) FROM sesiones_auditoria WHERE estado ILIKE '%complet%';
```

Si (1) devuelve vacío y (2) devuelve un número muy por debajo de (3), la causa es el guardado
silencioso, no la identidad.

### Contrato B — Semáforo · plan de retiro

La vista SQL sobrevive. Para que pueda hacerlo **le falta cubrir cuatro cosas** que hoy
resuelve el TypeScript:

1. **Un score numérico 0-100.** La vista expone `ultimo_score`
   (`etapa-18-sucursales-dashboard.sql:59`), que es la puntuación promedio de la auditoría en
   escala 1-5. `computeBranchScore` (`api.ts:703-712`) produce otra cosa completamente
   distinta: un índice de salud derivado de conteos de desvíos. Si se retira sin reemplazo,
   la columna "puntaje" del dashboard se queda sin dato. **Decisión pendiente**: o la vista
   agrega la fórmula, o el front deja de mostrar ese número. Recomiendo lo segundo: dos
   métricas de "salud" en la misma tarjeta es parte del problema, no de la solución.
2. **Conteos por severidad.** La vista cuenta abiertos y vencidos
   (`etapa-18:38-44`) pero no `altas`, que el front usa en `resolveSemaforo`
   (`api.ts:716-722`) y en los KPIs (`api.ts:849-853`). Falta un
   `COUNT(*) FILTER (WHERE severidad = 'Alta' AND estado NOT IN ('Resuelta','Cerrada'))`.
3. **Agregación por zona.** `api.ts:797-799` y el bucle de `sucursales_estado` producen un
   corte por zona que la vista no tiene. Se resuelve con un `GROUP BY zona` sobre la propia
   vista, no hace falta lógica nueva.
4. **Totales globales del dashboard** (`total_reportes`, `tasa_cierre`, distribución de
   severidad): `api.ts:840-856`. Son agregados sobre `gestion` y `reportes` completos, no por
   sucursal. Necesitan **su propia** vista o RPC — ver E4/E6, movimiento B7.

**Plan de retiro, en tres pasos, sin ventana rota:**

- **Paso 1 (backend, sin tocar el front).** Extender `sucursales_dashboard` con la columna de
  severidad alta del punto 2 y crear `dashboard_totales` para el punto 4. `CREATE OR REPLACE
  VIEW` no rompe a los consumidores existentes mientras solo se agreguen columnas al final.
- **Paso 2 (front).** Reemplazar las llamadas de `getDashboardStats` por lecturas de las dos
  vistas y borrar `computeBranchScore`, `resolveSemaforo` e `isCriticoActivo`
  (`api.ts:698-722`). Esto lo ejecuta la capa F; yo entrego las vistas.
- **Paso 3 (Python).** Mover `determine_severity` a la base como función SQL invocable, y que
  `audit_database.py` y `main.py:978` la llamen en lugar de calcular (o hardcodear) la
  severidad. Esto elimina de paso la duplicación 1.3.

**Qué necesito del front (capa F):** que confirme si el score 0-100 se muestra en algún lado
que dirección use de verdad. Si no, se borra y el paso 1 se simplifica.
**Qué necesito del bot (capa W):** que el bot deje de derivar salud por su cuenta y consulte
la vista cuando necesite decir "esta sucursal está en rojo".

### Contrato C — Evidencia · lo confirmo desde el lado de la persistencia

No es mi capa, pero toco su consecuencia. `audit_fiches_manager.py:59-77` intenta recuperar
los bytes de cada foto en dos pasos: primero re-descarga desde Meta usando `foto.media_id`
(`:62-67`), y si eso falla usa `foto.media_url` (`:70-71`). Como la capa W documenta que
`media_url` nunca se resuelve, **el único camino que funciona es el de Meta**, que caduca a
~30 días. Pasado ese plazo, `audit_fiches_manager.py:77` loguea
`"Could not obtain bytes for photo ... skipping in PDF"` y **el PDF se genera igual, sin
fotos**. La ficha existe, tiene `fotos_count` correcto (`audit_fiches_manager.py:114`) y el
PDF está vacío de evidencia. Nadie se entera.

**Qué necesito de la capa W:** que suba los bytes a Storage en el momento de recibir el media
de WhatsApp, no en el momento de generar el PDF. Yo aporto el bucket y las policies.

### Contrato D — Desvío → gestión · funciona, con las dos grietas ya señaladas más una tercera

Confirmo las dos de cimientos §4-D: `gestion.id_reporte` es texto suelto sin FK
(`supabase_setup.sql:39`, comparar con `id_sucursal` en la línea 40 que **sí** la tiene), y
`main.py:965-1049` hace tres inserts secuenciales sin transacción.

Preciso el modo de fallo del segundo, porque el código es más frágil que "queda un reporte
huérfano": si el insert de `gestion` no devuelve datos, `main.py:1020-1022` hace `continue` y
**sigue con el próximo desvío**, dejando el `reporte` ya creado sin gestión asociada y sin
ninguna señal fuera del log. Y como `main.py:1072` devuelve
`{"status": "ok", "deviations_created": len(created_gestiones)}`, el front recibe un 200 con
un conteo menor al enviado y no tiene forma de saber cuáles fallaron.

Tercera grieta: `audit_database.py:40-194` sí propaga la excepción (`raise` en la línea 194),
pero tampoco es transaccional — si falla la gestión del tercer desvío, los dos primeros ya
están escritos y el reporte del tercero también.

**Necesito:** una función `plpgsql` (`create_desvio(...)`) que haga los tres inserts dentro
de una transacción y devuelva los IDs. Es la única forma de atomicidad con PostgREST, que no
expone transacciones multi-request.

### Contrato E — Permisos de módulo · **roto, confirmado, y con un agravante**

`main.py:135-142` define `_VALID_MODULE_PERMISSIONS` con exactamente seis entradas:
`dashboard`, `gestion_desvios`, `revision_desvios`, `mis_desvios`, `sucursales`, `admin`.
`frontend/src/lib/permissions.ts:7-16` tiene esas seis más `campanias` y `mis_campanias`.

`_normalize_module_permissions` (`main.py:173-187`) lanza
`HTTPException(400, f"Modulo invalido: {module}")` en la línea 184 ante cualquier módulo fuera
del conjunto. Se invoca desde la creación de usuarios de panel (`main.py:787`) y desde la
edición (`main.py:837`, vía `main.py:860`). Confirmado: **el módulo de campañas es
inasignable desde el panel.**

El agravante que agrego: `_normalize_module_permissions` también se invoca desde
`_profile_from_user_and_row` (`main.py:190-206`, llamada en la línea 202), que es la función
que arma el perfil que se **devuelve** en toda respuesta de usuario. Si un usuario tiene
`campanias` en su `app_metadata` —puesto a mano desde la consola de Supabase, que es la única
forma— entonces **leer ese usuario también tira 400**, no solo editarlo. El usuario queda
inaccesible desde el panel de administración.

Además hay una asimetría silenciosa en la línea 185: un módulo válido pero no permitido para
el rol se **descarta sin aviso**, mientras que un módulo desconocido tira 400. Dos
comportamientos distintos para "no podés tener esto".

**Necesito de la capa F:** ponerse de acuerdo en la lista. Mi propuesta en E6 (B6) es que la
lista deje de estar en el código de ambos lados y pase a ser una tabla en la base, servida por
un endpoint. Mientras tanto, el parche de un renglón es agregar las dos entradas faltantes a
`main.py:135-142` y a `_MODULES_BY_ROLE` (`main.py:148-152`).

---

## E4 — Falla silenciosa

Ordenado de más grave a menos.

### 4.1 `audit_fiches_manager.py:123` — el manejador de errores se rompe a sí mismo

```python
if response.data:
    logger.info(...)
else:
    logger.error(f"Failed to save ficha metadata: {response.error}")
```

`requirements.txt:20` fija `supabase==2.0.3`. En supabase-py v2 la respuesta de
`.execute()` es un `APIResponse` con atributos `data` y `count` — **no existe `.error`**; los
errores se levantan como excepción. Entonces, cuando el insert devuelve `data` vacío, la
línea 123 lanza `AttributeError` **dentro del bloque else**, que sube al `except Exception`
de la línea 128 y se registra como "Error generating/saving ficha" con un traceback que apunta
al manejador de errores en vez de al error real. Es el peor tipo de bug de observabilidad: el
código escrito para diagnosticar el problema oculta el problema.

### 4.2 `audit_database.py:206` — una consulta a una tabla que no existe

```python
response = db.client.table("reporte").select("id, sucursal_id, puntuaciones")...
```

La tabla se llama `reportes`, en plural (`supabase_setup.sql:17`, y el propio
`migration_audit_fiches.sql:2` lo aclara en un comentario: *"la tabla de reportes se llama
reportes (plural)"*). Además pide las columnas `sucursal_id` y `puntuaciones`, y `reportes`
tiene `id_sucursal` (`supabase_setup.sql:23`) y **no tiene** `puntuaciones`.

`get_previous_audit` está envuelta en `try/except` que loguea `warning` y devuelve `None`
(`audit_database.py:222-224`). O sea: **la comparación con la auditoría anterior nunca
funcionó, en ninguna ejecución, y el sistema se comporta como si simplemente no hubiera
auditoría previa.** Tres errores independientes en una sola línea, tapados por un `except`.

### 4.3 `main.py:1033` — un teléfono en una columna `uuid`

`etapa-2.sql:9` declara `actor_id uuid references auth.users(id) on delete set null`.
`main.py:1033` escribe ahí `payload.auditor_telefono` — un string tipo `"5493816199195"`.
Postgres rechaza la fila con error de tipo, `evento_response.data` viene vacío y
`main.py:1048-1049` loguea un `warning`. **Falla en el 100% de las ejecuciones** y el endpoint
devuelve 200. Resultado: los desvíos creados desde el formulario web **no tienen evento de
creación en su timeline**, y el timeline es el mecanismo de trazabilidad del sistema.

El camino del bot lo hace bien: `save_encargado_evento` (`supabase_manager.py:1149`) recibe
`actor_nombre` y no fuerza un `actor_id` (`audit_database.py:119-131`).

### 4.4 `main.py:1101-1105` — el webhook acepta mensajes sin firmar

```python
app_secret = settings.meta_app_secret
if not app_secret:
    return True  # Verification disabled
```

Si `META_APP_SECRET` no está configurado, `_verify_meta_signature` devuelve `True` para
cualquier request. `config.py:71-77` emite un warning al arrancar, pero el sistema arranca
igual. Cualquiera que conozca la URL pública puede inyectar mensajes de WhatsApp falsos y
crear desvíos, sesiones y notificaciones. **No puedo verificar si la variable está seteada en
Railway** — es un dato de entorno, no de repositorio. Es lo primero que hay que confirmar.

### 4.5 `main.py:41-47` — CORS abierto a todo internet

```python
allow_origins=["*"],
allow_credentials=False,
allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
```

`allow_credentials=False` es lo que salva la situación: sin credenciales automáticas, el
navegador no adjunta cookies, y la autenticación real va por header
`Authorization: Bearer` (`main.py:327-330`), que **sí** está sujeto a CORS. Así que el riesgo
inmediato es bajo. Pero es una configuración que solo funciona por accidente: el día que
alguien necesite cookies y ponga `allow_credentials=True`, el navegador rechaza la
combinación con `*` y —dependiendo de cómo se "arregle"— se abre un agujero real. Debe
restringirse a los orígenes de Vercel más `localhost` para desarrollo.

### 4.6 `main.py:899-900` y `916-917` — endpoints GET que mutan estado

```python
@app.api_route("/api/desvios-borrador/{draft_id}/approve", methods=["POST", "GET", "OPTIONS"])
```

`approve_desvio_borrador` convierte un borrador en gestión + reporte
(`main.py:907`, `supabase_manager.py:654-702`) y `discard_desvio_borrador` lo descarta
(`main.py:928`). Ambos aceptan `GET`.

Matizo el riesgo con precisión, porque es fácil sobrevenderlo: **no es CSRF clásico**. Ambos
llaman a `_require_admin_or_auditor` (`main.py:905`, `:926`), que exige un bearer token
(`main.py:327-330`); un `<img src="...">` desde otro sitio no lo lleva. Lo que sí puede pasar
es que un prefetch del navegador, un preview de link (Slack, WhatsApp), un crawler o un
reintento automático de la SPA aprueben un borrador que nadie quiso aprobar — cualquier cosa
que reproduzca la request con el token presente. Y la aprobación **no es reversible**: crea
gestión y reporte definitivos. Debe ser `POST` únicamente.

### 4.7 `frontend/src/lib/api.ts:833-835` — datos demo cuando la base está vacía

```typescript
if (reportes.length === 0 && gestiones.length === 0 && sucursalesRows.length === 0) {
  return getDemoData();
}
```

`getDemoData` (`api.ts:726-...`) devuelve 48 reportes, 12 desvíos y tres zonas inventadas
(`api.ts:797-799`). Es capa de front, pero el modo de fallo es de datos y le pega de lleno a
la confiabilidad: **si la sesión pierde permisos y las tres consultas vuelven vacías, el
dashboard muestra números falsos sin ninguna marca visual de que son falsos.** Dirección no
tiene forma de distinguir "no hay datos" de "hay 48 reportes". Lo señalo acá para que quede en
el registro conjunto; la ejecución es de la capa F.

### 4.8 Los `except` que devuelven listas vacías

`AuditFichesManager.get_fiches` devuelve `[]` ante cualquier excepción
(`audit_fiches_manager.py:159-161`), igual que `get_sucursales_with_fiches`
(`audit_fiches_manager.py:170-172`). En `supabase_manager.py` el patrón se repite en
`get_all_sucursales` (`:220-225`), `get_all_auditores`, `get_overdue_gestiones` (`:875-877`) y
una docena más. Cada uno individualmente es defendible; en conjunto significan que **una caída
de Supabase se presenta como "no hay nada" en vez de como un error.** El semáforo se pone en
verde, el panel Hoy se vacía y nadie recibe una alerta.

### 4.9 Los tests no prueban lo que dicen probar

`test_architecture_merge.py:75` verifica una tabla llamada `'gestiones'` — que no existe; la
real es `gestion` (`supabase_setup.sql:37`). Y la consulta usa
`where={'id': {'gte': 0}}` (`test_architecture_merge.py:81`) contra tablas cuyo `id` es
`text`. Además todos los `test_*` de ese archivo son funciones que **devuelven `bool` e
imprimen**, sin un solo `assert`: no son tests de pytest, son un script. Si falta
`SUPABASE_URL` imprime `[SKIP]` y devuelve `False` (`test_architecture_merge.py:66-68`), que
en un runner ingenuo se cuenta como resultado, no como falla.

`test_audit_database.py:20,43` sí testea `determine_severity` de verdad, pero solo eso — la
lógica pura, no el guardado.

---

## E5 — Superficie a borrar

Verifiqué uso real antes de proponer cada borrado.

| Qué | Evidencia de que no se usa | Recomendación |
|---|---|---|
| `frontend/docs/sql/etapa-12-desvios-auditoria-perfumeria.sql` | No compila (`:72`, `:82`); depende de `maestro_auditores`, sin DDL; la tabla es "término muerto" por cimientos §3 | **Borrar el archivo entero.** Si la tabla llegó a existir en Supabase, un `DROP TABLE` explícito en la migración inicial |
| `frontend/docs/sql/etapa-7-bot-encargado.sql` | Duplica `etapa-6` casi línea por línea y **relaja** sus policies de Storage (`etapa-7:77-80` vs `etapa-6:73-77`) | **Borrar**, y re-aplicar la versión de la etapa 6 |
| `sheets.py` (41 KB) + `setup_sheets.py` + `create_sheets.py` + `sync_sheets_to_supabase.py` | El único uso programado está comentado (`main.py:474-480`: *"Disabled: Using Supabase directly"*), igual que el endpoint `/sync-now` (`main.py:1079-1083`) | **Verificar `get_sheets()` primero** — se invoca en `main.py:907` y `:928`, así que el módulo NO está muerto del todo. Borrar solo los scripts de setup y el sync |
| `gspread`, `google-auth-oauthlib`, `google-auth`, `google-auth-httplib2`, `google-api-python-client` (`requirements.txt:8-12`) | Dependen de lo anterior | Borrar **después** de resolver `get_sheets()` |
| `twilio==8.10.0` (`requirements.txt:19`) | Cero importaciones de `twilio` en el repo; el canal WhatsApp es Meta Cloud API (`meta_client.py`) | **Borrar** |
| `playwright==1.40.0` (`requirements.txt:7`) | No hay importaciones en el backend; el uso es del front (HANDOFF.md:31) | **Borrar de `requirements.txt` del backend** — instala ~400 MB de navegadores en cada build de Railway |
| `qrcode==7.4.2` (`requirements.txt:5`) | Verificar importaciones antes de tocarlo | Verificar |
| `init_supabase.py` completo | Su rama de creación (`:29-38`) llama a un RPC `exec_sql` que no está definido en ningún SQL del repo; su rama de verificación solo loguea | **Reemplazar** por el runner de migraciones (B1), no borrar sin sustituto |
| `test_architecture_merge.py` | Ver 4.9: sin asserts, apunta a una tabla inexistente | **Reescribir o borrar.** Un test que no puede fallar es peor que ninguno |
| `sql_diagnostico.sql` | Consulta ad-hoc de una sesión de debug; referencia `respuesta_pregunta.telefono_auditor` y `mensajes_json` (`:2`), columnas sin DDL en el repo | Borrar |
| `analisis_auditoria` (la tabla, no el archivo) | Cero referencias en `.py`/`.ts`/`.tsx` | **No borrar — usar.** Es el destino correcto del movimiento B8 |

---

## E6 — Propuesta

Ocho movimientos. Los tres primeros son secuenciales y desbloquean el resto.

### B1 — Baseline del esquema + runner de migraciones

**El movimiento fundacional.** Sin esto, ninguno de los otros siete se puede probar antes de
producción.

*Paso 1 — capturar la verdad.* Sobre la instancia real de Supabase:

```bash
pg_dump --schema-only --no-owner --no-privileges \
  --schema=public "$SUPABASE_DB_URL" > db/migrations/0000_baseline.sql
```

Esto convierte en texto versionado las siete tablas sin DDL de E2.1, más las policies que de
verdad quedaron aplicadas tras el desorden de etapas 6/7/8/12. Es la única forma honesta de
resolver la ambigüedad, porque el repo ya no sabe cuál es el estado.

*Paso 2 — el runner.* Recomiendo **`sqlx-cli`** o **`dbmate`** por sobre Alembic: son binarios
únicos que ejecutan SQL plano, sin ORM, sin modelos Python que mantener sincronizados, y el
proyecto ya escribe SQL a mano. Ambos crean una tabla `schema_migrations` y aplican en orden
lo que falte.

*Paso 3 — reordenar las etapas existentes* como migraciones numeradas después del baseline,
descartando `etapa-7` y `etapa-12` (E5), y envolviendo cada una en `BEGIN; ... COMMIT;`.

*Paso 4 — cerrar la puerta.* Regla de equipo: **ningún `ALTER TABLE` se corre en el editor SQL
de Supabase.** El comando de deploy de Railway ejecuta `dbmate up` antes de arrancar uvicorn.

*Paso 5 — un chequeo de arranque que sirva.* Reemplazar `init_supabase.py` por una
verificación de que `schema_migrations` tiene la última versión esperada; si no, **fallar el
arranque** en lugar de loguear un error y seguir (`init_supabase.py:62`).

**Costo estimado:** un día. **Riesgo:** bajo — el baseline no modifica nada, solo lee.

### B2 — Resolver el drift de `audit_fiches` (contrato A)

Depende de B1. Dos cosas que hoy no puedo separar:

**(a) ¿Existen las columnas `score_*`?** `analysis_agents.py:107` hace
`.select("...,score_limpieza,score_stock,score_ofertas,score_burbujas,total_desvios")` sobre
una tabla cuyo `CREATE TABLE` (`migration_audit_fiches.sql:5-21`) define
`desvios_count`, `fotos_count` y `puntuacion_promedio` — y **ninguna** de esas seis. Grepeé
todos los `.sql` del repo: la única aparición de `score_limpieza` está en `analysis_agents.py`
y en tres páginas del front (`AuditFichesGallery.tsx:26,35`, `SucursalDetail.tsx:32,43`,
`Dashboard.tsx:42`). **No hay ningún `ALTER TABLE audit_fiches ADD COLUMN` en el repositorio.**

Hay exactamente dos escenarios posibles y llevan a diagnósticos opuestos:

- **Si las columnas NO existen en Supabase:** PostgREST responde 400 a un `select` que nombra
  una columna inexistente, y esa excepción sube sin `try/except` desde `_fetch`
  (`analysis_agents.py:105-113`) hasta el `except` del endpoint (`main.py:1836`). Entonces
  **`POST /api/analisis/ficha/{id}` devuelve 500 siempre** y el módulo de análisis nunca
  funcionó. Lo mismo con `Dashboard.tsx:42`, que también nombra `total_desvios` explícitamente.
- **Si SÍ existen** (agregadas a mano en la consola, sin quedar en el repo): las consultas
  pasan, pero `audit_fiches_manager.py:113-115` solo escribe `desvios_count`, `fotos_count` y
  `puntuacion_promedio`. Las seis columnas quedan en `NULL` para toda ficha, y los cinco
  agentes de IA reciben `None` en cada score (`analysis_agents.py:139-143`,
  `:179-183`, `:270`). El prompt le llega a Claude como
  `"Limpieza: None | Stock: None | Ofertas: None"` y **el modelo produce un diagnóstico
  confiadamente construido sobre nada.** Es peor que el 500: falla en silencio, con salida
  plausible.

**No puedo determinar cuál es sin la base viva.** Verificación:

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'audit_fiches'
ORDER BY ordinal_position;
```

**(b) La FK ausente y la causa de las fichas faltantes.** Correr el diagnóstico de tres
consultas del contrato A (sección E3). Según el resultado:

- Si hay `sucursal_id` huérfanos → limpiar y agregar
  `ALTER TABLE audit_fiches ADD CONSTRAINT fk_audit_fiches_sucursal FOREIGN KEY (sucursal_id) REFERENCES sucursales(id);`
- Si `audit_fiches` está casi vacía → el problema es el `return None` de
  `audit_fiches_manager.py:93`. Arreglo: **insertar la fila de metadatos ANTES de subir el
  PDF**, con `url_pdf` nulo, y actualizarla después. Así una falla de Storage cuesta el PDF,
  no la ficha entera ni el semáforo.

En cualquier caso la FK se agrega, porque su función es impedir que el problema vuelva.

**Sobre las columnas:** unificar en un solo juego de nombres. Recomiendo conservar
`desvios_count`/`fotos_count`/`puntuacion_promedio` (los que el código *escribe*) y agregar
las cuatro `score_*` reales, que sí faltan y sí tienen sentido — el bot ya tiene los cuatro
scores de bloque en `session.bloques` (`audit_fiches_manager.py:97`) y hoy los promedia y
descarta el detalle. Actualizar `analysis_agents.py` y las tres páginas del front a los
nombres canónicos.

### B3 — Transacción para desvío → gestión (contrato D)

Una función `plpgsql` `crear_desvio(...)` que haga los tres inserts (`reportes`, `gestion`,
`desvio_eventos`) en una transacción y devuelva `(id_reporte, id_gestion)`. PostgREST no
expone transacciones entre requests, así que es la única opción real. Reemplaza los tres
caminos duplicados de E1.3 (`main.py:965-1049`, `audit_database.py:79-131`,
`supabase_manager.py:486-570`) por una llamada a `db.client.rpc("crear_desvio", {...})`.

De paso arregla dos cosas: `main.py:1033` deja de mandar un teléfono al `actor_id uuid` (la
función lo recibe como `actor_nombre` y deja `actor_id` en `NULL`), y la severidad se calcula
en un solo lugar en vez de estar hardcodeada en `main.py:978`.

Agregar también la FK faltante:
`ALTER TABLE gestion ADD CONSTRAINT fk_gestion_reporte FOREIGN KEY (id_reporte) REFERENCES reportes(id);`
— previo chequeo de huérfanos.

### B4 — Unificar la definición de "vencida"

Elimina la duplicación de E1.2. Tres partes:

1. Corregir `get_overdue_gestiones` (`supabase_manager.py:866,871`) para comparar contra la
   fecha argentina, no contra `now()` UTC. Sin esto, todo desvío se vence 3 horas antes de
   tiempo — y en la práctica, un día antes.
2. Que el job (`main.py:1539-1579`) y la vista (`etapa-18:41-44`) usen **la misma expresión
   SQL**, idealmente vía una función `es_vencida(estado, plazo_fecha)` invocada por ambos.
3. Que el front deje de calcularlo (`api.ts:844`, `:880`) y lea la columna de la vista.
   Depende de la capa F.

Decisión de negocio pendiente: `get_overdue_gestiones` (`supabase_manager.py:870`) marca
`Vencida` también a las gestiones en `En_revision`, o sea las que están esperando **al
auditor**. Penalizar a la sucursal por la demora del auditor probablemente no es lo que se
quiere; hay un mecanismo aparte para eso (`get_gestiones_en_revision_stale`,
`supabase_manager.py:879`).

### B5 — Seguridad: policy de rol, CORS y verbos HTTP

Tres arreglos independientes, todos chicos:

**(a) La policy anti-escalado de rol no existe.**
`supabase_setup.sql:194-199` usa `new.role` y `old.role` dentro de una `CREATE POLICY`:

```sql
create policy "profiles_role_protected" on profiles for update
  using (true)
  with check ((new.role = old.role) or (exists (...)));
```

`NEW` y `OLD` son variables de **trigger**, no de policy. En el contexto de una policy la
única referencia válida es el nombre de la tabla. Postgres rechaza esto con
`missing FROM-clause entry for table "new"`, así que **la policy nunca se creó**.

La consecuencia se combina con `etapa-4-roles-responsables.sql:53-55`, que redefine
`profiles_admin_update` **solo con `USING` y sin `WITH CHECK`**. En Postgres, una policy de
`UPDATE` sin `WITH CHECK` usa la expresión de `USING` para validar la fila nueva. Como esa
expresión pregunta si *quien ejecuta* es admin, y no dice nada sobre el valor de `role`, un
admin puede cambiar roles (correcto) — pero **no hay ninguna policy que impida a un usuario
no-admin escalar su propio rol si alguna otra policy le permite un `UPDATE` sobre su fila.**
`supabase_setup.sql:185` le da `SELECT` sobre su propio perfil, no `UPDATE`, así que hoy el
riesgo está contenido por omisión, no por diseño.

El reemplazo correcto es un **trigger**, que es donde `NEW`/`OLD` sí existen:

```sql
CREATE OR REPLACE FUNCTION prevent_role_escalation() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  IF NEW.role IS DISTINCT FROM OLD.role
     AND NOT EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin')
  THEN RAISE EXCEPTION 'No autorizado a cambiar el rol';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER profiles_role_protected BEFORE UPDATE ON profiles
FOR EACH ROW EXECUTE FUNCTION prevent_role_escalation();
```

**Verificar primero si la policy existe:**
`SELECT polname FROM pg_policy WHERE polrelid = 'profiles'::regclass;` — si
`profiles_role_protected` no aparece, se confirma que el `CREATE POLICY` falló.

**(b) CORS.** Reemplazar `allow_origins=["*"]` (`main.py:43`) por la lista explícita de
orígenes de Vercel más `http://localhost:5173`. Sacar `GET` de `allow_methods`
(`main.py:45`) una vez hecho (c).

**(c) Verbos.** `main.py:899-900` y `916-917`: dejar solo `["POST", "OPTIONS"]`. Requiere que
la capa F ajuste las llamadas correspondientes.

**(d) `META_APP_SECRET`.** Confirmar que está seteado en Railway y considerar hacerlo
obligatorio en `config.py:63-67` en vez de solo warnear (`config.py:71-77`).

### B6 — Fuente única para los permisos de módulo (contrato E)

*Parche inmediato (5 minutos):* agregar `campanias` y `mis_campanias` a
`_VALID_MODULE_PERMISSIONS` (`main.py:135-142`) y a las entradas de rol correspondientes en
`_MODULES_BY_ROLE` (`main.py:148-152`). Desbloquea el módulo de campañas hoy.

*Arreglo estructural:* una tabla `modulos_panel (clave text primary key, nombre text, roles text[])`
servida por `GET /api/modulos`. El front deja de tener la lista en
`frontend/src/lib/permissions.ts:7-16` y el backend la lee de la base. Agregar un módulo pasa a
ser un `INSERT`, no un deploy coordinado de dos repositorios.

*Y un arreglo defensivo:* que `_normalize_module_permissions` **no lance 400 al leer** — solo
al escribir. Hoy `_profile_from_user_and_row` (`main.py:202`) la usa para armar la respuesta,
y un valor viejo en `app_metadata` vuelve al usuario inaccesible desde el panel (ver E3-E). En
lectura debería ignorar lo desconocido y loguear.

### B7 — Vistas y RPC para el dashboard (performance)

`getDashboardStats` (`frontend/src/lib/api.ts:805-830`) hace
`supabase.from('reportes').select('*')` y `supabase.from('gestion').select('*')` **sin
límite**, y agrega todo en el navegador (`api.ts:840-895`). Con 25 sucursales el volumen aún
es tolerable; con dos años de operación son decenas de miles de filas viajando por la red en
cada carga de pantalla, para producir una docena de números.

Lo que hace falta del lado SQL:

- **`dashboard_totales`** — vista con `total_reportes`, `total_desvios`, conteos por estado,
  `tasa_cierre`, `criticos_activos`, `criticos_vencidos` y la distribución de severidad. Todo
  lo que hoy calculan `api.ts:840-856`.
- **`dashboard_por_zona`** — `GROUP BY zona` sobre `sucursales_dashboard`, reemplazando el
  bucle de `api.ts:858-895`.
- **Extender `sucursales_dashboard`** con el conteo de severidad `Alta` que hoy falta (ver
  contrato B, punto 2).

Índices ausentes que valen la pena, todos verificables contra `pg_indexes`:

| Índice | Por qué | Hoy |
|---|---|---|
| `gestion(plazo_fecha)` o `gestion(estado, plazo_fecha)` | `get_overdue_gestiones` (`supabase_manager.py:867-872`) hace un scan cada 15 minutos (`main.py:432-438`) | Solo hay `idx_gestion_estado` (`supabase_setup.sql:103`) y `idx_gestion_sucursal_bloque_estado` (`etapa-13:38-39`) |
| `gestion(id_reporte)` | El join de `etapa-13:14-19` y todo lookup reporte→gestión | No existe |
| `reportes(created_at)` / `gestion(created_at)` | `analysis_agents.py:95-99` filtra por rango de `created_at` | No existen |
| FK `gestion.id_reporte → reportes.id` | Integridad, y Postgres no indexa FKs automáticamente | No existe (`supabase_setup.sql:39`) |

### B8 — Persistir el análisis multi-agente

La tabla ya existe (`etapa-17-analisis-agentes.sql:5-21`) con el índice único por `ficha_id`
que hace falta (`:24-25`). Solo hay que escribir en ella.

Al final de `analizar` (`analysis_agents.py:341-348`), antes del `return`, un `upsert` sobre
`analisis_auditoria` con `on_conflict="ficha_id"`. Y al principio de la función, un `select`
por `ficha_id`: si ya hay análisis, devolverlo sin llamar a Claude. Un parámetro
`forzar: bool = False` en el endpoint (`main.py:1819`) permite regenerarlo a pedido.

Ahorro: seis llamadas a Claude por cada consulta repetida de la misma ficha. Ganancia
adicional, y probablemente más valiosa: el análisis queda como registro histórico auditable,
que es para lo que se construyó la tabla.

**Detalle a arreglar en el mismo movimiento:** `analysis_agents.py:335-337` ya tiene una
guarda decente —si *todos* los agentes fallaron, no sintetiza sobre basura— pero no cubre el
caso de que fallen cuatro de cinco. Y el resultado con `"error"` igual se devolvería al front
como éxito parcial. Si se va a persistir, conviene no persistir análisis degradados: marcar la
fila con un campo de calidad o directamente no escribirla.

---

## Tabla de movimientos

| ID | Movimiento | Impacto | Esfuerzo | Riesgo | Depende de |
|----|-----------|---------|----------|--------|------------|
| B1 | Baseline `pg_dump` del esquema real + runner de migraciones (`dbmate`/`sqlx`), reordenar etapas, prohibir SQL manual | Alto | Medio | Bajo | — |
| B2 | Resolver drift de `audit_fiches`: verificar columnas `score_*`, unificar nombres, agregar FK a `sucursales`, invertir el orden insert/upload de la ficha | Alto | Medio | Medio | B1 |
| B3 | Función `crear_desvio` transaccional (reporte+gestión+evento), FK `gestion.id_reporte`, elimina los 3 caminos duplicados y el `actor_id` inválido | Alto | Medio | Medio | B1, W— |
| B4 | Unificar "vencida": corregir zona horaria en `get_overdue_gestiones`, una sola expresión SQL compartida por job y vista | Alto | Bajo | Bajo | B1, F2 |
| B5 | Seguridad: trigger anti-escalado de rol (la policy nunca se creó), CORS restringido, quitar `GET` de approve/discard, exigir `META_APP_SECRET` | Alto | Bajo | Bajo | B1, F— |
| B6 | Permisos de módulo: parche inmediato de 2 entradas + tabla `modulos_panel` como fuente única + no fallar en lectura | Medio | Bajo | Bajo | F— |
| B7 | Vistas `dashboard_totales` y `dashboard_por_zona`, columna de severidad Alta en `sucursales_dashboard`, índices en `gestion` y `reportes` | Medio | Medio | Bajo | B1, F2 |
| B8 | Persistir el análisis multi-agente en `analisis_auditoria` con caché por `ficha_id` y regeneración explícita | Medio | Bajo | Bajo | B2 |

**Orden sugerido:** B1 → B5 (seguridad, no espera) → B2 → B4 → B3 → B6 → B7 → B8.

**Dependencias hacia otras capas.** Las marco con `—` cuando necesito una confirmación más que
un desarrollo:

- **Hacia W (WhatsApp):** B3 necesita que el bot llame a `crear_desvio` en lugar de armar los
  inserts a mano. B2 necesita confirmación de que `session.sucursal_id` sale siempre de
  `sucursales.id` (`audit_handlers.py:942`) y nunca del otro camino
  (`audit_handlers.py:514`).
- **Hacia F (Frontend):** B4 y B7 requieren que el front deje de agregar en el navegador y lea
  las vistas — es el paso 2 del plan de retiro del contrato B. B5(c) requiere que las llamadas
  a approve/discard usen `POST`. B6 requiere acordar la lista de módulos.
- **Pregunta abierta para F:** ¿el score 0-100 de `computeBranchScore` (`api.ts:703`) se
  muestra en alguna pantalla que dirección use? Si no, se borra sin reemplazo y B7 se
  simplifica.

---

## Anexo: qué verificar en Supabase antes de ejecutar nada

Cinco consultas, todas de solo lectura, que resuelven las incógnitas de este informe:

```sql
-- 1. ¿Existen las columnas score_* en audit_fiches?  (decide el escenario de B2)
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'audit_fiches' ORDER BY ordinal_position;

-- 2. ¿Se creó la policy anti-escalado de rol?  (esperado: NO aparece)
SELECT polname FROM pg_policy WHERE polrelid = 'profiles'::regclass;

-- 3. ¿Hay fichas con sucursal_id huérfano?  (decide la causa del contrato A)
SELECT af.sucursal_id, count(*) FROM audit_fiches af
LEFT JOIN sucursales s ON s.id = af.sucursal_id
WHERE s.id IS NULL GROUP BY 1;

-- 4. ¿Cuántas fichas hay, y cuántas sesiones completadas?  (guardado silencioso)
SELECT (SELECT count(*) FROM audit_fiches) AS fichas,
       (SELECT count(*) FROM sesiones_auditoria) AS sesiones;

-- 5. ¿Qué tablas existen realmente?  (la brecha entre el repo y la realidad)
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1;
```

La consulta 5 es la más importante de las cinco: su resultado, comparado con el inventario de
E2.1, es la medida exacta de cuánto esquema vive solo en Supabase. Ese número es el que B1
tiene que llevar a cero.

# Handoff — Estado del proyecto

_Última sesión: 2026-08-11. Todo pusheado a `origin/master`._

---

## La decisión que ordena todo lo demás

**WhatsApp es EL canal de captura.** El auditor y el encargado viven en WhatsApp; la app web es
**panel de lectura y gestión** para dirección.

Esto no es un detalle de implementación: reencuadra qué vale la pena construir. La ergonomía de captura la da
WhatsApp, así que todo trabajo sobre pantallas de carga en el navegador quedó descartado. El formulario web de
auditoría (`AuditPerfumeriaV2`) **ya se borró**.

El otro norte de esta etapa fue **coherencia y confiabilidad, no features**. El diagnóstico completo está en
[`docs/analisis/`](docs/analisis/) — arrancá por [`04-roadmap.md`](docs/analisis/04-roadmap.md), que tiene los
20 movimientos priorizados, las dependencias entre capas, y lo que se decidió **no** hacer.

---

## ⚠️ Primer paso al retomar

1. **¿Se aprobó la plantilla `farmaaudit_novedades` en Meta?** Se envió a revisión el **2026-08-11**. Es lo que
   destraba el bloque 4 del panel de desvíos (ver más abajo). Chequealo en Meta Business Manager.
   - De paso, verificá si **`campana_nueva_sucursal`** llegó a aprobarse alguna vez. El código la usa
     (`main.py:745`) y loguea *"probablemente el template no está aprobado aún"* cuando falla. Si esa nunca
     pasó, el trámite de plantillas es una incógnita más grande de lo que parece.
2. ~~Verificación manual pendiente en el navegador.~~ **Hecha 2026-08-11.** `/campanias`, `/mis-campanias`,
   `/desvios` y detalle de sucursal andan bien en navegación normal (SPA). Se encontró y arregló un bug real:
   ver "Sesión no sobrevivía una recarga dura" más abajo.
3. **`META_APP_SECRET` en Railway.** Sin esa variable el webhook acepta mensajes **sin verificar la firma de
   Meta**, o sea que cualquiera que conozca la URL puede inyectar mensajes falsos al bot. El backend lo avisa
   por log al arrancar. Con WhatsApp como único canal, es el agujero más serio que queda abierto.
4. **`etapa-16-campania-sucursal-rls.sql`** sigue sin correr. Sin ella, `/mis-campanias` devuelve 0 filas para
   el rol `sucursal` por RLS. Solo importa si vas a tocar campañas.
5. ~~`SUPABASE_SERVICE_KEY` legacy deshabilitada.~~ **Resuelto y verificado 2026-08-11** (`3414155`), y fue más
   grave de lo que parecía al principio — **Railway estaba caído**, no solo el `.env` local. Deploy
   `8eae4a0e` confirmado activo y sano: todas las queries a Supabase en 200 OK, sin `Invalid API key`. Detalle
   en "Supabase cortó las keys legacy — Railway estuvo caído" más abajo.
6. ~~Confirmar la URL del webhook en Meta Developers.~~ **Resuelto y verificado 2026-08-11.** Se actualizó el
   Callback URL a `https://farmaaudit-production.up.railway.app/webhook` (la vieja tenía el sufijo `-3f78`,
   corregido también en `META_SETUP.md`) y se probó con un mensaje real: el bot respondió. Con esto el
   incidente de la key legacy de Supabase queda cerrado de punta a punta — webhook, Railway, Supabase, todo
   verificado con tráfico real, no solo con curl.

---

## Qué se hizo en la etapa 2026-08-11 (verificación en navegador)

**Sesión no sobrevivía una recarga dura** (`1be5607`) — con login real (no dev bypass), cualquier F5, URL
directa o pestaña nueva colgaba 15-20s en "Verificando sesión..." → "Cargando perfil..." y terminaba en "No se
pudo cargar tu perfil", en **todas** las rutas protegidas. 100% reproducible con tests espaciados.

Causa: `main.tsx` usa `<StrictMode>`, que en dev invoca los effects de `useAuth` dos veces. Cada invocación
llama `getSession()`, serializado por defecto vía Web Locks API (`navigatorLock` de supabase-js) con su propio
ciclo de acquire/steal-timeout de 5s. La duplicación acumulaba más de los 15s de `PROFILE_LOAD_TIMEOUT_MS`.

Fix en `frontend/src/lib/supabase.ts`: `lock: processLock` en vez de `navigatorLock` — lock en memoria del
mismo proceso, sin la sobrecarga de Web Locks. Este panel no necesita coordinar sesión entre pestañas.
Verificado con 3 corridas limpias antes/después: fallaba consistentemente a los 15s sin el fix, carga en <5s
con él.

**Pendiente relacionado, no tocado**: `loadProfileWithRetry` en `useAuth.ts` no reintenta cuando gana la
carrera el timeout interno (`Promise.race` resuelve `null` sin lanzar, así que `MAX_PROFILE_RETRIES` no se
ejecuta en ese path). Con el fix de arriba no debería activarse en la práctica, pero es un gap real si vuelve
a aparecer latencia.

**Bloque 2 del panel de desvíos — ficha como contenedor** (`1987001`)

- `gestion.ficha_id → audit_fiches(id)` (`etapa-22-gestion-ficha-id.sql`, **ya corrida**). Se puebla en
  `audit_fiches_manager.generate_and_save_ficha` justo después de crear la ficha — no por heurística. Las
  gestiones históricas quedan en `null` a propósito, sin backfill.
- `save_audit_to_database` (`audit_database.py`) devolvía solo el primer `gestion_id` de la sesión y
  descartaba el resto; ahora devuelve todos, y `audit_handlers.py` los guarda en
  `session.pending_ficha_gestion_ids` para que la ficha los linkee al crearse.
- `DesvioDetail` muestra de qué auditoría salió el desvío (o "Auditoría no vinculada"); el modal de una ficha
  en `/auditorias` muestra sus desvíos con progreso "X de Y resueltos" y linkea a cada uno. Soporta deep-link
  `/auditorias?ficha=<id>`.
- De paso, `analysis_agents.py` dejó de adivinar las gestiones de una ficha por fecha+sucursal (la heurística
  que este mismo bloque vino a evitar) y usa `ficha_id` directo, con la heurística vieja como fallback solo
  para fichas históricas sin el campo poblado.
- Verificado en navegador: el caso sin ficha vinculada renderiza bien. El caso **con** ficha vinculada no se
  pudo probar visualmente esta sesión — no hay todavía ninguna gestión real con `ficha_id` poblado (recién se
  puebla en la próxima auditoría completa por WhatsApp) y escribir un valor de prueba directo en producción
  quedó bloqueado por el sandbox. Vale la pena confirmarlo en la próxima auditoría de punta a punta.

**Bloque 3 del panel de desvíos — identidad viva del responsable + estado de entrega** (`0cf8e65`)

- `usuarios_whatsapp.ultimo_mensaje_entrante_at` (`etapa-23-mensajeria-en-vivo.sql`, **ya corrida**), que el
  webhook actualiza en cada mensaje entrante de un usuario conocido — un solo update no bloqueante, en el
  punto donde `main.py` ya resuelve identidad. Es la base para saber si la ventana de 24h de Meta está abierta.
- **Hallazgo que cambió el plan**: `usuarios_whatsapp` no tenía nada que impidiera dos responsables activos
  para la misma sucursal — "el" responsable no estaba bien definido. La misma migración agrega un índice único
  parcial (`id_sucursal` donde `rol='responsable_sucursal' and activo`); verificado antes contra producción
  que no había duplicados.
- `identity.resolve_responsable_by_sucursal()`: la resolución inversa a `resolve_whatsapp_user`, sucursal →
  responsable activo. La usan el job de recordatorio (que ahora agrupa por `id_sucursal`, no por teléfono
  congelado) y el endpoint nuevo `GET /api/gestion/{id}/responsable-activo`.
- El frontend no puede leer `usuarios_whatsapp` directo — RLS admin-only, pero lo necesita también el rol
  `auditor` — de ahí el endpoint nuevo, que hace de puente con el cliente service-role del backend.
- `DesvioResponsibleCard`, el link de WhatsApp y los botones "Contactar responsable"/"Notificar encargado"
  (en `DesvioDetail` y en la lista de `DesviosGestion`) dejan de leer `gestion.tel_responsable` y resuelven en
  vivo. Sin responsable activo, dice explícitamente "Sin responsable activo" con link a Administración →
  Usuarios WhatsApp, en vez de fallar en silencio.
- Mitad "mostrar" de "estado de entrega visible": `ChatMensajes` ya sabe renderizar un badge de
  `desvio_eventos.metadata.entrega` (enviado/fallido/sin ventana) — capacidad muerta hasta que el Bloque 4
  empiece a escribir ese campo al enviar.
- Verificado de punta a punta contra Supabase real (ver incidente abajo): el endpoint nuevo devuelve el
  responsable correcto tanto para una sucursal sin responsable activo (`{"responsable": null, ...}`) como para
  una con responsable activo (`{"responsable": {"nombre": "juan", "telefono": "549..."}, "ventana_abierta":
  false}`). `ventana_abierta` da `false` en todos los casos todavía porque `ultimo_mensaje_entrante_at` nunca
  se pobló con tráfico real — falta esa prueba, no se puede simular sin riesgo desde acá.

### Supabase cortó las keys legacy — Railway estuvo caído (`3414155`)

Lo que en la sesión anterior parecía "solo el `.env` local desincronizado" resultó ser más grave: **Railway
también estaba corriendo con la key legacy**, y al rotarla a la nueva (`sb_secret_...`) el deploy quedó roto
con `supabase.client.SupabaseException: Invalid API key` — un error distinto y más duro que el 401 original.
Con eso, el backend arrancaba pero **no podía hablar con Supabase para nada**: ni el webhook, ni los jobs de
fondo, ni ningún endpoint autenticado.

Causa real: `supabase-py==2.0.3` (la versión pineada en `requirements.txt` desde siempre) valida la key con
una regex que exige forma de JWT (`algo.algo.algo`) **antes de mandar cualquier request** — rechaza el formato
nuevo de Supabase en el cliente, ni siquiera llega a la red. No alcanzaba con cambiar la key: hacía falta
actualizar la librería.

Fix: `supabase` `2.0.3` → `2.31.0`, más `httpx<0.25.0` → `httpx>=0.26,<0.29` (la dependencia interna
`supabase-auth` de la versión nueva lo exige; `anthropic` y `openai` declaran `httpx<1,>=0.23`, así que el
rango más ancho no choca con ellos). Verificado localmente con la key nueva: arranque limpio, sin errores de
Supabase, y el endpoint de responsable-activo del Bloque 3 devolviendo datos reales.

**Confirmado en vivo, de punta a punta**: deploy `8eae4a0e` (`farmaaudit-production.up.railway.app`) activo,
logs limpios, todas las queries a Supabase en 200 OK, `/health` sano desde afuera. Meta Developers apuntaba a
la URL vieja (`-3f78`) — se corrigió el Callback URL, y se probó con un mensaje real de WhatsApp: **el bot
respondió**. Incidente cerrado del todo, sin cabos sueltos.

---

## Qué se hizo en la etapa 2026-08-10/11

**Módulo de identidad y sucursales** (`etapa-21`, **ya corrida y verificada en Supabase**)

- Tabla nueva `usuarios_whatsapp` como **fuente única** de "quién es este teléfono y qué puede hacer".
  Reemplaza los tres lugares que guardaban el mismo dato sin hablarse: `auditores.telefono`,
  `profiles.telefono` y `sucursales.tel_responsable`.
- Catálogo `tipos_auditoria` + `usuario_tipos_auditoria`: sumar el próximo rol (auditor de venta de
  medicamentos al público) es **un INSERT**, no una migración de esquema.
- `sucursales.activo`: baja lógica. Archivar una sucursal la saca del menú del bot y de los selectores sin
  romper las seis tablas que le apuntan con FK. El borrado real fallaba siempre.
- `identity.py` con `resolve_whatsapp_user()`. `get_auditor` y `get_encargado_by_phone` quedaron como
  envoltorios finos, así que los ~13 call sites de `router.py` no se tocaron.
- **Se cerró un bypass de autorización**: `main.py` procesaba el mensaje sin verificar identidad si el teléfono
  tenía una fila en `sesiones_whatsapp`. Bastaba con haber iniciado una auditoría alguna vez.
- `/admin` reconstruido en cuatro pestañas por query param, con sub-componentes en `components/admin/`.

**Panel de desvíos, bloque 1** — bandejas por turno (ver la sección del plan, arriba).

**Lint del frontend: 31 errores → 0**, sin un solo `eslint-disable`. Todo reestructuración real. De arrastre
aparecieron dos bugs: `Checkbox` aceptaba `className` y lo descartaba, y `ChatMensajes` pasaba un evento de
teclado donde se esperaba uno de formulario (`as any`). Además, todas las cargas de datos ganaron **guarda de
cancelación**, que no tenían: salir de una página a mitad de carga escribía estado sobre un componente
desmontado.

---

## Qué se hizo en la etapa anterior (2026-08-06)

### El diagnóstico

Tres especialistas (WhatsApp, backend, frontend) analizaron el código con la misma rejilla y cinco contratos
entre capas, para que sus propuestas se sumaran en vez de chocar.

**El hallazgo de fondo: el sistema no falla, degrada.** Casi ningún defecto emitía un error; producían un
resultado plausible y equivocado.

### Lo que se ejecutó

**Datos honestos** (`ec7d038`)

- El dashboard **inventaba datos** cuando las queries volvían vacías, y "vacía" era indistinguible de "sin
  permisos" o "mal configurado". Nada leía el flag `isDemoData`, así que se mostraba sin ningún indicador.
  Borrado.
- La galería y el detalle de sucursal mostraban **cero desvíos en verde** para auditorías que sí los tenían: la
  base guarda `desvios_count` y el código leía `total_desvios`. Con `select('*')` eso llega como `undefined` y
  `undefined > 0` es falso.
- El endpoint de análisis multi-agente **estaba caído**, no corriendo a ciegas: pedía columnas `score_*`
  inexistentes y PostgREST devuelve 400.

**Retiro de la captura web** (`ec7d038`)

Se borraron `AuditPerfumeriaV2` + 6 componentes + el hook de audio + la ruta + el endpoint
`POST /api/auditorias-completadas/perfumeria`. Los cinco botones "Auditar" ahora abren WhatsApp.

Ese endpoint era además **el peor de los tres caminos de creación de desvíos**: hardcodeaba `severidad="Media"`,
plazo fijo de 7 días, e insertaba un teléfono en `desvio_eventos.actor_id`, que es `uuid` (fallaba siempre).

**El bot deja de perder auditorías** (`c3312d6`)

- **Persistencia de sesión.** Antes vivía solo en un `dict` del proceso: cualquier redeploy de Railway borraba
  las auditorías en curso en silencio. Ahora se persiste en `sesiones_whatsapp` (migración `etapa-19`, **ya
  corrida y verificada**). Job nuevo: avisa a las 2 h de inactividad, cierra a las 24 h, siempre avisando.
- **Seis arreglos de robustez**: el menú ofrecía 10 de 25 sucursales; un sticker iniciaba auditoría sobre la
  primera sucursal alfabética; `"no sirve"` confirmaba la auditoría entera; cualquier texto en el estado `DONE`
  se guardaba como nombre del responsable (de ahí el `'Ch'` que apareció en `audit_fiches`); un `"ok"` durante
  la evidencia creaba un desvío real; y media no soportada dejaba al bot mudo.

---

## 🎯 El plan en curso: panel de desvíos

**Documento vinculante: [`ARQUITECTURA_PANEL_DESVIOS.md`](ARQUITECTURA_PANEL_DESVIOS.md).** Tiene el diseño
completo, los hallazgos verificados que lo motivaron, y las cuatro decisiones ya tomadas (no se re-discuten).

Cuatro bloques. **El 1, el 2 y el 3 están hechos**; queda uno, y depende de Meta:

| # | Bloque | Estado | Depende de |
|---|---|---|---|
| **0** | Plantilla `farmaaudit_novedades` en Meta | ⏳ **enviada a revisión 2026-08-11** | Meta |
| **1** | Bandejas por turno en `/desvios` | ✅ hecho | — |
| **2** | Ficha como contenedor (FK `gestion.ficha_id` + navegación en ambos sentidos) | ✅ **hecho 2026-08-11** (`1987001`) | — |
| **3** | `usuarios_whatsapp.ultimo_mensaje_entrante_at` + teléfono resuelto en vivo + estado de entrega visible | ✅ **hecho 2026-08-11** (`0cf8e65`) | — |
| **4** | Chat del panel → WhatsApp; reemplazar el `send_text` roto del job de recordatorio | ⬜ pendiente | 0, 3 |

**Los bloques 2 y 3 no dependen de Meta**: se pueden hacer y probar sin esperar la plantilla. El 3 incluso se
prueba entero, porque dentro de la ventana de 24h ya se entrega con `send_text` — la plantilla solo agrega el
caso "ventana cerrada".

**Por qué importa el bloque 4**: hoy `POST /api/gestion/{id}/mensajes` (`main.py:515`) escribe en
`desvio_eventos` y nada más. Cuando un auditor escribe en el chat de un desvío, **el responsable nunca se
entera**. La dirección inversa sí funciona. La conversación es de una sola vía y la vía rota es la nuestra.

---

## Qué sigue además, en orden

Detalle completo en [`docs/analisis/04-roadmap.md`](docs/analisis/04-roadmap.md).

| # | Qué | Por qué ahora |
|---|---|---|
| **B5** | Seguridad: `META_APP_SECRET` obligatorio, CORS cerrado, trigger anti-escalado de rol, sacar `GET` de endpoints que mutan | La policy `profiles_role_protected` es SQL inválido y **nunca se creó**: hoy no hay anti-escalado de rol. Esfuerzo bajo, impacto alto. |
| **W2** | Evidencia a Storage: hoy las fotos de auditoría solo existen como `media_id` de Meta, **que caduca a ~30 días** | Se está perdiendo evidencia que no vuelve. Los bytes ya están en memoria; el patrón correcto ya existe en el mismo archivo. |
| **B1** | Baseline del esquema + runner de migraciones | La BD **no es reproducible desde el repo**: faltan los `CREATE TABLE` de `conversaciones`, `sesiones_auditoria`, `checklist_*`, `areas`, `pendientes`. |
| **B2** | Decidir qué pasa con los cuatro `score_*` por bloque | La base **nunca los guardó**. O se persisten desde el bot, o se ocultan los paneles que hoy muestran `—`. Es decisión de producto. |
| **B3/B4** | Transacción única para crear desvíos · una sola definición de "vencida" | Hoy "vencida" se calcula en tres lugares con tres relojes distintos. Una gestión se marca vencida **un día antes** por comparar UTC contra fecha argentina. |
| **W3/W6** | Separar formalmente las dos máquinas de estado · partir `router.py` (6.937 líneas) | Estructural. W3 sube de prioridad si ves al auditor cayendo en el flujo v1 sin pedirlo. |

**Después de la Tanda 3**, el candidato natural es el **scoring por marca de perfumería** (reporte mensual de
compliance por Natura, Avon, Unilever…), que tiene valor de monetización. Se descartó para esta etapa a
propósito: construir features de valor sobre datos que podían ser inventados era construir sobre arena.

---

## Cosas que te van a morder si no las sabés

**El lint está en cero — mantenelo así.** `cd frontend && npx eslint src` tiene que dar 0. Si aparece
`react-hooks/set-state-in-effect`, la regla **no** se satisface con un flag ni con un `eslint-disable`
razonable: hay que poner el `await` antes del primer `setState` (el estado ya arranca en `loading`). Si el
spinner tiene que volver al cambiar de entidad, eso va como ajuste **durante el render**, no en el efecto.

**Código muerto detectado, sin borrar todavía**: los default export `DesviosGestion` y `RevisionDesvios` (con
su `AppLayout`) ya no los importa nadie — solo se usan los `*Panel`. Con ellos muere también toda la rama
`embedded={false}`. Queda como decisión de limpieza aparte.

**`gestion.tel_responsable` es una foto congelada** al crear el desvío, y el job de recordatorio agrupa por
ahí (`supabase_manager.py:882`). Desde `etapa-21` la fuente de verdad es `usuarios_whatsapp`: si cambia el
responsable de una sucursal, los desvíos viejos siguen pingueando al teléfono anterior. Lo arregla el bloque 3.

**La tabla `auditores` quedó sin lecturas** pero no se borró, a propósito, como red de seguridad del backfill
de `etapa-21`. Se elimina en una etapa posterior.

**`pytest` está roto en este entorno** (incompatibilidad con Python 3.14: `ValueError: I/O operation on closed
file`). Los archivos de test se corren directo y funcionan:

```bash
python test_audit_hardening.py      # 17 tests de W1 + W4
python test_audit_session.py
python test_verification_flow.py
python test_imports.py              # smoke test de imports, detecta ciclos
```

**No hay runner de migraciones.** Los `frontend/docs/sql/etapa-*.sql` se pegan a mano en el SQL Editor de
Supabase. Ojo: `etapa-12` no compila (paréntesis de más), hay **dos archivos con el número 8**, y `etapa-7`
relaja policies que `etapa-6` endurece. El estado de "corrida / no corrida" vive en prosa, no en la base.

**Los tests no escriben en producción**, pero por una guarda explícita: `audit_session._client()` devuelve
`None` si detecta `PYTEST_CURRENT_TEST`. La máquina tiene credenciales de producción en `.env`, así que no
saques esa guarda.

**El bot degrada a memoria** si Supabase no responde, y lo loguea. Eso es deliberado: nunca se cae la
conversación en curso. Pero si ves auditorías perdiéndose otra vez, revisá los logs antes de sospechar del
código.

**Dos `total_desvios` distintos conviven** y no hay que confundirlos: el de `DashboardStats` / `ZonaResumen` se
calcula de `gestiones.length` y está bien; el de `audit_fiches` se llama `desvios_count`.

---

## Cómo levantar todo

```bash
# Frontend
cd frontend
npm run dev                                    # http://localhost:5173
VITE_ENABLE_DEV_BYPASS=true npm run dev        # entra como admin sin login
                                               # (ojo: trae datos reales de Supabase)

# Backend
uvicorn main:app --reload                      # http://localhost:8000
```

Variables del frontend en `frontend/.env.example`. La nueva es `VITE_WHATSAPP_PHONE`: el número del bot al que
apuntan los botones "Auditar por WhatsApp".

**Detalle no obvio del bot**: el texto pre-armado de esos botones tiene que ser **exactamente** `auditoria`.
`router.py` compara contra `V2_TRIGGERS` por igualdad, no por substring — un "Hola, quiero auditar la sucursal
X" cae en el flujo v1 sin avisar. Por eso el número y el disparador viven juntos en `whatsappAuditLink()`
(`frontend/src/lib/utils.ts`).

---

## Prueba de fuego si tocás el bot

1. Escribí `auditoria` → tienen que aparecer las **25** sucursales.
2. Elegí una, puntuá un bloque, mandá una foto.
3. **Reiniciá el backend** y mandá otro mensaje → el bot tiene que seguir donde estaba, no arrancar de cero.
4. Terminá la auditoría y mirá `audit_fiches`: `responsable_desvios` tiene que ser un nombre real.

# 01 — Capa WhatsApp

> Especialista: canal WhatsApp (webhook Meta, máquinas de estado conversacionales, parser Claude, evidencia).
> Rejilla E1-E6 según `docs/analisis/00-cimientos.md`. Fecha: 2026-08-05 · Rama `master`.

---

## Resumen ejecutivo

El bot funciona en el camino feliz y se cae de maneras silenciosas en casi todos los demás. Eso era
tolerable cuando WhatsApp era "una vía más de captura". Con la decisión de cimientos §2.1 —WhatsApp es
**el** canal— cada uno de esos caminos deja de ser un borde y pasa a ser el producto.

Los cuatro problemas de mayor peso, en orden:

1. **La sesión de auditoría v2 vive solo en un `dict` de proceso** (`audit_session.py:308`). Un redeploy de
   Railway —o un `docker restart`, o un OOM— borra toda auditoría en curso sin avisar a nadie. El auditor
   sigue mandando fotos a un bot que ya no sabe quién es.
2. **La evidencia se evapora.** Las fotos se descargan, se validan y se tiran: solo se guarda el `media_id`
   de Meta, que caduca a ~30 días (`audit_handlers.py:1174-1181`). Lo doloroso es que los bytes ya están en
   memoria en ese mismo bloque y el propio archivo tiene, 500 líneas antes, la implementación correcta
   (`audit_handlers.py:651`).
3. **Hay dos máquinas de estado por teléfono que no se hablan** y que se pisan mutuamente al terminar una
   auditoría, mandando al auditor al flujo v1 sin que nadie lo pida.
4. **Entrada no anticipada = comportamiento arbitrario.** Un sticker mandado en el momento equivocado
   inicia una auditoría sobre la sucursal alfabéticamente primera (`audit_handlers.py:910-942`); un mensaje
   de texto libre en la etapa de evidencia crea un desvío que termina en la tabla `gestion`; y hay un estado
   terminal (`DONE`) del que la única salida garantizada es un redeploy.

Todo lo que sigue está verificado leyendo el código. Donde no pude verificar algo, lo digo.

---

## E1 — Duplicación

### 1.1 Dos máquinas de estado conversacional por teléfono

Esta es la duplicación estructural que ordena a casi todas las demás.

| | v1 | v2 |
|---|---|---|
| Estados | `ConversationState`, 29 valores (`models.py:13-45`) | `AuditState`, 9 valores (`audit_session.py:11-21`) |
| Persistencia | tabla `conversaciones` (`supabase_manager.py:257`, 4 usos) | `_sessions_cache: Dict[str, AuditSession]` (`audit_session.py:308`) |
| Escrituras de estado | `update_conversacion` aparece **71 veces** en `router.py` | `save_session`, en memoria |
| Ruteo | `ConversationRouter._handle_message_locked` (`router.py:188-388`) | `AuditConversationHandler.handle_message` (`audit_handlers.py:286-401`) |

`audit_handlers.py`, `audit_session.py` y `audit_database.py` **nunca** tocan `conversaciones` (verificado
por grep: cero coincidencias). Es decir: no hay ningún punto donde las dos máquinas se sincronicen.

El árbitro es `main.py:1224-1228`:

```python
session = get_session(payload.telefono)
if session:
    result = await route.handle_perfumeria_audit(payload, meta_client)
else:
    result = await route.handle_message(payload, meta_client)
```

Y `router.py:229-232` tiene **su propia versión del mismo árbitro, con otra condición**:

```python
session = get_session(payload.telefono)
if session and session.estado != AuditState.DONE:
    return await self.handle_perfumeria_audit(payload, meta_client)
```

Dos guardas para la misma decisión, con criterios distintos (`if session` vs. `if session and estado !=
DONE`). Hoy la de `router.py:230` es inalcanzable —`main.py` desvía antes— pero está ahí, lista para
divergir más.

**El síntoma concreto del desacople.** Secuencia real y reproducible:

1. El auditor escribe `hola` → `router.py:267-268` → `_iniciar_seleccion_sucursal` deja la fila de
   `conversaciones` en `SELECCIONANDO_SUCURSAL_PERFUMERIA` (`router.py:3026-3030`).
2. En vez del número, escribe `auditoria` → `router.py:237-239` lo desvía a v2 y se crea la sesión en
   memoria. **La fila de `conversaciones` sigue en `SELECCIONANDO_SUCURSAL_PERFUMERIA`.**
3. Termina la auditoría v2. Alguna rama llama `delete_session` (p. ej. `audit_handlers.py:338`).
4. El siguiente mensaje ya no encuentra sesión v2 → cae en v1 → `_handle_seleccionando_sucursal_perfumeria`
   (`router.py:2471`). Si ese mensaje es un número entre 1 y 25, **arranca una auditoría v1 completa** que
   el auditor no pidió (`router.py:2496`, `2519-2560`).

El auditor termina en un flujo distinto, con otro checklist, sin haber hecho nada raro.

**Qué sobrevive:** la máquina v2 (`AuditState`), porque es la que implementa el flujo que la dirección
usa hoy y la que produce `gestion` con `bloque`. Ver W3 para la propuesta: no unificar las dos en una,
sino **separarlas formalmente por dominio** con un único punto de entrada.

### 1.2 Dos listas de disparadores para el mismo comando

- `router.py:237`: `V2_TRIGGERS = {"auditoria", "auditoría", "audit", "auditar", "perfumeria", "perfumería"}`
  — comparación **exacta** (`trigger in V2_TRIGGERS`).
- `audit_handlers.py:296`: `any(word in texto for word in ["auditoria", "audit", "perfumeria", "farmacia"])`
  — comparación por **subcadena**, y con un término (`farmacia`) que la otra lista no tiene, y sin los
  acentuados que la otra sí tiene.

La segunda es hoy casi inalcanzable (solo se llega a ella si `handle_perfumeria_audit` se invoca sin
sesión, lo cual únicamente ocurre desde `router.py:239`, que ya filtró). Es una lista muerta que diverge.
**Sobrevive `V2_TRIGGERS`**, y debería moverse a un único módulo de intents (ver W4).

### 1.3 Siete copias del mismo *stripping* de fences Markdown

`parser.py` repite el mismo bloque de seis líneas en **seis** métodos: 116-123, 187-194, 266-273, 357-364,
426-433, 498-505. `router.py:4334-4352` tiene una séptima variante (`_parse_llm_json_array`), más elaborada
—recorta por `[` y `]`— pero incompatible en comportamiento con las otras seis.

Siete implementaciones de "sacale los ``` a la respuesta de Claude", ninguna de las cuales sería necesaria
si se usara `output_config.format` (structured outputs), que el SDK soporta. Ver W6.

### 1.4 Dos caminos de evidencia dentro del mismo archivo, uno correcto y otro no

`audit_handlers.py` implementa la recepción de una foto dos veces:

- **Verificación de desvío previo** (`audit_handlers.py:630-655`): descarga, valida, y **sube a Storage**
  con `db.upload_desvio_evidencia(...)`, guardando `path`, `thumb_path`, `bucket` y una URL firmada en el
  `metadata` del evento (`audit_handlers.py:706-718`).
- **Evidencia de bloque** (`audit_handlers.py:1158-1184`): descarga, valida, y **descarta los bytes**;
  solo guarda `media_id` en `FotoEvidence`.

Es el mismo problema resuelto bien y mal en el mismo archivo, con 500 líneas de distancia. Sobrevive el
patrón de `:651`. Ver W2.

### 1.5 `determine_severity` — duplicación entre capas (contrato B)

`audit_database.py:14-21` deriva `Alta/Media/Baja` del puntaje del bloque. Los cimientos (§2.2) ya lo
marcaron para retiro en favor de la vista `sucursales_dashboard`. Confirmo desde mi lado que el bot es el
**productor** de ese valor: se escribe en `reportes.severidad` y `gestion.severidad`
(`audit_database.py:66`, `90`, `106`) y después alimenta plazos, alertas y semáforo. El retiro no es
gratis: hay que decidir quién calcula la severidad de una `gestion` nueva. Lo declaro en E3.

---

## E2 — Estado que se pierde

### 2.1 La sesión v2 completa, ante cualquier reinicio de proceso

`audit_session.py:307-308`:

```python
# Session storage: in-memory cache with Redis fallback
_sessions_cache: Dict[str, AuditSession] = {}
```

El comentario dice "in-memory cache with Redis fallback". **No hay Redis.** No hay tabla. No hay archivo.
No hay nada. Es un diccionario de proceso. Grep confirma: cero referencias a `redis` en todo el repo.

El contenedor corre `uvicorn main:app` sin `--workers` (`Dockerfile`, última línea), así que es un proceso
único por réplica. Todo lo que se pierde en un reinicio:

- Los puntajes de los bloques ya calificados (`bloques`, `audit_session.py:118`).
- Los puntajes por marca de OFERTAS (`brands`, `:122`).
- Toda la evidencia acumulada: `fotos` y `desvios` (`:128-129`) — incluidos los `media_id` de fotos que el
  auditor ya sacó y mandó.
- La cola de verificación de desvíos previos y su progreso (`pending_verifications`,
  `current_verification_index`, `:132-133`).
- `pending_ficha_reporte_id` (`:143`), es decir el `id_reporte` recién creado en la BD. Si el proceso se
  reinicia entre `save_audit_to_database` y la generación de la ficha, queda un reporte + gestiones en la
  base **sin ficha y sin forma de reconstruirla**, porque nadie sabe ya a qué sesión pertenecían.

**Qué pasa exactamente cuando se cae.** El auditor manda el siguiente mensaje. `main.py:1224` no encuentra
sesión, así que va a `route.handle_message` → `_handle_message_locked`. Ahí pasa una de dos:

- Si el mensaje es texto y `conversaciones` tenía un estado v1 viejo, entra al handler de ese estado (ver
  §1.1, punto 4).
- Si no, cae en `_handle_idle_state` (`router.py:1895`) y el bot responde como si nada hubiera pasado.

**En ningún caso se le dice al auditor que perdió la auditoría.** No hay mensaje, no hay alerta al
coordinador, no hay log distinguible. La media hora de recorrido de piso se evapora en silencio.

### 2.2 El camino barato ya está escrito y probado — y nadie lo usa

`AuditSession.to_dict()` (`audit_session.py:160-188`) y `from_dict()` (`:190-207`) existen, serializan los
23 campos incluidos `fotos` y `desvios`, y están cubiertos por test (`test_audit_session.py:179`, `187`).

Grep sobre todo el repo excluyendo tests: **cero llamadas en producción**. La infraestructura de
persistencia está construida y desconectada.

Lo mismo con el vencimiento: `expires_at` se calcula en cada sesión con 24h de TTL
(`audit_session.py:151-153`) e `is_expired()` está implementado (`:301-304`). Grep confirma que
`is_expired` **nunca se invoca**. El job que *parece* hacerlo, `check_expired_audit_sessions`
(`main.py:1396`), en realidad opera sobre la tabla v1 vía `sheets.get_sesiones_activas_expiradas`
(`main.py:1400`) — no toca `_sessions_cache` ni una vez. Consecuencia: **una sesión v2 nunca expira**.
Un auditor que abandona a mitad de camino queda bloqueado en ese estado indefinidamente (agravado por
§4.4).

`get_all_sessions()` (`audit_session.py:341-343`), que sería la herramienta natural para barrer sesiones
vencidas, tampoco se llama desde ningún lado.

### 2.3 Estado accesorio que también vive en memoria

- `_processed_messages` / `_processing_messages` (`main.py:127-128`): deduplicación de mensajes. Acá el
  diseño **sí** contempló el problema: `_claim_message_distributed` (`main.py:234-257`) escribe en la tabla
  `webhook_dedup` "to prevent cross-instance duplicates". Es la prueba de que el sistema ya anticipa correr
  en más de una instancia — mientras las sesiones asumen exactamente una. Esa contradicción es la que W1
  resuelve.
- `_last_reminder_sent` (`main.py:133`): contador de recordatorios. Se resetea en cada deploy, así que las
  3 notificaciones máximo se vuelven 3 *por deploy*.
- `ConversationRouter._conversation_locks` (`router.py:64`): dict de locks por teléfono que **nunca se
  purga**. Crece monótonamente. Con ~25 auditores + encargados es irrelevante en volumen, pero es un lock
  que no protege nada entre réplicas.

**No pude verificar** cuántas réplicas corre este servicio en Railway (no hay `railway.json`, `Procfile`
ni `nixpacks.toml` en el repo). Si es más de una, el bug es inmediato y grave: mensajes consecutivos del
mismo auditor pueden caer en procesos distintos y solo uno tiene la sesión. Si es una sola, sigue siendo
grave, solo que el disparador es el deploy en vez del balanceo. Además, con más de una réplica el
scheduler de `main.py:411-470` correría duplicado y los recordatorios diarios saldrían N veces.

---

## E3 — Contratos

### Contrato A — Identidad de sucursal (**produzco**)

El bot escribe `sucursal_id` en tres lugares distintos del flujo v2:
`Reporte.id_sucursal` (`audit_database.py:85`), `Gestion.id_sucursal` (`:103`) y `audit_fiches.sucursal_id`
(vía `AuditFichesManager`). El valor sale de `session.sucursal_id`, que se fija en
`audit_handlers.py:942` desde `elegida["id"]`, y ese `id` viene directo de
`SELECT id, nombre FROM sucursales` (`audit_handlers.py:871`).

**Es decir: en el flujo v2 el valor sí proviene de la tabla `sucursales`.** No es el bot el que inventa
IDs sueltos. Pero hay una ruta donde sí puede escribir basura: `start_desvio_management` crea la sesión con
`sucursal_id=""` (`audit_handlers.py:453`), y si por alguna razón el flujo llegara a persistir con ese
valor vacío, escribiría `id_sucursal=""`. Hoy ese flujo no crea reportes, así que es teórico.

**Qué necesito de backend:** la FK que falta en `audit_fiches.sucursal_id → sucursales(id)`
(`migration_audit_fiches.sql:8`). Sin ella no tengo forma de detectar en tiempo de escritura que estoy
generando una ficha huérfana; me entero cuando la dirección ve 25 sucursales "Sin auditar". Con la FK, el
insert falla ruidosamente y yo puedo alertar al auditor en el momento.

### Contrato B — Estado de salud / semáforo (**consumo, y contamino**)

Consumo indirectamente: `get_previous_audit` (`audit_database.py:197-224`) intenta traer los puntajes de la
auditoría anterior para mostrarle al auditor la tendencia (`audit_handlers.py:1017-1030`).
**Está roto de dos formas simultáneas** (ver E4.1).

Contamino de dos formas:

1. `determine_severity` (`audit_database.py:14`), que los cimientos ya mandaron a retiro.
2. **La gestión fantasma.** Cuando una auditoría cierra sin desvíos, `save_audit_to_database` crea igual un
   `reporte` y una `gestion` de resumen (`audit_database.py:136-187`) con `desvio="Auditoría de Perfumeria
   - Resumen"`, `estado=ABIERTA` y plazo a 7 días. Eso viola el glosario de cimientos §3 de frente: una
   gestión es "el hallazgo ya convertido en compromiso", y esto no es un hallazgo.

   Las consecuencias son medibles: `get_gestiones_pendientes_sucursal` filtra solo por
   `estado in ["Abierta","En_proceso","Vencida"]` (`supabase_manager.py:811`), sin excluir resúmenes, así
   que la gestión fantasma aparece en el menú de "gestión de desvíos" por WhatsApp y el bot le pregunta al
   auditor "¿Cómo está hoy? ✅ Resuelto / ⚠️ Persiste" sobre una auditoría sin hallazgos
   (`audit_handlers.py:604-615`). A los 7 días, `check_overdue_gestion` (`main.py:1539`) la marca `Vencida`
   y le manda una alerta al coordinador. Y cuenta como desvío abierto para el semáforo.

**Qué necesito de backend/SQL:** que la vista `sucursales_dashboard` sea la única fuente de salud, y una
regla explícita sobre qué hace el bot cuando una auditoría cierra limpia (mi propuesta: escribe la ficha y
**no** escribe gestión).

### Contrato C — Evidencia (**produzco**) — roto, y la reparación es barata

Confirmo la pista y agrego el detalle que la vuelve accionable.

Los TODO de `main.py:1175-1176` y `1184-1185` siguen sin implementar, así que `media_url` sale siempre
`None` del webhook (`main.py:1164`, `1207`). Eso deja muertas todas las ramas condicionadas a
`payload.media_url` en `router.py` (líneas 1385, 1953, 4090, 4429, 4537, 4612, 4755, 4763, 4956, 4996,
5640, 5648 — doce). En v2, `FotoEvidence.media_url` se llena con ese `None`
(`audit_handlers.py:1177`) y después `audit_database.py:70-73` busca una foto con `media_url` para llenar
`Reporte.foto_url`: **nunca encuentra ninguna**, así que todos los reportes de perfumería v2 se guardan con
`foto_url=""` (`supabase_manager.py:444`).

Y el audio se guarda literalmente como el string `"[AUDIO] Sin transcripción"`
(`audit_handlers.py:1218`), aunque `AudioTranscriber.transcribe_bytes` existe y funciona con bytes
(`audio.py:39-77`).

**Lo importante: la reparación no requiere resolver `media_url`.** En el punto exacto donde hoy se descarta
la evidencia, los bytes ya están en memoria:

```python
# audit_handlers.py:1160-1164
media_bytes, mime_type = await meta_client.download_media_with_metadata(payload.media_id)
validation = PhotoValidator.validate_media_bytes(media_bytes, mime_type)
```

Y el repositorio ya tiene el patrón correcto implementado dos veces: `audit_handlers.py:651`
(`upload_desvio_evidencia`) y `router.py:1362-1377`, que hace descarga → subida a Storage → URL firmada →
transcripción con `transcribe_bytes`, todo sin tocar `media_url`. W2 es esencialmente copiar
`router.py:1361-1384` dentro de `handle_bloque_evidence`.

**Qué necesito de frontend:** que consuma `foto_url` como una URL firmada de vida corta (86400s por
defecto, `supabase_manager.py:1032`) y no como link permanente, o que pida una nueva al abrir. Si el front
hoy asume URL estable, W2 lo rompe.
**Qué necesito de backend:** una decisión sobre el bucket y la política de retención de
`auditoria-respuestas` / evidencias de gestión.

### Contrato D — Desvío → gestión (**produzco**)

Confirmo las dos grietas de cimientos §4 y agrego una tercera y una cuarta.

- Los tres inserts secuenciales sin transacción están en `audit_database.py:95`, `115` y `119`
  (`create_reporte` → `create_gestion` → `save_encargado_evento`), dentro de un `for` sobre desvíos
  (`:60`). Si falla el desvío 3 de 5, quedan 2 gestiones creadas, 3 no, y la excepción sube hasta
  `audit_handlers.py:1582` que le dice al auditor *"Error guardando en BD, pero tu auditoría fue
  registrada"* — que es falso, quedó a medias.
- **La tercera grieta:** el mensaje de `audit_handlers.py:1586` afirma que la auditoría "fue registrada" y
  el handler retorna `audit_saved_local_only` (`:1589`). No hay ningún "local" donde se registre: la sesión
  sigue en el `dict` de memoria y no se persiste nada. Es una mentira al usuario en el peor momento.
- **La cuarta:** `save_audit_to_database` devuelve `results[0]` (`audit_database.py:190`), o sea solo el
  primer par reporte/gestión. La ficha se asocia únicamente a ese `id_reporte`
  (`audit_handlers.py:1571-1572`). Si la auditoría tuvo 5 desvíos, 4 reportes quedan sin ficha asociada.

**Qué necesito de backend:** la FK `gestion.id_reporte → reportes(id)` y, sobre todo, un punto de escritura
transaccional — idealmente una función RPC de Postgres `crear_desvios_auditoria(payload jsonb)` que haga
los N reportes + N gestiones + N eventos en una sola transacción. Desde el bot yo llamo una vez y me entero
de si funcionó o no, sin estados intermedios.

### Contrato E — Permisos de módulo

No lo toco. `_VALID_MODULE_PERMISSIONS` (`main.py:135-142`) está en mi archivo por accidente de layout, no
por dominio; es del backend/panel.

---

## E4 — Falla silenciosa

Ordenadas por daño.

### 4.1 `get_previous_audit` consulta una tabla que no existe

`audit_database.py:206-210`:

```python
response = db.client.table("reporte").select(
    "id, sucursal_id, puntuaciones"
).eq("sucursal_id", sucursal_id)...
```

Tres errores en cinco líneas: la tabla se llama **`reportes`** en plural (`supabase_manager.py:432`), la
columna es **`id_sucursal`** no `sucursal_id` (`supabase_manager.py:438`), y **`puntuaciones` no existe**
en el esquema de `reportes` (ver el insert completo, `supabase_manager.py:432-447`).

La excepción se traga en `:222-224` con un `logger.warning` y retorna `None`. Resultado: la comparación
histórica que `handle_score` construye con tanto cuidado (`audit_handlers.py:1017-1030`, el bloque de
`⬆️ +2 (antes: 3/5)`) **nunca se muestra**. Es una feature completa que nadie sabe que está apagada, desde
que se escribió.

### 4.2 El encargado recibe notificaciones que mienten, o dos por auditoría

`handle_confirmation` llama `send_manager_notification` **incondicionalmente** tras guardar
(`audit_handlers.py:1576-1578`), sin mirar cuántos desvíos hubo. El texto dice
`"✅ Auditoría enviada con hallazgos pendientes de revisar"` (`audit_database.py:245`).

Con 0 desvíos: el encargado recibe un mensaje que le anuncia hallazgos pendientes que no existen.
Con ≥1 desvío: recibe ese mensaje **más** el de `_notify_responsable_desvios_pendientes`
(`audit_handlers.py:96-126`, invocado en `:382`), que dice `"🚨 Se detectaron N desvío(s)"`. Dos mensajes
casi idénticos con minutos de diferencia.

De yapa, el primer mensaje pone `Auditor: {telefono}` (`audit_database.py:242`): le filtra al encargado el
número de teléfono del auditor en vez de su nombre, que está disponible en `session.auditor_nombre`.

### 4.3 `handle_select_sucursal` acepta cualquier cosa y elige la primera sucursal

`audit_handlers.py:910`:

```python
texto = (payload.contenido or "").strip().lower() if payload.tipo == "text" else ""
```

Si el mensaje es un sticker, un video, un documento, una ubicación o un contacto, `texto` queda `""`.
Seguimiento línea por línea: `""` no está en `{"cancelar","salir","cancel"}` (`:912`); no empieza con
`audit_suc_` (`:920`); `"".isdigit()` es `False` (`:923`); y entonces cae al matcheo por nombre parcial
(`:927-930`):

```python
match = next((s for s in sucursales if texto in s["nombre"].lower()), None)
```

`"" in cualquier_string` es **siempre `True`**. Devuelve `sucursales[0]`, o sea la sucursal alfabéticamente
primera (el `ORDER BY nombre` está en `:871`). Línea `942`: `session.sucursal_id = elegida["id"]` y arranca
la auditoría.

**Mandar un sticker mientras se elige la sucursal inicia una auditoría sobre la sucursal equivocada, sin un
solo mensaje de error.** El mismo camino se activa con `contenido=""`, que `main.py:1199-1201` produce para
cualquier mensaje `interactive` que no sea `list_reply` ni `button_reply`.

El contraste hace más obvio que es un descuido: `handle_verify_sucursal_selection`, 400 líneas antes,
maneja el mismo caso bien —`if not texto.isdigit()` corta y reenvía el menú (`audit_handlers.py:508-511`).

### 4.4 El estado `DONE` es una trampa sin salida garantizada

Tras una auditoría con desvíos, la sesión queda en `DONE` con `ficha_url` cargada y se le manda al auditor
un quick reply con botones `descargar_ficha_si` / `descargar_ficha_no` (`audit_handlers.py:244-251`).

En `DONE`, `handle_message` acepta exactamente tres cosas (`audit_handlers.py:332-397`): el id
`descargar_ficha_si`, el id `descargar_ficha_no`, o una de las palabras `ficha|pdf|documento|descargar`.
Cualquier otro texto llega a `:399`:

```python
return "audit_already_completed"
```

**Sin enviar ningún mensaje y sin borrar la sesión.** Y como `main.py:1225` desvía a v2 mientras exista
*cualquier* sesión, el auditor queda encerrado: no puede empezar otra auditoría, no puede gestionar
desvíos, no puede escribir `hola`, y el bot no le contesta nada. Las únicas salidas son tocar exactamente
uno de los dos botones (que pueden haber quedado arriba en el hilo, o expirado) o **esperar un redeploy**.

La ironía es exacta: el defecto de E2.1 —que las sesiones no persistan— es hoy el único mecanismo de
recuperación de este defecto.

La palabra clave `descargar` (`:348`) tampoco salva: lleva a `generate_and_send_ficha`, que retorna
`"ficha_sent"` sin borrar la sesión (`:1479`) y sin mandar el PDF (el TODO de `:1475-1476` sigue abierto;
solo manda un texto que dice que la ficha se generó).

### 4.5 Cualquier texto libre durante la recolección de evidencia crea un desvío real

`handle_bloque_evidence` (`audit_handlers.py:1116-1129`): si el texto no es `SIGUIENTE`/`NEXT`, ni el id
`sin_problemas`, ni el id `otro`, ni un id de plantilla, entonces:

```python
session.add_desvio(bloque=current_bloque, descripcion=raw_id)
```

`gracias`, `ok`, `ya está`, `hola`, `dale`, `👍`, un mensaje mandado por error, o el fragmento de una
conversación que el auditor pegó sin querer: todo se convierte en un `Desvio`, y todo `Desvio` se convierte
en un `reporte` + una `gestion` + una notificación al encargado (`audit_database.py:59-133`). Un desvío
falso llamado "gracias" queda abierto con plazo de 7 días, escala a `Vencida`, dispara alerta al
coordinador (`main.py:1565-1575`) y cuenta para el semáforo.

No hay confirmación, no hay preview, no hay forma de borrarlo desde WhatsApp: la única corrección es entrar
al panel web.

### 4.6 Matcheo por subcadena en la confirmación final

`handle_confirmation` (`audit_handlers.py:1564`):

```python
if any(word in texto for word in ["sí", "si", "yes", "confirmo", "ok", "✅"]):
```

`"si"` como subcadena, evaluado **antes** que la rama negativa (`:1646`). Palabras castellanas comunes que
contienen `si` y por lo tanto **confirman y guardan la auditoría**:

- `siguiente` — que es literalmente la palabra que el auditor viene tipeando cuatro veces seguidas en los
  cuatro bloques anteriores (`audit_handlers.py:1038`, `1310`).
- `revisión`, `revisar la puntuación`, `necesito`, `posible`, `insisto`, `casi`, `decisión`, `visita`.

Un `no, quiero hacer una revisión` confirma el envío. `ok` también, por estar en la lista, así que un
acuse de recibo del auditor cierra la auditoría.

El mismo patrón está en la verificación de desvíos (`audit_handlers.py:677`, `687`, `690`): `"resuelto" in
respuesta`, `"persiste" in respuesta`, `"omitir" in respuesta`. Ahí es menos peligroso porque las palabras
son largas, pero `"no está resuelto"` marca el desvío como **Resuelto**, cierra la gestión
(`:727`) y suma a `verified_resueltos`.

### 4.7 Media no soportada deja al bot mudo

`handle_bloque_evidence` maneja `text` (`:1051`), `image` (`:1149`) y `audio` (`:1214`). Cualquier otro
tipo —video, documento, sticker, ubicación, contacto, reacción— cae en `:1242`:

```python
return "unsupported_media"
```

Sin enviar nada. El auditor manda un video del problema (que es lo natural si la foto no alcanza) y el bot
no responde. Sin `SIGUIENTE`, la auditoría no avanza y él no sabe por qué.

Peor: `main.py` ni siquiera extrae contenido para esos tipos. Solo hay ramas para `text`, `audio`, `image`
e `interactive` (`main.py:1168-1201`); para el resto `contenido` queda `None` y `media_id` también, así
que ni el `media_id` se registra para diagnóstico posterior.

### 4.8 Código muerto que parece vivo

- `audit_handlers.py:1131-1147`: un segundo `if payload.tipo == "text":` **inalcanzable**. Todas las ramas
  del primer bloque (`:1051`) retornan: la de SIGUIENTE en `:1068`/`:1081`/`:1087`, la de `sin_problemas`
  en `:1102`, la de `otro` en `:1112`, y el catch-all en `:1129`. La feature "escribí *problema* y te
  muestro las plantillas" nunca se ejecutó.
- `router.py:5642`: `await self.transcriber.transcribe(payload.media_url)`. `AudioTranscriber` tiene
  `transcribe_from_url` y `transcribe_bytes` (`audio.py:20`, `:39`), **no** `transcribe`. Sería un
  `AttributeError` si la rama fuera alcanzable — que no lo es, porque está guardada por `payload.media_url`
  (`:5640`), que es siempre `None`. Un bug protegido por otro bug.
- `router.py:1449`: `if False:` con 35 líneas adentro, en `check_expired_audit_sessions`
  (`main.py:1449-1484`) — perdón, en `main.py`. Rama de auto-omisión desactivada con un comentario que lo
  admite (`main.py:1448`).

### 4.9 Fail-open en la detección de borrosidad

`PhotoValidator._detect_blur` devuelve exactamente `BLUR_THRESHOLD` (80.0) ante cualquier excepción
(`photo_validator.py:127-129`), y el chequeo es `blur_score < BLUR_THRESHOLD`
(`photo_validator.py:76`), que con 80.0 da `False`. Toda foto cuyo análisis falle pasa como nítida.
Es la elección defensiva correcta —mejor aceptar una foto dudosa que bloquear al auditor— pero solo deja un
`logger.warning`, así que si la detección se rompiera del todo (una versión de Pillow, un formato raro)
nadie se enteraría.

### 4.10 `save_session` sin `save_session`

Varias mutaciones de sesión no persisten al cache porque `save_session` no se llama después. Ejemplos:
`session.set_bloque_score(...)` en `audit_handlers.py:979` sí se guarda después (`:985`/`:1011`), pero
`verif["resultado"] = "omitido"` en `:691` muta un dict dentro de `pending_verifications` y confía en que
`_advance_verification` guarde (`:792`) — cosa que solo pasa si hay una verificación siguiente
(`:791`). En la última verificación de la cola, `move_to_next_verification` devuelve `False` y se va a
`_finish_verifications` (`:795`), que sí guarda (`:824`). Funciona, pero por casualidad: la corrección
depende de que el objeto sea el mismo por referencia en memoria. **En cuanto la sesión se persista (W1),
esta clase de mutación se pierde.** Es un requisito de diseño para W1, no un bug actual.

---

## E5 — Superficie a borrar

Verificado con grep sobre todo el repo, excluyendo `test_*.py`.

| Qué | Dónde | Evidencia de que no se usa |
|---|---|---|
| `AuditConversationHandler.handle_evidence` (124 líneas) | `audit_handlers.py:1316-1439` | Cero llamadas. Ningún `AuditState` rutea ahí (`:306-330`). Es el flujo de evidencia de una versión anterior. |
| `get_all_sessions()` | `audit_session.py:341-343` | Cero llamadas. |
| Rama de plantillas por palabra clave | `audit_handlers.py:1131-1147` | Inalcanzable (§4.8). |
| `get_previous_audit` | `audit_database.py:197-224` | Se llama pero siempre falla (§4.1). **Reescribir, no borrar** — la feature es buena. |
| `router.py:5640-5650` (transcripción/imagen en `_cerrar_auditoria`) | `router.py` | Guardado por `media_url` siempre `None`, y llama un método inexistente. |
| Las 12 ramas `payload.media_url` de `router.py` | `1385, 1953, 4090, 4429, 4537, 4612, 4755, 4763, 4956, 4996, 5640, 5648` | Todas muertas por el contrato C. Con W2 se reemplazan por el patrón `media_id`, no se conservan. |
| `if False:` en el job de sesiones expiradas | `main.py:1449-1484` | Comentado como intencionalmente inalcanzable (`:1448`). |
| `expires_at` / `is_expired()` | `audit_session.py:151-153`, `301-304` | Nunca invocados. **Conservar solo si W1 los usa**; si no, borrar para no simular una garantía inexistente. |
| Seis bloques de fence-stripping | `parser.py:116-123, 187-194, 266-273, 357-364, 426-433, 498-505` | Reemplazables por structured outputs (W6). |
| `send_file` / `send_message` de MetaClient | `meta_client.py:171`, `:321` | `send_message` no tiene llamadas fuera del propio archivo; `send_file` solo se usa desde `send_message`. **Verificar antes de borrar** — no revisé el frontend ni scripts sueltos. |
| `handle_init` como estado ruteado | `audit_handlers.py:306-307` | `AuditState.IDLE` nunca persiste: `create_session` la pone en IDLE (`audit_session.py:318`) y `handle_init` la pisa con `SELECT_SUCURSAL` antes de `save_session` (`:895-897`). Rama defensiva; se puede simplificar. |

Superficie total identificada como borrable con certeza: ~200 líneas de `audit_handlers.py` +
`audit_session.py`, más ~80 líneas de ramas muertas en `router.py`. No es mucho en volumen, pero es
superficie que hoy hace parecer que existen features que no existen.

---

## E6 — Propuesta

Seis movimientos. El orden importa: W1 y W2 son prerrequisitos conceptuales de todo lo demás, porque sin
sesión persistida y sin evidencia persistida, cualquier otra mejora sigue apoyada sobre arena.

---

### W1 — Persistir la sesión v2 en Postgres

**Problema:** E2.1, E2.2.

**Plan.**

1. Tabla nueva, en un archivo SQL versionado del repo (cimientos §2.2: el esquema vive en los archivos SQL):

   ```sql
   CREATE TABLE sesiones_whatsapp (
     telefono      text PRIMARY KEY,
     id_sesion     text NOT NULL,
     estado        text NOT NULL,
     payload       jsonb NOT NULL,          -- AuditSession.to_dict()
     sucursal_id   text REFERENCES sucursales(id),
     updated_at    timestamptz NOT NULL DEFAULT now(),
     expires_at    timestamptz NOT NULL
   );
   CREATE INDEX ON sesiones_whatsapp (expires_at);
   ```

   `telefono` como PK da exclusión mutua natural: una sesión activa por teléfono, que es exactamente la
   semántica que `_sessions_cache` ya tiene.

2. Reescribir los cinco puntos de acceso de `audit_session.py:311-343` contra esa tabla, usando
   `to_dict()`/`from_dict()` **que ya existen y ya están testeados** (`:160-207`,
   `test_audit_session.py:179-187`). El cache en memoria se conserva como *read-through* con invalidación
   por `updated_at`, no como fuente de verdad.

3. **Requisito de diseño derivado de E4.10:** una vez persistida, toda mutación tiene que terminar en
   `save_session`. Hoy hay mutaciones que funcionan por identidad de referencia
   (`audit_handlers.py:691`, `729`, `772`). Auditar las ~15 mutaciones de sesión y agregar el guardado
   faltante es parte del alcance de W1, no un extra.

4. Conectar `is_expired()` (`audit_session.py:301`) a un job real. `check_expired_audit_sessions`
   (`main.py:1396`) hoy solo mira la tabla v1; se le agrega un barrido de `sesiones_whatsapp` que, ante una
   sesión vencida, **le avisa al auditor** ("tu auditoría de X quedó incompleta, escribí *auditoria* para
   empezar de nuevo") antes de borrarla. Hoy no hay ningún aviso, ni siquiera cuando el estado se pierde.

5. Migración: no hay estado que migrar. El deploy de W1 pierde las sesiones en vuelo una última vez.
   Hacerlo fuera del horario de auditoría.

**Riesgo:** bajo. El contrato de la API interna (`create/get/save/delete_session`) no cambia. Lo único que
puede sorprender es la latencia: pasa de 0 a un round-trip de Postgres por mensaje. Con ~25 auditores es
irrelevante.

**Beneficio colateral:** habilita más de una réplica en Railway, que es lo que `webhook_dedup`
(`main.py:242`) ya asumía posible.

---

### W2 — Cerrar el contrato C: la evidencia sobrevive a los 30 días de Meta

**Problema:** E1.4, E3-C, E4.7.

**Plan.** No requiere resolver `media_url` ni tocar el webhook. En `handle_bloque_evidence`, donde hoy los
bytes se validan y se tiran (`audit_handlers.py:1160-1181`), se replica el patrón ya probado de
`router.py:1362-1377`:

```
media_bytes, mime = download_media_with_metadata(media_id)   # ya está
validation      = PhotoValidator.validate_media_bytes(...)   # ya está
upload          = db.upload_auditoria_evidencia(...)         # NUEVO — bytes ya en RAM
foto.storage_path = upload["path"]
foto.thumb_path   = upload.get("thumb_path")
```

Para audio, lo mismo más `await self.transcriber.transcribe_bytes(media_bytes, mime)`
(`audio.py:39`), que reemplaza el literal `"[AUDIO] Sin transcripción"` de `audit_handlers.py:1218`.

Después, `audit_database.py:69-73` deja de buscar `foto.media_url` y usa `foto.storage_path`, con lo cual
`Reporte.foto_url` deja de guardarse vacío por primera vez.

Y se agrega el `else` que falta en `:1242` para media no soportada: guardar el `media_id` igual (Meta lo da
para video y documento también) y responder "guardé tu video pero no puedo analizarlo; si el problema se ve
mejor en foto, mandá una".

Como movimiento acompañante en el webhook: `main.py:1168-1201` debería extraer `media_id` para `video`,
`document` y `sticker` también, aunque solo sea para no perder la referencia.

**Riesgo:** bajo-medio. El único punto delicado es el consumo desde el front (URLs firmadas de 24h,
`supabase_manager.py:1032`) y la cuota de Storage: ~25 sucursales × 4 fotos × frecuencia de auditoría.
No dimensioné el crecimiento, hay que hacerlo antes de mergear.

**Depende de:** una decisión de frontend sobre URLs firmadas vs. permanentes (F), y de la política de
buckets (B).

---

### W3 — Un solo punto de entrada, y separación formal de dominios

**Problema:** E1.1, E1.2, E2.3.

**Tomo posición: no se unifican las dos máquinas de estado. Se separan formalmente por dominio.**

El razonamiento es que no son dos versiones del mismo flujo: son **dos productos distintos que comparten
canal**. La v2 es "auditoría de perfumería con puntaje 1-5 por bloque". La v1 contiene, además del flujo de
auditoría legacy, el flujo del **encargado** (`ENCARGADO_*`, `router.py:427-434`) y el de **campañas**
(`CAMPANIA_*`, `:436-449`), que no tienen nada que ver con la auditoría y que están vivos. Fusionar
`AuditState` con `ConversationState` produciría un enum de 38 estados que mezcla tres dominios: sería
duplicación disfrazada de unificación.

**Plan.**

1. **Un único resolvedor de conversación**, en un módulo nuevo (`conversation_router.py`), invocado desde
   `main.py:1224`, que decide entre tres dominios en un solo lugar y devuelve el handler:

   ```
   resolve(telefono) -> AUDITORIA_V2 | ENCARGADO | AUDITOR_LEGACY
   ```

   Elimina la guarda duplicada de `router.py:229-232` y el `if session:` de `main.py:1225`.

2. **Invariante explícito y verificado en runtime:** un teléfono no puede tener a la vez una fila activa en
   `sesiones_whatsapp` (post-W1) y un `conversaciones.estado_actual != IDLE`. Al crear una sesión v2,
   `handle_init` escribe `conversaciones.estado_actual = IDLE`; al borrarla, también. Eso mata la secuencia
   de E1.1 de raíz. Son dos llamadas a `update_conversacion`, que ya existe
   (`supabase_manager.py:257`).

3. **Una sola tabla de intents**, compartida por los tres dominios, con matcheo **exacto sobre texto
   normalizado** (sin acentos, sin puntuación, trim), reemplazando `V2_TRIGGERS` (`router.py:237`) y la
   lista por subcadena de `audit_handlers.py:296`. `router.py` ya tiene `_normalize_intent_text`
   (`:990`) — se reutiliza.

4. **Comando de escape global**, disponible en todo estado de todo dominio: `cancelar` / `salir` /
   `reiniciar` limpia sesión v2 y estado v1 y responde el menú. Hoy `cancelar` solo funciona en dos estados
   (`audit_handlers.py:500`, `912`) y no existe en `SCORING`, `BLOQUE_EVIDENCE_COLLECTION`,
   `SCORING_BRANDS`, `SUMMARY` ni `DONE`.

**Riesgo:** medio. Toca el punto de entrada de todos los mensajes. Mitigable con un rollout donde el
resolvedor nuevo primero solo *loguea* su decisión y se compara con la del código actual durante unos días,
antes de tomar el control.

---

### W4 — Endurecer la entrada del auditor

**Problema:** E4.3, E4.4, E4.5, E4.6, E4.7, más la pista del menú de 10 sucursales.

Cinco arreglos acotados, ninguno arquitectónico, todos de alto impacto sobre confiabilidad:

1. **Menú de sucursales completo.** `_send_audit_sucursal_menu` (`audit_handlers.py:838-841`) hace
   `chunk = sucursales[:10]` y después pregunta `if len(chunk) <= PAGE`, condición que es **siempre
   verdadera**, con lo cual el fallback de texto numerado de `:858-862` es inalcanzable y solo se ofrecen
   10 de ~25 sucursales. Detalle importante que matiza el impacto: el índice numérico sí es consistente con
   la lista completa (`:923-924` indexa `verification_menu`, que tiene las 25), así que quien conozca el
   número o el nombre puede llegar a la 17. Pero el menú nunca se lo muestra.

   La solución ya está escrita dos veces en el repo: `_send_sucursal_menu` (`audit_handlers.py:468`) hace
   la comprobación correcta, y `router.py:3007-3020` la resuelve con un comentario que explica exactamente
   por qué el texto numerado es lo correcto con ~25 sucursales (`MAX_LIST_ROWS_TOTAL` es 10 **en total**,
   no por sección — `meta_client.py:22-25`). Se copia esa.

2. **Sin matcheo por subcadena en decisiones destructivas.** `handle_confirmation`
   (`audit_handlers.py:1564`) pasa a comparar contra el conjunto exacto `{"si","sí","confirmar",
   "confirmo","1"}` sobre texto normalizado; los ids de botón (`"si"`/`"no"`, `:1543-1544`) siguen
   funcionando porque son exactos. Mismo tratamiento para `:677`, `:687`, `:690`. Ante ambigüedad, reenviar
   los botones — nunca adivinar.

3. **Nada de desvíos por accidente.** El texto libre en `BLOQUE_EVIDENCE_COLLECTION`
   (`audit_handlers.py:1116-1129`) pasa a mostrar una confirmación de un toque ("¿Registro esto como
   desvío en Limpieza?" → Sí / No, era un comentario) antes de `add_desvio`. Alternativa más barata:
   acumularlos como borradores en la sesión y mostrarlos todos juntos en el `SUMMARY`
   (`audit_handlers.py:1519-1522` ya los lista) con opción de descartar.

4. **Salir de `DONE`.** Cualquier mensaje no reconocido en `DONE` reenvía los botones **y** ofrece
   "empezar otra auditoría"; y `delete_session` se llama en toda rama terminal, incluida la de
   `generate_and_send_ficha` (`:1479`). Complementariamente, W1 le pone TTL a la sesión, con lo cual el
   encierro deja de ser permanente aun si se escapa un camino.

5. **Nunca callarse.** `handle_bloque_evidence:1242` y `handle_message:401` (`return "unknown_state"`)
   pasan a enviar siempre algo. Es una regla que conviene volver invariante del canal: *ningún handler
   retorna sin haber mandado al menos un mensaje*, verificable con un test que recorra los nueve estados
   con los seis tipos de media.

**Riesgo:** bajo. Son cambios locales y muy testeables. Recomiendo hacer W4 **primero** si hay que elegir
uno solo para esta semana: es el que más sufrimiento diario elimina por unidad de esfuerzo.

---

### W5 — Fiabilidad del canal Meta

**Problema:** cinco defectos independientes en el webhook y en el envío.

1. **Firma obligatoria.** `_verify_meta_signature` (`main.py:1101-1107`) devuelve `True` cuando
   `META_APP_SECRET` está vacío. `config.py:71-77` lo detecta y emite un warning que dice, textualmente,
   *"cualquiera puede falsificar mensajes de WhatsApp"* — y arranca igual. Con el bot como columna vertebral
   del producto, un POST anónimo a `/webhook` puede cerrar auditorías, marcar desvíos como resueltos y
   disparar notificaciones a encargados. **Cambio: `validate()` (`config.py:60`) falla el arranque si falta
   el secreto.** Es una línea. No pude verificar si la variable está seteada en Railway; si lo está, el
   cambio es gratis y previene la regresión.

2. **Procesar el batch completo.** `main.py:1143` hace `msg = messages[0]` y descarta el resto. Meta
   agrupa mensajes en un mismo `entry.changes[0].value.messages` cuando llegan juntos, cosa habitual con un
   auditor que manda tres fotos seguidas. Hoy se procesa una y **dos se pierden en silencio** (`return
   {"status":"ok"}` en `:1236` le confirma a Meta que se recibió todo, así que ni siquiera hay reintento).
   Además solo se mira `entry[0]` (`:1131`) y `changes[0]` (`:1136`). Cambio: iterar los tres niveles,
   procesando en orden y con el `_claim_message_for_processing` que ya existe por mensaje.

3. **Consumir `statuses`.** `main.py:1139-1141`: si el payload no trae `messages`, se retorna con un
   `logger.debug` que dice "might be status update". Los eventos `sent/delivered/read/failed` de Meta se
   descartan. Consecuencia práctica: el sistema **no sabe si sus notificaciones llegaron**. Un encargado
   con el número mal cargado en `sucursales.tel_responsable` nunca recibe nada y nadie se entera: los
   `send_text` retornan `True` si Meta acepta el request (`meta_client.py:146-156`), que no es lo mismo que
   entrega. Cambio: persistir `statuses` en una tabla `whatsapp_entregas` y alertar sobre `failed`,
   especialmente los códigos 131047 (ver punto 4) y 131026 (número no en WhatsApp).

4. **Modelar la ventana de 24 horas.** Todo el sistema notifica con `send_text`, es decir mensajes de
   sesión de forma libre. Meta solo los entrega si el destinatario escribió en las últimas 24h. Los
   emisores afectados son todos los proactivos: `remind_responsable_desvios_pendientes` (`main.py:1617`,
   cron 13:00 UTC diario), `remind_sla_auditor_revision` (`:1584`), `check_overdue_gestion` (`:1539`),
   `daily_summary_job` (`:1511`), y `_notify_responsable_desvios_pendientes`
   (`audit_handlers.py:120`). Un encargado que no escribe hace tres días **no recibe ninguno de esos
   recordatorios**, y hoy eso es invisible porque nadie mira los `statuses` (punto 3).

   `send_template` existe y está bien implementado (`meta_client.py:256-319`), con soporte de
   `body_params` y botones. Tiene **un solo llamador en todo el repo**: la activación de campañas
   (`main.py:759`), cuyo propio log admite que el template *"probablemente no está aprobado aún en Meta"*
   (`main.py:765-768`). El docstring de `meta_client.py:266-269` incluso lista las cinco plantillas que
   producción necesita.

   Cambio en dos partes: (a) aprobar en Meta Business Manager las plantillas de recordatorio; (b)
   introducir una función `notificar(telefono, plantilla, params, texto_fallback)` que consulte la última
   entrada del auditor/encargado y elija plantilla o texto libre según la ventana. Sin (a) esto no se puede
   hacer — es trabajo de configuración, no de código.

5. **El `finally` que puede reprocesar.** `main.py:1242-1244` libera el claim si el procesamiento no
   terminó bien. Pero el `except` de `:1237` ya devolvió `{"status":"error"}` con HTTP 200, así que Meta no
   reintenta. Resultado: el claim se libera y nadie reintenta. Ese `finally` solo sirve si el endpoint
   devuelve un 5xx. Decidir cuál de las dos semánticas se quiere y aplicarla; hoy tiene la mitad de cada
   una.

**Riesgo:** medio. El punto 1 puede tirar el servicio abajo si la variable no está seteada — mitigable
verificando Railway antes. El punto 4 depende de aprobaciones de Meta que pueden demorar días.

---

### W6 — Partir `router.py` (6.937 líneas) y unificar el acceso a Claude

**Criterio de partición: por dominio conversacional, no por tipo de artefacto.** Partir en
"handlers/models/utils" reproduce el problema con más archivos. El corte natural ya está insinuado en la
propia estructura de `_handle_message_locked` (`router.py:282-374`), donde los estados se agrupan por
familia.

**Destino propuesto** (líneas aproximadas medidas sobre el archivo actual):

| Módulo nuevo | Contenido | Origen |
|---|---|---|
| `conversation/router.py` (~200) | El resolvedor de W3 y el dispatch | `router.py:56-390` |
| `conversation/encargado.py` (~450) | Flujo del encargado | `router.py:408-560` |
| `conversation/campanias.py` (~450) | Flujo de campañas | `router.py:566-850` |
| `conversation/recolector.py` (~700) | Recolección multi-mensaje de respuestas | `router.py:968-1760` |
| `conversation/perfumeria_legacy.py` (~2.400) | Todo el flujo v1 de perfumería | `router.py:2407-4820` |
| `conversation/auditoria_bloques.py` (~2.100) | Flujo guiado por bloques + stock + compromisos | `router.py:4820-6937` |
| `llm.py` (~250) | **Todo** acceso a Claude | `parser.py` completo + `router.py:4334-4416` |

**Orden de ejecución**, de menor a mayor riesgo:

1. `llm.py` primero. Es el corte más limpio y el que más duplicación elimina: siete copias del
   fence-stripping (E1.3) colapsan en cero, porque el módulo nuevo usa `output_config.format` con un
   esquema JSON en lugar de pedirle a Claude que "responda SOLO JSON" y después parsear a mano. Se puede
   hacer sin tocar `router.py` más que en los imports.
2. `campanias.py` y `encargado.py`: dominios autocontenidos, sin superposición con auditoría.
3. `recolector.py`: acoplado a `respuesta_pregunta`, pero con frontera clara.
4. `perfumeria_legacy.py` y `auditoria_bloques.py` al final, porque son los que más comparten helpers.

**Sobre el endurecimiento del parser** (que va dentro de `llm.py`):

- La afirmación "sin reintentos" hay que matizarla: el SDK de Anthropic **ya reintenta automáticamente**
  429, 5xx, 408, 409 y errores de conexión, con backoff exponencial y `max_retries=2` por defecto. Lo que
  no existe es reintento ante **JSON malformado**: `parser.py:151-153` captura `JSONDecodeError` y devuelve
  `None` inmediatamente, y quien lo llama interpreta ese `None` como "no hay hallazgos". Un error de
  formato se vuelve indistinguible de un resultado vacío.
- `response.content[0].text` (`parser.py:113`, `186`, `263`, `354`, `424`, `496`; `router.py:4394`) asume
  que el primer bloque es texto. Con el modelo actual y sin `thinking` configurado eso se cumple, pero es
  una suposición no verificada que rompe en el momento en que alguien active thinking. Lo correcto es
  `next(b.text for b in response.content if b.type == "text")`.
- El modelo configurado es `claude-sonnet-4-6` (`parser.py:25`). Es un ID válido y el modelo sigue activo;
  no está roto. Pero es generación anterior: los targets actuales son `claude-sonnet-5` (mismo escalón, más
  capaz) o `claude-opus-5`. Migrar tiene una consecuencia concreta a considerar: Sonnet 5 usa un tokenizer
  nuevo (~30% más tokens para el mismo texto), lo que importa acá porque `_build_system_prompt`
  (`parser.py:35-90`) inyecta el catálogo completo de sucursales y áreas en cada llamada.
- Ese `_build_system_prompt` además hace **dos queries a la base en cada parseo**
  (`parser.py:38-39`) y produce un prompt que cambia con el contenido de la BD. Sin `cache_control` en
  ningún lado, cada mensaje del auditor paga el catálogo completo a precio de entrada nueva. Cachear el
  catálogo en memoria con TTL y agregar un breakpoint de prompt caching es un cambio de pocas líneas con
  ahorro directo.

**Riesgo:** medio para `llm.py` (cambia el formato de respuesta del modelo, hay que revalidar contra casos
reales), alto para los dos módulos grandes de auditoría. **Este movimiento no debería hacerse antes que
W1-W4**: partir un archivo no arregla ningún defecto de producto, y los seis primeros meses de beneficio
son de mantenibilidad, no de confiabilidad.

---

## Tabla de movimientos

| ID | Movimiento | Impacto | Esfuerzo | Riesgo | Depende de |
|----|-----------|---------|----------|--------|------------|
| W1 | Persistir la sesión v2 en Postgres (`sesiones_whatsapp`) usando `to_dict`/`from_dict`, conectar `is_expired` a un job real y avisar al auditor cuando su sesión vence | Alto | Medio | Bajo | B (runner de migraciones, esquema SQL versionado) |
| W2 | Cerrar el contrato C: subir a Storage los bytes ya descargados en `handle_bloque_evidence`, transcribir audio con `transcribe_bytes`, y llenar `Reporte.foto_url` desde `storage_path` | Alto | Bajo | Bajo | F (consumo de URLs firmadas), B (política de buckets) |
| W3 | Un único resolvedor de conversación + separación formal de los tres dominios (auditoría v2 / encargado / legacy) + invariante de exclusión mutua entre `sesiones_whatsapp` y `conversaciones` | Alto | Alto | Medio | — |
| W4 | Endurecer la entrada del auditor: menú completo de sucursales, matcheo exacto en decisiones destructivas, confirmación antes de crear desvíos, salida del estado `DONE`, y la invariante "ningún handler se calla" | Alto | Medio | Bajo | — |
| W5 | Fiabilidad del canal Meta: firma obligatoria, procesar el batch completo, consumir `statuses`, y modelar la ventana de 24h con plantillas aprobadas | Alto | Medio | Medio | B (tabla `whatsapp_entregas`); externo: aprobación de plantillas en Meta |
| W6 | Partir `router.py` por dominio conversacional y extraer `llm.py` con structured outputs, prompt caching y modelo actual | Medio | Alto | Medio | W3 |

**Orden recomendado de ejecución:** W4 → W2 → W1 → W5 → W3 → W6.
W4 primero porque es el mayor alivio por unidad de esfuerzo y no depende de nadie. W2 antes que W1 porque
la evidencia que se está perdiendo hoy no se recupera después. W3 y W6 al final porque son refactors
grandes que se benefician de tener el resto ya estable.

---

## Nota de trazabilidad

Todas las citas de este documento se verificaron leyendo el código en la rama `master` al 2026-08-05.
Las tres cosas que **no** pude verificar y que declaro explícitamente:

1. **Cuántas réplicas corre el servicio en Railway.** No hay `railway.json`, `Procfile` ni `nixpacks.toml`
   en el repo; el `Dockerfile` solo fija `uvicorn main:app` sin `--workers`. La gravedad de E2 cambia según
   la respuesta.
2. **Si `META_APP_SECRET` está seteado en producción.** Solo puedo ver que el código tolera su ausencia
   (`config.py:71-77`, `main.py:1104-1105`).
3. **Si alguna de las cinco plantillas de Meta listadas en `meta_client.py:266-269` está aprobada.** El
   log de `main.py:765-768` sugiere que al menos `campana_nueva_sucursal` no lo estaba cuando se escribió.

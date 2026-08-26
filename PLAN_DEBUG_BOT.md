# Plan de debug y hardening del bot de WhatsApp

> **Fecha:** 2026-08-26. Escrito tras reproducir el bug en local y una auditoría de 3 expertos
> (concurrencia asyncio, ruteo conversacional, observabilidad SRE).
> **Estado del repo:** nada de esto está implementado todavía. Nada pusheado.
> **Contexto de negocio:** hay auditoras trabajando en producción; los deploys se coordinan.

---

## 1. Qué está roto (dos fallas distintas, síntomas parecidos)

### Falla A — Deadlock por lock no reentrante (determinística, reproducida)

`ConversationRouter` tiene un `asyncio.Lock` por teléfono. `handle_message()` (`router.py:196`)
lo toma y llama a `_handle_message_locked()`. Adentro, en `router.py:296` y `router.py:303`,
se llama a `self.handle_perfumeria_audit(...)`, que en `router.py:223-225` **vuelve a tomar el
mismo lock**. `asyncio.Lock` no es reentrante → espera para siempre.

**Disparador real:** cuando el usuario toca un botón, WhatsApp manda el **id** del botón como
texto (`main.py:1123-1129`). El chequeo de `V2_TRIGGERS` (`router.py:299-302`) corre **antes**
del ruteo por estado, así que cualquier id que coincida con un trigger secuestra el flujo.

Colisiones confirmadas (id de botón vs. trigger de texto):

| id del botón | dónde se manda | trigger que lo intercepta | efecto |
|---|---|---|---|
| `auditar` | `router.py:1142` (menú principal) | `V2_TRIGGERS` (`:301`) | **deadlock en cada auditoría** |
| `perfumeria` | `router.py:1461` (alcance de campaña) | `V2_TRIGGERS` (`:301`) | **deadlock al elegir "Con perfumería"** |
| `tour` | `router.py:1144` (menú principal) | `:314` | no rompe hoy (ambas ramas hacen lo mismo), pero saltea el handler del menú |

Verificado además: **esta es la única re-entrada del lock en todo el repo** (barrido exhaustivo,
`audit_handlers.py` no llama al router).

### Falla B — El event loop se congela entero (intermitente, afecta a TODOS a la vez)

`supabase-py` es **sincrónico** y se lo llama desde handlers `async def` sin aislarlo.
Verificado: **cero** `run_in_executor` / `asyncio.to_thread` en todo el repo. Con un solo worker
de uvicorn (`Dockerfile:24`), **cada consulta congela el proceso completo**.

- ~10-12 round-trips bloqueantes por mensaje entrante (en los logs de producción se cuentan 7
  antes de llegar siquiera al handler, **3 de ellos duplicados** — la identidad se resuelve 2-3
  veces: `main.py:1157` + `router.py:268` + `get_encargado_by_phone`).
- `supabase_manager.py:1825,1858,1864` — `get_sesion` hace `time.sleep(0.5)` × 5 reintentos =
  **2,5s de bloqueo duro NO cancelable**, en el camino caliente.
- 14 jobs de APScheduler en el **mismo loop** (`main.py:393-500`), uno cada 30s.
- 2 full-table-scans por mensaje sobre `conversaciones` (`supabase_manager.py:262` y `:324`,
  `select("*")` sin `.eq()`, filtrando en Python).

Con el timeout actual de 15s × 10-12 llamadas, un mal momento de red = **2-3 minutos con todo
el proceso muerto y sin un solo error en el log**.

### Por qué los parches ya desplegados no alcanzan

Medido con test (`asyncio.wait_for(90s)` de `router.py:198` y `:227`):

| Escenario | Comportamiento real hoy |
|---|---|
| Mensaje que causa el deadlock | Se recupera, pero **a los 90s** |
| Mensaje siguiente encolado | **Sin protección**: el `async with lock` está FUERA del `wait_for` |
| Congelamiento por I/O bloqueante | **No lo cubre**: `wait_for` no puede cancelar una llamada sincrónica ya empezada |

El cambio de timeout de Supabase (120s→15s) sí reduce el peor caso de la Falla B, pero no la elimina.

---

## 2. Plan de ejecución

### DEPLOY 1 — urgente, quirúrgico, bajo riesgo

Objetivo: que el bot deje de colgarse. Cambios chicos y acotados.

**1.1 Romper la re-entrada del lock** · `router.py:215-249`
Extraer el cuerpo de `handle_perfumeria_audit` a un `_handle_perfumeria_locked(payload, meta_client)`
**sin lock**. `handle_perfumeria_audit` queda solo como entrypoint de `main.py:1180` (toma lock →
llama al nuevo método). `_handle_message_locked` (`:296` y `:303`) llama a `_handle_perfumeria_locked`
directamente, ya que el lock lo tiene el que la llamó.

**1.2 Renombrar los ids de botón que colisionan** · `router.py:1142-1144`, `router.py:1457-1462`
- `auditar` → `menu_auditar`
- `tour` → `menu_tour`
- `campania` → `menu_campania` (por consistencia)
- `perfumeria` → `alcance_perfumeria`; y por prolijidad `todas`/`cat_a`/`cat_b`/`cat_c`/`elegir`
  → `alcance_*`
Actualizar los `if choice == ...` correspondientes en `_handle_auditor_eligiendo_modulo` y
`_handle_auditor_campania_alcance`. **Regla nueva a respetar de acá en adelante: ningún id de
botón puede ser una palabra que el dispatcher chequee como texto libre.**

**1.3 Timeout en la ADQUISICIÓN del lock** · `router.py:196` y `:223`
Reemplazar `async with lock:` por:
```python
try:
    await asyncio.wait_for(lock.acquire(), timeout=15)
except asyncio.TimeoutError:
    logger.error(f"No se pudo tomar el lock de {payload.telefono} en 15s (locked={lock.locked()})")
    await meta_client.send_text(payload.telefono, "Estoy con otro mensaje tuyo, probá en unos segundos.")
    return "lock_acquire_timeout"
try:
    ...
finally:
    lock.release()
```

**1.4 Escape universal** (crítico para soporte) · `router.py` + `audit_handlers.py`
Hoy **no hay forma de que un usuario se destrabe solo**:
- Con sesión v2 viva, `main.py:1179` ni pasa por el router; `audit_handlers.py:390+` no tiene rama
  para "hola", y `cancelar` solo funciona en 6 estados (`audit_handlers.py:411-418`).
- `handle_encargado_message` (`router.py:559-599`) rutea puro por estado, sin saludo ni cancelar.
- `_handle_campania_esperando_evidencia` (`router.py:1005`) y `:854` rechazan **todo** texto.
Agregar un chequeo al tope de las **tres** entradas (`_handle_message_locked`,
`AuditConversationHandler.handle_message`, `handle_encargado_message`): si el texto es
`hola`/`inicio`/`cancelar`/`salir` → borrar sesión v2, poner conversación en `IDLE`, mostrar el menú.

**1.5 Log de entrada/salida con duración** · `main.py`, endpoint `webhook` (~1041-1199)
Ya existe `correlation_id`. El `logger.info` de resultado (`:1189`) está en el camino feliz: si se
cuelga, **no sale nada**. Mover/duplicar al `finally` (`:1196`):
```python
logger.info(f"[{cid}] FIN phone={telefono} dur={time.monotonic()-t0:.2f}s result={result}")
```

**1.6 Watchdog por mensaje** · `main.py`, endpoint `webhook`
`asyncio.create_task()` que duerme 20s y, si el mensaje sigue vivo, loguea
`WARN [cid] LENTO >20s phone=... locks_tomados=N`. Cancelarlo en el `finally`. Es lo que hace
visible el cuelgue **mientras pasa**.

**1.7 `/health` que detecte este caso** · `main.py:512`
Hoy es un `return` estático: ante un deadlock por-teléfono el server responde normal → **no
detecta nada**. Agregar `event_loop_lag`, `locks_held`, `oldest_lock_age_s`, y devolver **503 si
`oldest_lock_age_s > 120`**.
⚠️ **Railway ignora el `HEALTHCHECK` del Dockerfile** (no hay `railway.json`). Hay que setear
`healthcheckPath=/health` en el dashboard de Railway **en el mismo deploy**.

**1.8 Config faltante ruidosa** · `config.py:64-81` + `main.py:387`
`meta_app_id` no se valida: sin él, `check_webhook_health` (`main.py:1201`) hace `return` mudo para
siempre. Loguear un banner al arrancar: `CONFIG: META_APP_ID=NOT SET → webhook health check DESACTIVADO`.

---

### DEPLOY 2 — después de validar el 1 (más invasivo)

**2.1 Sacar Supabase del event loop** · `supabase_manager.py`
Envolver las llamadas en `asyncio.to_thread` (o convertir `SupabaseManager` a async). Es el arreglo
de fondo de la Falla B. Toca muchos call sites → merece su propio deploy y su propia validación.

**2.2 Eliminar `time.sleep` del camino caliente** · `supabase_manager.py:1825,1858,1864`
Reemplazar por reintentos async, o directamente sacarlos.

**2.3 Filtrar las consultas de `conversaciones`** · `supabase_manager.py:262` y `:324`
Agregar `.eq("telefono", telefono_normalizado)` + índice. Normalizar el teléfono al escribir para
que el `.eq()` matchee siempre.

**2.4 Resolver la identidad una sola vez por mensaje**
Pasar el `whatsapp_user` ya resuelto en `main.py:1157` al router, en vez de que `router.py:268`
lo vuelva a buscar. Ahorra 3-6 round-trips bloqueantes por mensaje.

---

### PENDIENTE (sin urgencia, anotado para no perderlo)

- **PDF y miniaturas en el loop**: `audit_handlers.py:2283` (reportlab) y `supabase_manager.py:1186-1189`
  (PIL) congelan a todos los usuarios al cerrar una auditoría.
- **Los jobs del scheduler escriben estado sin el lock**: `main.py:1240,1307,1318,1405`. Pueden pisar
  una conversación en curso.
- **Texto libre secuestrado**: nombrar una campaña "Perfumería", "Tour" o "Desvíos" (`router.py:1281`,
  `:1371`) descarta el borrador o deadlockea.
- **`router.py:300` no normaliza acentos** (solo `.lower().strip()`), a diferencia de
  `_normalize_intent_text` (`router.py:1815`). Inconsistente.
- **Ramas muertas**: `SELECCIONANDO_ESCUADRON` (`router.py:358`) y `SELECCIONANDO_SUCURSAL` (`:366`)
  nunca se escriben, solo se leen. `router.py:293-296` es código muerto (`main.py:1178` ya desvía antes).
- **Doble rol**: un teléfono que sea auditor y encargado a la vez toma la rama auditor (`router.py:272`)
  y cae en "⚠️ Estado desconocido" (`:480`).
- **`AUDITOR_ELIGIENDO_MODULO` no está** en `AUDITOR_CAMPANIA_ESTADOS_FLUJO` (`main.py:1376-1385`) →
  se queda sin job de timeout.

---

## 3. Tests de regresión (escribir junto con el Deploy 1)

Archivo nuevo `test_router_deadlock.py`, estilo `test_respuesta_recolectora.py` (fakes, sin DB real).
Hay una reproducción ya funcionando en el scratchpad de la sesión que sirve de base.

1. **Deadlock**: `handle_message` con `contenido="menu_auditar"` y con `"auditar"` responde en < 5s
   (hoy con `"auditar"` cuelga).
2. **Serialización**: dos `handle_message` concurrentes del mismo teléfono se serializan; de teléfonos
   distintos, corren en paralelo.
3. **Colisiones**: test parametrizado que recorre **todos** los ids de botón que manda el bot y
   verifica que ninguno esté en los sets de triggers de texto del dispatcher. Este es el que evita
   que la clase entera de bug vuelva.
4. **Escape universal**: desde cada estado de `ConversationState`, mandar "hola" devuelve al menú.

---

## 4. Checklist de verificación post-deploy (~10 min, en orden)

1. Logs de Railway: banner de config + `Background jobs started`.
2. `curl -s $URL/health | jq` → `locks_held: 0`, `event_loop_lag` < 50ms, HTTP 200.
3. `GET /webhook?hub.mode=subscribe&hub.verify_token=$META_VERIFY_TOKEN&hub.challenge=ping` → devuelve `ping`.
4. Mensaje real desde un teléfono de prueba → confirmar que salen **INICIO y FIN con duración** y el
   mismo `correlation_id`.
5. **Reproducir el bug viejo**: tocar "🔍 Auditar". Debe abrir la lista de sucursales en < 5s.
6. **Segunda colisión**: crear una campaña y elegir "Con perfumería" en el alcance. Debe avanzar al plazo.
7. **Escape**: escribir "hola" en medio de una auditoría → debe volver al menú.
8. `curl /health` de nuevo → `locks_held` volvió a 0.

**Rollback**: Railway → Deployments → *Redeploy* del build anterior (1-2 min).
**Criterio de aborto**: `/health` en 503, o `locks_held` que no baja a 0.

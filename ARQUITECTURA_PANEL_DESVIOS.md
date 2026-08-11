# Arquitectura — Panel de desvíos, mensajería al responsable y fichas

> Continuación de [`ARQUITECTURA_DESVIOS_CAMPANIAS.md`](ARQUITECTURA_DESVIOS_CAMPANIAS.md), que definió el
> ciclo de revisión (Fase 1) y el módulo de campañas. Este documento cubre lo que quedó sin resolver:
> **cómo se estructura el panel de desvíos, cómo le hablamos al responsable, y dónde vive lo que responde.**

Fecha: 2026-08-10 · Rama: `master`

---

## 1. Por qué

El ciclo de desvíos funciona de punta a punta salvo por un detalle que lo vacía de sentido: **la conversación
es de una sola vía, y la vía rota es la del auditor**. El responsable puede responder por WhatsApp y su
respuesta aterriza bien; el auditor puede escribir en el panel y eso no llega a ningún lado.

A eso se suma que "revisar" significa dos cosas distintas en dos lugares distintos del panel, y que la ficha
PDF de la auditoría y los desvíos que esa auditoría generó son dos mundos que no se conocen.

---

## 2. Hallazgos del estado actual

Todos verificados contra el código, no inferidos.

### 2.1 El chat del panel no llega a WhatsApp

`POST /api/gestion/{id}/mensajes` ([main.py:515](main.py#L515)) inserta en `desvio_eventos` con
`tipo='mensaje'` y termina ahí. No hay ninguna llamada a `MetaClient`.

Consecuencia: cuando un auditor escribe en el chat de un desvío, el responsable **nunca se entera**. Solo lo
vería entrando al panel web — que es exactamente lo que no hace, porque el canal es WhatsApp
(decisión fijada en [`docs/analisis/00-cimientos.md`](docs/analisis/00-cimientos.md) §2.1).

La dirección inversa **sí funciona**: `_handle_encargado_respuesta` ([router.py:893](router.py#L893)) guarda
foto (a Storage, con URL firmada) o texto como evento del timeline, pasa la gestión a `En_revision` y notifica
a los auditores.

### 2.2 El botón para avisarle al responsable no existe

`POST /api/notificar-encargado` está implementado ([main.py:487](main.py#L487)) y no lo llama **ningún**
archivo del frontend. Endpoint huérfano desde su creación.

### 2.3 Los recordatorios se caen en silencio

`remind_responsable_desvios_pendientes` (cron 10:00 ART, cada 3 días) envía con `send_text`
([main.py:1584](main.py#L1584)). Fuera de la ventana de 24h de Meta, `send_text` no se entrega. El job loguea
un warning y sigue.

`send_template` existe en `meta_client.py:256` y se usa **en un solo lugar**: campañas
([main.py:745](main.py#L745)).

**El sesgo es el problema**: la ventana está abierta para el responsable que ya contesta seguido, y cerrada
para el que hace semanas que no aparece. Sin plantilla, el sistema funciona con quien ya coopera y falla
callado con quien no — al revés de lo que necesita un sistema de auditoría. Ya estaba anotado como riesgo #2
en `ARQUITECTURA_DESVIOS_CAMPANIAS.md` §3.

### 2.4 Colisión de nombre: "revisar" significa dos cosas

- Pestaña **"Por revisar"** (`/desvios?v=revision`) → `desvios_borrador`: hallazgos que propuso la IA y
  esperan aprobación humana para *convertirse* en gestión.
- Estado **`En_revision`**, escondido dentro de la pestaña "En seguimiento" → el responsable ya mandó su
  corrección y espera que el auditor la apruebe o rechace.

Son dos bandejas de entrada distintas con el mismo nombre, y una de las dos está enterrada. `DesviosGestion`
ya se autofiltra a `En_revision` al montar ([DesviosGestion.tsx:621](frontend/src/pages/DesviosGestion.tsx#L621)),
lo cual confirma que en la práctica es una bandeja aparte disfrazada de filtro.

### 2.5 Ficha PDF y desvíos, desconectados

`audit_fiches.id_reporte` es FK a `reportes.id`; no hay ninguna relación con `gestion`.
`DesvioDetail.tsx` no menciona fichas ni una vez.

No se puede responder "¿cuánto de esta auditoría se resolvió?".

### 2.6 El teléfono del responsable está congelado

`gestion.tel_responsable` es una copia tomada al crear el desvío, y es por ahí que agrupa el job de
recordatorio (`get_gestiones_pendientes_recordatorio`, [supabase_manager.py:882](supabase_manager.py#L882)).

Desde `etapa-21`, la fuente de verdad de identidad es `usuarios_whatsapp`. Si cambia el responsable de una
sucursal, los desvíos viejos siguen pingueando al teléfono anterior.

---

## 3. Decisiones tomadas

| Decisión | Elegido |
|---|---|
| Chat del panel → WhatsApp | **Sí, siempre.** Dentro de la ventana, texto libre; fuera, plantilla. |
| Plantillas de Meta | **Una sola, genérica** (`farmaaudit_novedades`), que cubre los tres casos. |
| Estructura del panel | **Por turno** — quién tiene que actuar, no en qué estado está. |
| Ficha ↔ desvíos | **Ficha como contenedor**, navegable en ambos sentidos. |

---

## 4. Mensajería

### 4.1 Regla de entrega

`POST /api/gestion/{id}/mensajes` con `origen='auditor'` pasa a entregar por WhatsApp además de escribir el
evento:

| Ventana de 24h | Qué se manda |
|---|---|
| Abierta | `send_text` con el mensaje completo |
| Cerrada | `send_template('farmaaudit_novedades', …)` — avisa e invita a responder; su respuesta reabre la ventana y a partir de ahí se conversa libre |

### 4.2 Saber si la ventana está abierta

Columna nueva `usuarios_whatsapp.ultimo_mensaje_entrante_at`, que el webhook actualiza en **cada** mensaje
entrante (un solo `update` en el punto donde ya se resuelve identidad, `main.py`).

Se descarta inferirlo de `desvio_eventos`: sería frágil y solo vería los mensajes atados a un desvío, no la
conversación completa (auditorías, campañas) que también abre la ventana.

### 4.3 Que un fallo se vea

Cada envío saliente registra su resultado en `desvio_eventos.metadata.entrega`:

- `enviado` — Meta lo aceptó
- `fallido` — Meta lo rechazó (se guarda el motivo)
- `sin_ventana` — no había ventana y la plantilla tampoco pudo entregarse

El chat del panel muestra ese estado al lado de cada mensaje. **Esto es lo que evita repetir el defecto
actual**: hoy el fallo solo existe en los logs de Railway.

### 4.4 Resolución del teléfono

Siempre en vivo desde `usuarios_whatsapp` — el responsable **activo** de `gestion.id_sucursal` — nunca desde
`gestion.tel_responsable`, que queda como registro histórico de a quién se le asignó originalmente.

Si la sucursal no tiene responsable activo cargado, el panel lo dice explícitamente y ofrece el link a
Administración → Usuarios WhatsApp. Nunca falla en silencio.

### 4.5 Plantilla a registrar

Categoría **UTILITY** (no Marketing: menor costo, sin opt-in, menos riesgo de rechazo).

- **Nombre:** `farmaaudit_novedades` · **Idioma:** `es_AR`
- **Cuerpo:**
  ```
  Hola {{1}}, tenés {{2}} novedad(es) pendientes de tu sucursal {{3}} en FarmaAudit. Respondé este mensaje para verlas y enviar tu respuesta.
  ```
  `{{1}}` responsable · `{{2}}` cantidad · `{{3}}` sucursal
- **Botón** (quick reply, opcional): `Ver novedades`

Reemplaza además el `send_text` roto del job de recordatorio (§2.3).

---

## 5. Bandejas por turno

`/desvios` pasa de dos pestañas a tres, cada una con contador:

| Bandeja | Contiene | Acción del auditor |
|---|---|---|
| **Requiere tu decisión** (default) | `desvios_borrador` pendientes + gestiones `En_revision` | Aprobar borrador *crea* gestión · Aprobar corrección *cierra* |
| **Esperando al responsable** | `Abierta`, `En_proceso`, `Vencida` | Mensajear, ajustar plazo |
| **Cerrado / terceros** | `En_gestion_terceros`, `Resuelta`, `Cerrada` | Consulta |

Dentro de "Requiere tu decisión" los dos grupos van visualmente separados, porque la acción no es la misma.

**Costo de implementación bajo**: `Desvios.tsx` ya monta dos paneles embebidos, y `DesviosGestion` ya se
autofiltra por estado. Es reasignar qué panel va en qué pestaña y pasarle el filtro por prop — no reescribir
los paneles.

---

## 6. Ficha como contenedor

FK nueva: `gestion.ficha_id → audit_fiches(id)`, poblada al crear la ficha (en ese momento ya se conocen las
gestiones de la sesión — ver `audit_database.save_audit_to_database` y `audit_fiches_manager`).

Habilita las dos navegaciones que hoy no existen:

- **Ficha → desvíos**: "3 de 7 desvíos resueltos" — el avance real de esa auditoría.
- **Desvío → ficha**: de qué auditoría salió, con su PDF y su puntuación.

Las auditorías históricas quedan con `ficha_id = null` y la UI degrada a "auditoría no vinculada". No se
adivina con heurísticas de fecha + sucursal: un match equivocado es peor que un dato ausente.

---

## 7. Orden de trabajo

La plantilla tiene plazo externo (aprobación de Meta), así que se arranca por lo que no depende de ella.

| # | Bloque | Depende de |
|---|---|---|
| **0** | Dar de alta `farmaaudit_novedades` en Meta Business Manager | — (hacer ya, corre en paralelo) |
| **1** | Bandejas por turno | — |
| **2** | Ficha como contenedor (migración + FK + UI) | — |
| **3** | `ultimo_mensaje_entrante_at` + resolución de teléfono en vivo + estado de entrega visible | — |
| **4** | Chat del panel → WhatsApp; reemplazo del `send_text` del job de recordatorio | 0, 3 |

El bloque 3 se puede construir y probar entero sin la plantilla: dentro de la ventana de 24h ya se entrega con
`send_text`. La plantilla solo agrega el caso "ventana cerrada".

---

## 8. Verificación

**Bandejas**: un desvío recién creado aparece en "Esperando"; el responsable responde por WhatsApp y salta a
"Requiere tu decisión"; el auditor aprueba y cae en "Cerrado". Los tres contadores cierran contra
`select estado, count(*) from gestion group by estado`.

**Mensajería** (necesita un teléfono de prueba):
1. Responsable escribe al bot → auditor responde desde el panel → **le llega al WhatsApp**.
2. Esperar >24h sin que el responsable escriba → auditor escribe → llega la plantilla, no el texto.
3. Sucursal sin responsable activo → el panel avisa y no simula haber enviado.
4. Desactivar al responsable en Administración → el envío se detiene y lo informa.

**Ficha**: cerrar una auditoría con 2+ desvíos → la ficha lista esos desvíos → resolver uno → el contador de
la ficha pasa a "1 de 2".

**Regresión obligatoria**: la prueba de fuego del bot de [`HANDOFF.md`](HANDOFF.md) y los tests que se corren
directo (`python test_audit_hardening.py`, `test_verification_flow.py`, `test_imports.py`) — `pytest` no
funciona en este entorno.

---

## 9. Qué queda explícitamente afuera

- **Escalamiento por niveles** (día 0 responsable → +1 auditora → +2 coordinador), ya descrito en
  `ARQUITECTURA_DESVIOS_CAMPANIAS.md` §2.6. Depende de que la mensajería confiable exista primero.
- **Franjas horarias de envío** (13:30–16h / después de 20h). Aplica a campañas; para desvíos se evalúa
  después de medir si molesta.
- **Cola de estados por `(telefono, tipo_flujo)`** — el riesgo #1 del documento anterior: un encargado con
  desvío y campaña activos se pisa a sí mismo. No lo toca este módulo.
- **Retirar `gestion.tel_responsable`**. Se deja de usar para entregar, pero la columna queda como registro
  histórico.

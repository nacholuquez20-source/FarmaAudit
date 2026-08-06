# Cimientos compartidos — ronda de análisis de coherencia

> **Este documento es de lectura obligatoria y vinculante para los tres especialistas** (WhatsApp, Backend, Frontend).
> Fija las decisiones transversales para que nadie invente su propia respuesta. Si un especialista cree que una
> decisión de acá está mal, lo dice explícitamente en su sección E3 y lo justifica — no la ignora en silencio.

Fecha: 2026-08-05 · Rama: `master`

---

## 1. Por qué esta ronda

FarmaAudit funciona, pero creció por acumulación: cada módulo nuevo trajo su propia versión de conceptos que ya
existían. El síntoma medible es que **la misma regla de negocio está implementada tres veces en dos lenguajes**.

El costo no es estético. Cambiar el criterio de "sucursal en rojo" hoy exige tocar SQL, TypeScript y Python, y
acordarse de los tres. En la práctica se toca uno, y los otros dos quedan mintiendo.

**El norte de esta ronda es coherencia y confiabilidad, no features nuevas.**

---

## 2. Decisiones ya tomadas (no se re-discuten)

### 2.1 WhatsApp es el canal

El auditor y el encargado viven en WhatsApp. La app web es **panel de lectura y gestión** para dirección.

Consecuencias que los especialistas deben asumir como dadas:

- El bot deja de ser "una vía más de captura" y pasa a ser la **columna vertebral del producto**. Defectos que
  hoy son tolerables (sesiones en memoria, evidencia que caduca) pasan a ser defectos de producto.
- El formulario web de auditoría (`frontend/src/pages/AuditPerfumeriaV2.tsx` + sus seis componentes de apoyo)
  **queda en revisión de retiro**. Revisión, no ejecución: hay que fundamentarlo con uso real.
- Invertir en persistir y endurecer el flujo del bot está justificado aunque sea caro.

### 2.2 Fuentes únicas de verdad

| Dominio | Fuente única | Qué se retira |
|---|---|---|
| Estado de salud / semáforo | Vista SQL `sucursales_dashboard` | `computeBranchScore` y `resolveSemaforo` (`frontend/src/lib/api.ts:703,715`) |
| Captura de auditoría | Bot de WhatsApp | Formulario web (a fundamentar) |
| Tokens de diseño | Bloque `@theme` de `frontend/src/index.css` | `tailwind.config.ts`, `design-tokens.ts`, objetos `tokens` hardcodeados por página |
| Esquema de BD | Los archivos SQL del repo | El estado real que hoy solo vive en Supabase |

Los especialistas proponen **cómo** migrar hacia estas fuentes, no **si** hacerlo.

> **Corrección posterior (aplicada tras la Fase 2).** La versión original de esta tabla listaba también
> `determine_severity` (`audit_database.py:14`) entre lo que se retira. **Era un error de este documento**, y los
> especialistas de Backend y WhatsApp lo objetaron con razón (ver conflicto C1 en [`04-roadmap.md`](04-roadmap.md)).
> `determine_severity` no es un semáforo de sucursal: es el mapeo `score del bloque → severidad del desvío`, que
> se persiste en `reportes.severidad` / `gestion.severidad` y que la vista SQL **consume como input**. Retirarla
> en favor de la vista sería circular y dejaría al pipeline sin quién asigne severidad.
> **No se borra: se muda** a la base como definición única que Python invoca en vez de reimplementar.

### 2.3 Alcance del entregable

**Propuesta priorizada, sin tocar código.** Ningún archivo de código se modifica en esta ronda. El único
output es documentación en `docs/analisis/`.

**Refactors grandes están permitidos** en las propuestas si vienen con plan: partir `router.py` (6.937 líneas),
unificar el semáforo, introducir un runner de migraciones.

---

## 3. Glosario del dominio

Hoy `reportes`, `gestion`, `desvios_borrador` y `desvios_auditoria_perfumeria` se solapan conceptualmente. Este
es el significado canónico. Si un especialista encuentra código que usa un término con otro sentido, es un
hallazgo E1 (duplicación), no una excepción aceptable.

| Término | Significado canónico | Dónde vive |
|---|---|---|
| **Reporte** | El hallazgo crudo tal como se capturó. Una observación con foto, área y severidad. | tabla `reportes` (PK text de 12 chars) |
| **Gestión** | El hallazgo ya convertido en compromiso: tiene responsable, plazo y plan de acción. Es lo que se sigue hasta cerrar. | tabla `gestion` (PK `id_gestion` text) |
| **Desvío** | Uso ambiguo en el código: a veces significa reporte, a veces gestión. **Canónicamente = gestión abierta.** | — |
| **Evento** | Una entrada del timeline de una gestión (contacto, respuesta, evidencia, rechazo, cierre). | tabla `desvio_eventos` |
| **Ficha** | El PDF resumen de una auditoría completa, con su puntuación promedio. Alimenta el semáforo. | tabla `audit_fiches` |
| **Bloque** | Una de las cuatro dimensiones de la auditoría de perfumería: LIMPIEZA, STOCK, OFERTAS, BURBUJAS. | `gestion.bloque`, `BLOQUE_ORDER` en `audit_session.py` |
| **Sesión** | Una auditoría en curso por WhatsApp, con su estado y lo capturado hasta ahora. | `_sessions_cache` en memoria (v2) / tabla `conversaciones` (v1) |
| **Borrador** | Un desvío propuesto por la IA, esperando aprobación humana antes de volverse gestión. | tabla `desvios_borrador` |

**Términos muertos** (existen en el schema pero sin uso en código): `desvios_auditoria_perfumeria`,
`analisis_auditoria`.

---

## 4. Los cinco contratos entre capas

Cada contrato tiene una capa que lo **produce** y otras que lo **consumen**. Todo especialista que toque un
contrato debe declarar en su sección E3 qué necesita de las otras capas. **Este es el mecanismo que hace que
las tres propuestas se sumen en vez de chocar.**

### Contrato A — Identidad de sucursal

- **Produce**: el bot, al crear una ficha o un reporte. **Consume**: el front y la vista SQL.
- **Formato**: `SUC002` (text).
- **Estado: roto.** `audit_fiches.sucursal_id` es `VARCHAR(50) NOT NULL` **sin foreign key** a `sucursales(id)`
  (verificado en `migration_audit_fiches.sql:8`). Nada garantiza que el valor que escribe el bot exista en
  `sucursales`.
- **Síntoma observado**: `HANDOFF.md:35` reporta 25 sucursales apareciendo "Sin auditar" porque no hay filas en
  `audit_fiches` que matcheen esos `sucursal_id`. **Este contrato es la causa candidata número uno.**
- Nota: `audit_fiches.id_reporte` **sí** tiene FK a `reportes(id)`. La asimetría es sospechosa por sí sola.

### Contrato B — Estado de salud / semáforo

- **Produce**: la vista SQL `sucursales_dashboard`. **Consume**: front y bot.
- **Estado: triplicado en tres lenguajes con criterios incompatibles.**
  - SQL (`frontend/docs/sql/etapa-18-sucursales-dashboard.sql:73-84`): 4 estados
    `critica / atencion / ok / sin_datos`, con umbrales de puntuación 3.0 y 4.0 y de días 15 y 30.
  - TypeScript (`frontend/src/lib/api.ts:715`): 3 estados `rojo / amarillo / verde`, sin considerar puntuación
    ni antigüedad — solo conteos de desvíos. Más un score 0-100 propio en `api.ts:703` que resta 15 por vencido,
    12 por crítico activo y 3 por abierto.
  - Python (`audit_database.py:14`): 3 niveles `Alta / Media / Baja` derivados del score del bloque.
- Los tres responden preguntas parecidas con respuestas distintas. **Sobrevive el SQL.**

### Contrato C — Evidencia (foto y audio)

- **Produce**: el bot, al recibir media de WhatsApp. **Consume**: el front, al mostrarla.
- **Estado: roto.** El webhook nunca resuelve `media_url` — los TODOs de `main.py:1175-1186` siguen sin
  implementar. Consecuencia: las fotos de auditoría v2 existen **solo como `media_id` de Meta**, que caduca a
  ~30 días, y **nunca se suben a Supabase Storage**. La evidencia de las auditorías se evapora sola.
- Efecto colateral: todas las ramas de transcripción de audio condicionadas a `payload.media_url` están muertas
  (`router.py:1957, 4539, 4765, 4960, 5642`). En v2 el audio se guarda literalmente como
  `"[AUDIO] Sin transcripción"`.

### Contrato D — Desvío → gestión

- **Produce**: el bot, al cerrar una auditoría con hallazgos. **Consume**: el front, que los gestiona hasta cerrar.
- **Estado: funciona**, con dos grietas. `gestion.id_reporte` no tiene FK a `reportes(id)` (es texto suelto), y
  la creación en `main.py:965-1049` hace tres inserts secuenciales sin transacción: si falla el de `gestion`
  después de crear el `reporte`, queda un reporte huérfano.

### Contrato E — Permisos de módulo

- **Produce**: nadie. La lista está **duplicada literalmente** en Python y TypeScript, y divergió.
- **Estado: divergente y roto.** Verificado:
  - `main.py:135-142` conoce 6 módulos: `dashboard`, `gestion_desvios`, `revision_desvios`, `mis_desvios`,
    `sucursales`, `admin`.
  - `frontend/src/lib/permissions.ts:7-16` conoce 8: los 6 anteriores más `campanias` y `mis_campanias`.
- **Consecuencia concreta**: crear o editar un usuario de panel con el módulo `campanias` desde el front devuelve
  `HTTP 400 "Modulo invalido: campanias"`. La funcionalidad de campañas es inasignable.

### Contrato F — El reloj compartido

> **Agregado tras la Fase 2.** No estaba previsto: emergió al cruzar los hallazgos de Backend y Frontend, que
> habían visto cada uno una mitad distinta del mismo defecto (ver conflicto C3 en [`04-roadmap.md`](04-roadmap.md)).

- **Produce**: SQL, en zona horaria `America/Argentina/Buenos_Aires`. **Consume**: todos.
- **Estado: roto en tres relojes distintos.**
  - SQL usa TZ argentina explícita (`etapa-18-sucursales-dashboard.sql:31-33`).
  - Python compara `plazo_fecha` (columna `date`) contra `datetime.now(timezone.utc)`
    (`supabase_manager.py:866,871`) — marca una gestión como vencida a las 21:00 ART **del día anterior**, así
    que el responsable pierde el último día de plazo y el semáforo se pone en rojo antes de tiempo.
  - El navegador usa su hora local (`frontend/src/lib/utils.ts:115,126`), que coincide con la argentina solo
    mientras nadie abra el panel desde otra zona.
- **Regla**: *"hoy" se calcula una sola vez, en SQL, en hora argentina. Ninguna otra capa lo recalcula.*

---

## 5. Rejilla común de análisis

Los tres especialistas responden **las mismas seis preguntas** aplicadas a su capa. Mismas preguntas → salidas
comparables → roadmap fusionable.

**E1 — Duplicación.** ¿Qué lógica existe más de una vez, dentro de mi capa o entre mi capa y otra? Para cada
caso: cuál sobrevive y por qué.

**E2 — Estado que se pierde.** ¿Qué se guarda solo en memoria, solo en el navegador, o en ningún lado? ¿Qué pasa
exactamente cuando eso se cae?

**E3 — Contratos.** De los cinco contratos, ¿cuáles toco? Para cada uno: qué asumo de otra capa que hoy no está
garantizado, y qué necesito que la otra capa me dé.

**E4 — Falla silenciosa.** ¿Qué se rompe sin que nadie se entere? Excepciones tragadas, comportamiento
*fail-open*, datos demo, inserts que fallan y solo loguean.

**E5 — Superficie a borrar.** ¿Qué código, tabla, dependencia o archivo puede desaparecer? Menos superficie es
menos incoherencia futura. Verificar uso real antes de proponer un borrado.

**E6 — Propuesta.** De 3 a 6 movimientos, con dependencias explícitas hacia las otras dos capas.

---

## 6. Formato de entrega

Cada especialista escribe **`docs/analisis/0X-<capa>.md`** con las seis secciones E1-E6 en ese orden, y cierra
con esta tabla exacta (mismas columnas en los tres, para poder fusionarlas):

```markdown
| ID | Movimiento | Impacto | Esfuerzo | Riesgo | Depende de |
|----|-----------|---------|----------|--------|------------|
| W1 | ...       | Alto    | Medio    | Bajo   | B2, —      |
```

- **ID**: prefijo por capa (`W` WhatsApp, `B` Backend, `F` Frontend) + número.
- **Impacto / Esfuerzo / Riesgo**: Alto / Medio / Bajo.
- **Depende de**: IDs de otras capas, o `—`.

### Regla de trazabilidad

**Toda afirmación cita archivo y línea.** Se muestrean 5 citas por documento contra el código real; una cita que
no verifica invalida el hallazgo. Si algo no se pudo verificar, se dice explícitamente — no se rellena con
suposiciones plausibles.

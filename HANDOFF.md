# Handoff — Rediseño "Centro de Operaciones" del auditor

_Última sesión: 2026-08-05. Todo pusheado a `origin/master` (último commit `3d439c9`)._

## ⚠️ PRIMER PASO AL RETOMAR (obligatorio)

Correr esta migración en el **SQL Editor de Supabase** (es `CREATE OR REPLACE VIEW`, se pega y listo, no borra nada):

```
frontend/docs/sql/etapa-18-sucursales-dashboard.sql
```

Sin esto, el nuevo estado gris **"sin datos"** no aparece y las sucursales nunca-auditadas siguen saliendo en rojo (lógica vieja de la vista). Al correrla, el contador `25 críticas` se parte en `~16 críticas · ~9 sin datos` y el semáforo recupera señal.

> Nota: ya la corriste una vez en la sesión anterior, pero **volví a modificar la vista** (se agregó el estado `sin_datos`). Hay que correrla de nuevo.

## Qué se construyó (3 módulos nuevos + QA + design pass)

1. **Centro de Operaciones** — `/sucursales` ahora es un grid visual de tarjetas con semáforo (antes era una tabla editable, que se movió a `/sucursales/editar`).
   - `frontend/src/pages/SucursalesDashboard.tsx`
2. **Hub de Sucursal** — `/sucursales/:id` con pestaña **Resumen**: header de salud, acciones sugeridas (una abre WhatsApp con reclamo pre-armado), evolución de scores.
   - `frontend/src/pages/SucursalDetail.tsx`
3. **Panel "Hoy"** — `/hoy`, landing del auditor: to-do priorizado del día (vencidos, sin auditar +30d, perfumerías del mes, esperando revisión).
   - `frontend/src/pages/Hoy.tsx`

Todo se apoya en una sola vista SQL pre-calculada (`sucursales_dashboard`) con semáforo de **4 estados**: `critica / atencion / ok / sin_datos`. Cálculos de fecha en zona horaria Argentina. Helpers compartidos en `frontend/src/lib/utils.ts` (`whatsappLink`, `diasDesde`, `esMesActual`).

## Estado: verde

- `tsc --noEmit` y `npm run build` pasan.
- Probado en vivo con Playmwright (dev bypass): 3 pantallas renderizan sin errores de runtime, con datos reales.

## Observación de datos pendiente de confirmar

Las 25 sucursales aparecían "Sin auditar" → **no hay filas en `audit_fiches` que matcheen esos `sucursal_id`** (formato `SUC002`). Confirmar en Supabase si es que aún no se auditó, o si hay un desajuste `audit_fiches.sucursal_id` ↔ `sucursales.id`. (Es dato, no bug de código: sin ficha → el semáforo lo maneja bien.)

## Roadmap pendiente (del design review, opcional)

- **#5 — Agrupar el grid por zona** (esfuerzo medio; útil al crecer a 50+ sucursales).
- **Modo campo mobile** — las 3 sucursales más urgentes como tarjetas grandes con botones táctiles de 44px (la auditora usa esto en el celular en el auto).
- **Scoring por marca de perfumería** (del roadmap estratégico): reporte mensual de compliance por marca (Natura, Avon, Unilever, etc.) — tiene valor de monetización.

## Cómo levantar la app localmente

```bash
cd frontend
npm run dev          # http://localhost:5173
```
Para ver pantallas autenticadas sin login real: `VITE_ENABLE_DEV_BYPASS=true npm run dev` (entra como admin; ojo: las queries corren y traen datos reales de Supabase).

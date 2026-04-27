# FarmaAudit MVP Gestion

## Objetivo

Frontend operativo para supervisar sucursales, gestionar desvios, contactar responsables, registrar resolucion con evidencia y cerrar casos con trazabilidad.

## Stack

- React + TypeScript + Vite
- Tailwind CSS
- Supabase Auth + Supabase database
- Recharts para visualizacion

## Rutas Principales

- `/login`: autenticacion Supabase.
- `/dashboard`: supervision global, semaforo por sucursal, ranking critico y tendencia.
- `/desvios`: centro operativo con filtros y prioridad.
- `/desvios/:id`: detalle, contacto, timeline, resolucion y cierre.
- `/sucursales`: listado de sucursales.
- `/sucursales/:id`: detalle historico por sucursal.
- `/admin`: gestion basica de auditores.

## SQL Requerido

Ejecutar en Supabase SQL Editor en este orden:

1. `../supabase_setup.sql`
2. `docs/sql/etapa-2.sql`
3. `docs/sql/etapa-3.sql`

`etapa-2.sql` crea `desvio_eventos` para timeline.

`etapa-3.sql` habilita el estado `Resuelta` y permite updates operativos en `gestion`.

## Como Correr

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Configurar `frontend/.env.local`:

```env
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
```

## Validacion Tecnica

```powershell
npm.cmd run lint
npx.cmd tsc -p tsconfig.app.json --noEmit
npm.cmd run build
```

El MVP usa lazy loading de rutas para separar pantallas pesadas como dashboard y graficos.

## QA Manual

### Login

- Entrar a `/login`.
- Iniciar sesion con un usuario de Supabase.
- Confirmar redireccion segun rol.

### Dashboard

- Entrar a `/dashboard`.
- Confirmar KPIs.
- Confirmar semaforo por sucursal.
- Confirmar ranking critico.
- Confirmar tendencia de 30 dias.
- Probar `Refrescar`.
- Probar auto-refresh en 20s o 30s.

### Centro de Desvios

- Entrar a `/desvios`.
- Filtrar por sucursal, severidad, estado, fecha y texto.
- Confirmar vencidos y severidad alta arriba.
- Click en `Ver detalle`.
- Click en `Contactar` en una fila con telefono.

### Detalle de Desvio

- Entrar a `/desvios/:id`.
- Confirmar datos, responsable, evidencias y timeline.
- Click `Contactar responsable`.
- Confirmar evento `contacto`.
- Click `Marcar en proceso`.
- Intentar resolver sin comentario: debe bloquear.
- Resolver con comentario y evidencia opcional.
- Confirmar eventos `respuesta` y `evidencia`.
- Cerrar el desvio.
- Confirmar estado `Cerrada` y evento `cierre`.

## Pendientes Conocidos

- Mover agregaciones de dashboard a una view/RPC de Supabase si crece el volumen.
- Hacer las transiciones de estado y timeline atomicas con una funcion RPC.
- Endurecer RLS por auditor/sucursal si se requiere aislamiento estricto.
- Implementar upload real de evidencia.
- Corregir mojibake heredado en pantallas antiguas.
- Revisar mobile con datos reales y tablas grandes.

## Handoff

Ver `docs/CODEX_HANDOFF.md` para bitacora de cambios por etapa.

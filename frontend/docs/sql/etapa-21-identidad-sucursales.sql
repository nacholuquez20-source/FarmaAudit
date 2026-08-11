-- Etapa 21: Identidad única de WhatsApp + catálogo de tipos de auditoría + baja
-- lógica de sucursales.
--
-- Por qué: hoy el teléfono de una persona vive en tres lugares que no se
-- hablan entre sí (auditores.telefono, profiles.telefono, sucursales.tel_
-- responsable), y "auditor de perfumería" no existe como dato — cualquier
-- auditor activo puede correr cualquier tipo de auditoría. Esto se arregla
-- antes de sumar el próximo rol (auditor de venta de medicamentos al
-- público), para que agregarlo sea un INSERT en tipos_auditoria y no una
-- migración de esquema.
--
-- Alcance de esta etapa: base + panel + bot resolviendo identidad contra el
-- modelo nuevo. El dispatch de flujo en router.py sigue siendo perfumería;
-- tipo_auditoria_id en sesiones_whatsapp queda listo para que la etapa
-- siguiente enchufe el flujo nuevo sin tocar el de perfumería.

-- ============ 1. Baja lógica de sucursales ============
-- Seis tablas referencian sucursales(id) sin ON DELETE (reportes, gestion,
-- control_stock, profiles, campania_tareas, campania_resultados), así que un
-- DELETE real falla en cuanto hay una sola fila asociada. Archivar en vez de
-- borrar.
alter table sucursales add column if not exists activo boolean not null default true;

-- ============ 2. Catálogo de tipos de auditoría ============
-- Sumar "venta de medicamentos al público" es insertar una fila acá, no
-- tocar código ni esquema.
create table if not exists tipos_auditoria (
  id text primary key,              -- 'perfumeria', 'venta_medicamentos'
  nombre text not null,
  descripcion text,
  activo boolean not null default true,
  orden integer not null default 0,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

insert into tipos_auditoria (id, nombre, descripcion, orden)
values ('perfumeria', 'Perfumería', 'Auditoría de los cuatro bloques de perfumería (limpieza, stock, ofertas, burbujas).', 1)
on conflict (id) do nothing;

-- ============ 3. Identidad única de WhatsApp ============
-- Reemplaza auditores + profiles.telefono + sucursales.tel_responsable como
-- fuente de "quién es este teléfono y qué puede hacer". Un teléfono es
-- responsable de una sucursal O auditor, nunca ambos (decisión de producto);
-- el CHECK de alcance lo hace imposible representar mal.
create table if not exists usuarios_whatsapp (
  id uuid primary key default gen_random_uuid(),
  telefono text not null unique,    -- normalizado: solo dígitos
  nombre text not null,
  rol text not null check (rol in ('responsable_sucursal', 'auditor')),
  id_sucursal text references sucursales(id),
  activo boolean not null default true,
  profile_id uuid references profiles(id) on delete set null,  -- login web opcional
  notas text,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  constraint usuarios_whatsapp_scope_check check (
    (rol = 'responsable_sucursal' and id_sucursal is not null)
    or (rol = 'auditor' and id_sucursal is null)
  )
);

create index if not exists idx_usuarios_whatsapp_telefono on usuarios_whatsapp(telefono);
create index if not exists idx_usuarios_whatsapp_sucursal on usuarios_whatsapp(id_sucursal);
create index if not exists idx_usuarios_whatsapp_rol on usuarios_whatsapp(rol);

-- ============ 4. Qué tipos de auditoría cubre cada auditor ============
-- Un auditor puede cubrir varios tipos (ej. perfumería y venta de
-- medicamentos). Con un tipo asignado el bot arranca directo, como hoy; con
-- más de uno, pregunta cuál — eso lo implementa la etapa siguiente.
create table if not exists usuario_tipos_auditoria (
  usuario_id uuid not null references usuarios_whatsapp(id) on delete cascade,
  tipo_auditoria_id text not null references tipos_auditoria(id) on delete restrict,
  primary key (usuario_id, tipo_auditoria_id)
);

-- ============ 5. Forward-compat para el bot ============
-- El dispatch de router.py no cambia en esta etapa, pero la columna queda
-- lista para que el próximo rol la use sin otra migración.
alter table sesiones_whatsapp
  add column if not exists tipo_auditoria_id text default 'perfumeria';

-- ============ 6. Backfill ============
-- Orden deliberado: replica la precedencia actual del bot (router.py — un
-- teléfono que es auditor activo gana sobre encargado). Se hace en el mismo
-- orden acá para que, ante un teléfono presente en dos fuentes legacy, el
-- backfill decida igual que el bot decidía antes de esta migración.

-- 6.1 auditores → rol='auditor', + cobertura de perfumería (todo lo que hoy
-- existe en la tabla legacy auditaba perfumería, que era el único tipo).
insert into usuarios_whatsapp (telefono, nombre, rol, activo)
select
  regexp_replace(a.telefono, '\D', '', 'g'),
  a.nombre,
  'auditor',
  coalesce(a.activo, true)
from auditores a
where regexp_replace(a.telefono, '\D', '', 'g') <> ''
on conflict (telefono) do nothing;

insert into usuario_tipos_auditoria (usuario_id, tipo_auditoria_id)
select u.id, 'perfumeria'
from usuarios_whatsapp u
join auditores a
  on regexp_replace(a.telefono, '\D', '', 'g') = u.telefono
where u.rol = 'auditor'
on conflict do nothing;

-- 6.2 profiles con role='sucursal' → rol='responsable_sucursal', vinculando
-- el login web existente.
insert into usuarios_whatsapp (telefono, nombre, rol, id_sucursal, activo, profile_id)
select
  regexp_replace(p.telefono, '\D', '', 'g'),
  coalesce(p.nombre, 'Responsable de sucursal'),
  'responsable_sucursal',
  p.id_sucursal,
  true,
  p.id
from profiles p
where p.role = 'sucursal'
  and p.telefono is not null
  and regexp_replace(p.telefono, '\D', '', 'g') <> ''
  and p.id_sucursal is not null
on conflict (telefono) do nothing;

-- 6.3 sucursales.tel_responsable que no haya entrado por 6.1 ni 6.2 (mismo
-- fallback que get_encargado_by_phone hace hoy en runtime).
insert into usuarios_whatsapp (telefono, nombre, rol, id_sucursal, activo)
select
  regexp_replace(s.tel_responsable, '\D', '', 'g'),
  coalesce(s.responsable, 'Responsable de sucursal'),
  'responsable_sucursal',
  s.id,
  true
from sucursales s
where s.tel_responsable is not null
  and regexp_replace(s.tel_responsable, '\D', '', 'g') <> ''
on conflict (telefono) do nothing;

-- ============ 7. Vista sucursales_dashboard: excluir archivadas ============
-- Mismas columnas que etapa-18, solo se agrega el filtro. No rompe nada
-- aguas abajo porque no cambia la forma de la vista.
CREATE OR REPLACE VIEW sucursales_dashboard
WITH (security_invoker = true) AS
WITH ultima_ficha AS (
  SELECT DISTINCT ON (sucursal_id)
    sucursal_id,
    COALESCE(fecha_auditoria, created_at) AS fecha_efectiva,
    puntuacion_promedio
  FROM audit_fiches
  ORDER BY sucursal_id, COALESCE(fecha_auditoria, created_at) DESC NULLS LAST, created_at DESC
),
hoy_ar AS (
  SELECT (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date AS d
),
desvios_agg AS (
  SELECT
    id_sucursal,
    COUNT(*) FILTER (
      WHERE estado NOT IN ('Resuelta', 'Cerrada')
    ) AS desvios_abiertos,
    COUNT(*) FILTER (
      WHERE estado NOT IN ('Resuelta', 'Cerrada')
        AND (estado = 'Vencida' OR plazo_fecha < (SELECT d FROM hoy_ar))
    ) AS desvios_vencidos
  FROM gestion
  GROUP BY id_sucursal
)
SELECT
  s.id,
  s.nombre,
  s.direccion,
  s.zona,
  s.categoria,
  s.responsable,
  s.tel_responsable,
  s.tiene_perfumeria,

  uf.fecha_efectiva            AS ultima_auditoria,
  uf.puntuacion_promedio       AS ultimo_score,
  CASE
    WHEN uf.fecha_efectiva IS NULL THEN NULL
    ELSE ((SELECT d FROM hoy_ar) - (uf.fecha_efectiva AT TIME ZONE 'America/Argentina/Buenos_Aires')::date)
  END                          AS dias_desde_auditoria,

  COALESCE(da.desvios_abiertos, 0) AS desvios_abiertos,
  COALESCE(da.desvios_vencidos, 0) AS desvios_vencidos,

  CASE
    WHEN COALESCE(da.desvios_vencidos, 0) > 0                                    THEN 'critica'
    WHEN uf.fecha_efectiva IS NOT NULL
     AND ((SELECT d FROM hoy_ar) - (uf.fecha_efectiva AT TIME ZONE 'America/Argentina/Buenos_Aires')::date) > 30  THEN 'critica'
    WHEN uf.puntuacion_promedio IS NOT NULL AND uf.puntuacion_promedio < 3.0    THEN 'critica'
    WHEN COALESCE(da.desvios_abiertos, 0) > 0                                   THEN 'atencion'
    WHEN uf.fecha_efectiva IS NOT NULL
     AND ((SELECT d FROM hoy_ar) - (uf.fecha_efectiva AT TIME ZONE 'America/Argentina/Buenos_Aires')::date) BETWEEN 15 AND 30  THEN 'atencion'
    WHEN uf.puntuacion_promedio IS NOT NULL AND uf.puntuacion_promedio < 4.0    THEN 'atencion'
    WHEN uf.fecha_efectiva IS NULL                                              THEN 'sin_datos'
    ELSE 'ok'
  END                          AS estado_salud
FROM sucursales s
LEFT JOIN ultima_ficha uf ON uf.sucursal_id = s.id
LEFT JOIN desvios_agg  da ON da.id_sucursal = s.id
WHERE s.activo;

GRANT SELECT ON sucursales_dashboard TO authenticated;

-- ============ 8. RLS ============
-- Mismo criterio admin que el resto del esquema desde etapa-20: is_admin(),
-- no una subquery inline sobre profiles (esa es la que causaba la recursión
-- en profiles_admin_read). Estas tablas no son profiles, así que no hay
-- riesgo de reintroducirla — pero se usa is_admin() de todos modos para no
-- tener dos convenciones conviviendo.

alter table tipos_auditoria enable row level security;
create policy "tipos_auditoria_read" on tipos_auditoria for select using (true);
create policy "tipos_auditoria_admin_write" on tipos_auditoria for all using (is_admin()) with check (is_admin());

alter table usuarios_whatsapp enable row level security;
create policy "usuarios_whatsapp_admin_all" on usuarios_whatsapp for all using (is_admin()) with check (is_admin());

alter table usuario_tipos_auditoria enable row level security;
create policy "usuario_tipos_auditoria_admin_all" on usuario_tipos_auditoria for all using (is_admin()) with check (is_admin());

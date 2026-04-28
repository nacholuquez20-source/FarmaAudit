-- AuditBot Perfumeria - Supabase operational schema
-- Run in Supabase SQL Editor before migrating data from Google Sheets.
-- Google Drive remains the storage target for uploaded photos.

create extension if not exists pgcrypto;

-- ========== Maestros ==========

create table if not exists auditores (
  telefono text primary key,
  nombre text not null,
  cuadrilla text,
  activo boolean not null default true,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists sucursales (
  id text primary key,
  nombre text not null,
  direccion text,
  responsable text,
  tel_responsable text,
  zona text,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists catalogo_areas (
  area text primary key,
  subitems jsonb not null default '[]'::jsonb,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists checklist_plantillas (
  item_id text primary key,
  bloque text not null,
  bloque_nombre text,
  descripcion text not null,
  peso integer not null default 5,
  punto_orden integer,
  area text,
  responsable_default text,
  severidad_default text default 'Media',
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists checklist_perfumeria (
  bloque_id text not null,
  bloque_nombre text not null,
  punto_orden integer not null,
  tipo_respuesta text not null default 'si_no',
  pregunta text not null,
  peso integer not null default 5,
  critico boolean not null default false,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  primary key (bloque_id, punto_orden)
);

-- ========== Transaccionales ==========

create table if not exists conversaciones (
  telefono text primary key,
  estado_actual text not null default 'idle',
  id_pendiente text,
  ultimo_mensaje text,
  timestamp timestamp with time zone not null default now(),
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists pendientes (
  id_temp text primary key,
  telefono_auditor text references auditores(telefono) on update cascade on delete set null,
  estado text not null,
  datos_json jsonb not null default '{}'::jsonb,
  timestamp_creacion timestamp with time zone not null default now(),
  expira_en timestamp with time zone not null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists sesiones_auditoria (
  id_sesion text primary key,
  telefono_auditor text references auditores(telefono) on update cascade on delete set null,
  sucursal_id text references sucursales(id) on update cascade on delete set null,
  estado text not null,
  timestamp_inicio timestamp with time zone not null default now(),
  timestamp_ultimo_punto timestamp with time zone not null default now(),
  punto_actual integer not null default 0,
  total_puntos integer not null default 0,
  hallazgos_json jsonb not null default '[]'::jsonb,
  omitidos_json jsonb not null default '[]'::jsonb,
  bloque_actual text not null default 'A',
  resultados_json jsonb not null default '{}'::jsonb,
  stock_total integer not null default 0,
  stock_actual integer not null default 0,
  stock_items_json jsonb not null default '[]'::jsonb,
  desvios_libres_json jsonb not null default '[]'::jsonb,
  compromisos_firmados text,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists reportes (
  id text primary key,
  fecha date,
  hora time,
  cuadrilla text,
  auditor text,
  id_sucursal text references sucursales(id) on update cascade on delete set null,
  sucursal text,
  area text,
  subitem text,
  descripcion text,
  severidad text check (severidad in ('Alta', 'Media', 'Baja')),
  foto_url text,
  creado_por_audio boolean not null default false,
  timestamp timestamp with time zone not null default now(),
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists gestion (
  id_gestion text primary key,
  id_reporte text references reportes(id) on update cascade on delete set null,
  id_sucursal text references sucursales(id) on update cascade on delete set null,
  sucursal text,
  desvio text,
  severidad text check (severidad in ('Alta', 'Media', 'Baja')),
  responsable text,
  tel_responsable text,
  plazo_fecha date,
  plan_accion text,
  estado text not null default 'Abierta' check (estado in ('Abierta', 'En_proceso', 'Resuelta', 'Cerrada', 'Vencida')),
  fecha_cierre timestamp with time zone,
  cerrado_por text,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists resultados_perfumeria (
  id text primary key default gen_random_uuid()::text,
  id_sesion text references sesiones_auditoria(id_sesion) on update cascade on delete cascade,
  bloque_id text not null,
  punto_orden integer not null,
  pregunta text,
  respuesta_json jsonb not null default '{}'::jsonb,
  tipo_respuesta text,
  foto_url text,
  timestamp timestamp with time zone not null default now(),
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists control_stock (
  id text primary key default gen_random_uuid()::text,
  auditoria_id text references sesiones_auditoria(id_sesion) on update cascade on delete set null,
  sucursal_id text references sucursales(id) on update cascade on delete set null,
  fecha date not null default current_date,
  auditor text,
  nombre_item text,
  stock_fisico integer not null default 0,
  stock_sistema integer not null default 0,
  diferencia integer not null default 0,
  alerta text,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists webhook_dedup (
  message_id text primary key,
  phone text,
  claimed_at timestamp with time zone not null default now()
);

-- Existing frontend auth table. Kept here so a fresh environment has one source of truth.
create table if not exists profiles (
  id uuid references auth.users(id) on delete cascade primary key,
  role text not null check (role in ('admin', 'auditor')),
  nombre text,
  telefono text,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

-- ========== Indexes ==========

create index if not exists idx_conversaciones_timestamp on conversaciones(timestamp);
create index if not exists idx_pendientes_telefono_auditor on pendientes(telefono_auditor);
create index if not exists idx_pendientes_expira_en on pendientes(expira_en);
create index if not exists idx_sesiones_telefono_auditor on sesiones_auditoria(telefono_auditor);
create index if not exists idx_sesiones_sucursal_id on sesiones_auditoria(sucursal_id);
create index if not exists idx_sesiones_estado on sesiones_auditoria(estado);
create index if not exists idx_reportes_sucursal on reportes(id_sucursal);
create index if not exists idx_reportes_timestamp on reportes(timestamp);
create index if not exists idx_gestion_sucursal on gestion(id_sucursal);
create index if not exists idx_gestion_estado on gestion(estado);
create index if not exists idx_gestion_plazo_fecha on gestion(plazo_fecha);
create index if not exists idx_resultados_perfumeria_sesion on resultados_perfumeria(id_sesion);
create index if not exists idx_control_stock_sucursal on control_stock(sucursal_id);
create index if not exists idx_webhook_dedup_claimed_at on webhook_dedup(claimed_at);
create index if not exists idx_profiles_telefono on profiles(telefono);

-- ========== Updated-at trigger ==========

create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'auditores', 'sucursales', 'catalogo_areas', 'checklist_plantillas',
    'checklist_perfumeria', 'conversaciones', 'pendientes',
    'sesiones_auditoria', 'reportes', 'gestion', 'resultados_perfumeria',
    'control_stock', 'profiles'
  ]
  loop
    execute format('drop trigger if exists trg_%I_updated_at on %I', table_name, table_name);
    execute format(
      'create trigger trg_%I_updated_at before update on %I for each row execute function set_updated_at()',
      table_name,
      table_name
    );
  end loop;
end $$;

-- ========== RLS ==========
-- The Python bot uses SUPABASE_SERVICE_KEY and bypasses RLS. Frontend users remain constrained.

alter table auditores enable row level security;
alter table sucursales enable row level security;
alter table catalogo_areas enable row level security;
alter table checklist_plantillas enable row level security;
alter table checklist_perfumeria enable row level security;
alter table conversaciones enable row level security;
alter table pendientes enable row level security;
alter table sesiones_auditoria enable row level security;
alter table reportes enable row level security;
alter table gestion enable row level security;
alter table resultados_perfumeria enable row level security;
alter table control_stock enable row level security;
alter table webhook_dedup enable row level security;
alter table profiles enable row level security;

drop policy if exists "read_static" on sucursales;
create policy "read_static" on sucursales for select using (true);

drop policy if exists "read_checklist_perfumeria" on checklist_perfumeria;
create policy "read_checklist_perfumeria" on checklist_perfumeria for select using (true);

drop policy if exists "read_checklist_plantillas" on checklist_plantillas;
create policy "read_checklist_plantillas" on checklist_plantillas for select using (true);

drop policy if exists "read_gestion" on gestion;
create policy "read_gestion" on gestion for select using (true);

drop policy if exists "authenticated_update_gestion" on gestion;
create policy "authenticated_update_gestion" on gestion for update using (auth.role() = 'authenticated');

drop policy if exists "read_reportes_authenticated" on reportes;
create policy "read_reportes_authenticated" on reportes for select using (auth.role() = 'authenticated');

drop policy if exists "profiles_own_read" on profiles;
create policy "profiles_own_read" on profiles for select using (auth.uid() = id);

drop policy if exists "webhook_dedup_deny_all" on webhook_dedup;
create policy "webhook_dedup_deny_all" on webhook_dedup for all using (false);

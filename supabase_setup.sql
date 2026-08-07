-- Supabase SQL Setup for FarmaAudit Dashboard
-- Run this in Supabase SQL Editor

-- 1. Sucursales table
create table if not exists sucursales (
  id text primary key,
  nombre text not null,
  direccion text,
  responsable text,
  tel_responsable text,
  zona text,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

-- 2. Reportes table
create table if not exists reportes (
  id text primary key,
  fecha text not null,
  hora text,
  cuadrilla text,
  auditor text not null,
  id_sucursal text references sucursales(id),
  sucursal text,
  area text,
  subitem text,
  descripcion text,
  severidad text check (severidad in ('Alta', 'Media', 'Baja')),
  foto_url text,
  creado_por_audio boolean default false,
  timestamp text,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

-- 3. Gestion table
create table if not exists gestion (
  id_gestion text primary key,
  id_reporte text,
  id_sucursal text references sucursales(id),
  sucursal text,
  desvio text,
  severidad text check (severidad in ('Alta', 'Media', 'Baja')),
  responsable text,
  tel_responsable text,
  plazo_fecha date,
  plan_accion text,
  estado text check (estado in ('Abierta', 'En_proceso', 'Resuelta', 'Cerrada', 'Vencida')),
  fecha_cierre date,
  cerrado_por text,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

-- 4. Auditores table
create table if not exists auditores (
  telefono text primary key,
  nombre text not null,
  cuadrilla text,
  activo boolean default true,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

-- 5. Control_Stock table
create table if not exists control_stock (
  id text primary key,
  auditoria_id text,
  sucursal_id text references sucursales(id),
  fecha date,
  auditor text,
  nombre_item text,
  stock_fisico integer,
  stock_sistema integer,
  diferencia integer,
  alerta text,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

-- 6. Webhook dedup table (cross-instance idempotency)
create table if not exists webhook_dedup (
  message_id text primary key,
  phone text,
  claimed_at timestamp with time zone default now()
);

-- 7. Profiles table (for auth)
create table if not exists profiles (
  id uuid references auth.users(id) on delete cascade primary key,
  role text not null check (role in ('admin', 'auditor', 'sucursal')),
  nombre text,
  telefono text,
  id_sucursal text references sucursales(id),
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

-- Create indexes for better query performance
create index if not exists idx_reportes_sucursal on reportes(id_sucursal);
create index if not exists idx_reportes_auditor on reportes(auditor);
create index if not exists idx_gestion_sucursal on gestion(id_sucursal);
create index if not exists idx_gestion_estado on gestion(estado);
create index if not exists idx_auditores_telefono on auditores(telefono);
create index if not exists idx_control_stock_sucursal on control_stock(sucursal_id);
create index if not exists idx_webhook_dedup_claimed_at on webhook_dedup(claimed_at);
create index if not exists idx_profiles_telefono on profiles(telefono);
create index if not exists idx_profiles_id_sucursal on profiles(id_sucursal);

-- ============ ROW LEVEL SECURITY (RLS) ============

-- Enable RLS on all tables
alter table sucursales enable row level security;
alter table reportes enable row level security;
alter table gestion enable row level security;
alter table auditores enable row level security;
alter table control_stock enable row level security;
alter table webhook_dedup enable row level security;
alter table profiles enable row level security;

-- Sucursales: Admins can see all, auditors can see all (farms are public data)
create policy "sucursales_read" on sucursales for select using (true);
create policy "sucursales_admin_update" on sucursales for update using (
  exists (select 1 from profiles where id = auth.uid() and role = 'admin')
) with check (
  exists (select 1 from profiles where id = auth.uid() and role = 'admin')
);

-- Reportes: Admins can see all, auditors can only see their own (by auditor name)
create policy "reportes_admin_read" on reportes for select using (
  exists (select 1 from profiles where id = auth.uid() and role = 'admin')
);
create policy "reportes_auditor_read" on reportes for select using (
  exists (select 1 from profiles where id = auth.uid() and role = 'auditor' and telefono = reportes.auditor)
);
create policy "reportes_sucursal_read" on reportes for select using (
  exists (
    select 1 from profiles p
    where p.id = auth.uid() and p.role = 'sucursal'
    and p.id_sucursal is not null
    and reportes.id_sucursal = p.id_sucursal
  )
);

-- Gestion: admins y auditores ven todo; responsable solo su sucursal
create policy "gestion_select_scope" on gestion for select using (
  exists (select 1 from profiles p where p.id = auth.uid() and p.role = 'admin')
  or exists (select 1 from profiles p where p.id = auth.uid() and p.role = 'auditor')
  or exists (
    select 1 from profiles p
    where p.id = auth.uid() and p.role = 'sucursal'
    and p.id_sucursal is not null
    and gestion.id_sucursal = p.id_sucursal
  )
);
create policy "gestion_update_admin" on gestion for update using (
  exists (select 1 from profiles where id = auth.uid() and role = 'admin')
);
create policy "gestion_update_sucursal" on gestion for update using (
  exists (
    select 1 from profiles p
    where p.id = auth.uid() and p.role = 'sucursal'
    and p.id_sucursal is not null
    and gestion.id_sucursal = p.id_sucursal
  )
);

-- Auditores: Only admins can see and update
create policy "auditores_admin_read" on auditores for select using (
  exists (select 1 from profiles where id = auth.uid() and role = 'admin')
);
create policy "auditores_admin_write" on auditores for all using (
  exists (select 1 from profiles where id = auth.uid() and role = 'admin')
);

-- Control_Stock: Admins can see all, auditors see only their own (by auditor name)
create policy "control_stock_admin_read" on control_stock for select using (
  exists (select 1 from profiles where id = auth.uid() and role = 'admin')
);
create policy "control_stock_auditor_read" on control_stock for select using (
  exists (select 1 from profiles where id = auth.uid() and role = 'auditor' and telefono = control_stock.auditor)
);

-- Profiles: Users can read own profile, admins can read all.
-- Admin checks go through is_admin() (SECURITY DEFINER, bypasses RLS
-- internally) instead of a plain subquery on profiles, because a
-- profiles-select-policy that itself selects from profiles causes
-- Postgres to detect infinite recursion on the table. See etapa-20.
create or replace function public.is_admin()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1 from profiles where id = auth.uid() and role = 'admin'
  );
$$;

grant execute on function public.is_admin() to authenticated;

create policy "profiles_own_read" on profiles for select using (auth.uid() = id);
create policy "profiles_admin_read" on profiles for select using (is_admin());
create policy "profiles_admin_update" on profiles for update using (is_admin());

-- Prevent role escalation: role field can only be changed by admins
create policy "profiles_role_protected" on profiles for update
  using (true)
  with check (
    -- Role can only be changed if the user doing the update is an admin
    (new.role = old.role) or (exists (select 1 from profiles where id = auth.uid() and role = 'admin'))
  );

-- Webhook dedup: only service role should access; deny anon/authenticated
create policy "webhook_dedup_deny_all" on webhook_dedup for all using (false);

-- ============ HELPER FUNCTIONS ============

-- Function to handle new user profile creation
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
as $$
begin
  insert into public.profiles (id, role, nombre)
  values (new.id, 'auditor', new.email);
  return new;
end;
$$;

-- Trigger to auto-create profile when user signs up
create trigger on_auth_user_created
  after insert on auth.users
  for each row
  execute procedure public.handle_new_user();

-- Etapa 4: rol "sucursal" (responsable de perfumería), sucursal asignada en el panel,
-- lectura segmentada en reportes/gestión y admins pueden actualizar perfiles.
-- Ejecutar en Supabase SQL Editor después de las etapas anteriores.

-- 1) Perfil enlazado a sucursal (nullable: auditores/admin no necesitan sucursal)
alter table public.profiles
  add column if not exists id_sucursal text references public.sucursales(id);

create index if not exists idx_profiles_id_sucursal on public.profiles(id_sucursal);

-- 2) Ampliar valores permitidos de role
alter table public.profiles drop constraint if exists profiles_role_check;
alter table public.profiles
  add constraint profiles_role_check check (role in ('admin', 'auditor', 'sucursal'));

-- 3) Gestión: reemplazar lectura abierta por alcance por rol
drop policy if exists gestion_read on public.gestion;

create policy gestion_select_scope on public.gestion for select using (
  exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin')
  or exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'auditor')
  or exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role = 'sucursal'
    and p.id_sucursal is not null
    and gestion.id_sucursal = p.id_sucursal
  )
);

-- Responsable puede actualizar planes de acción solo de su sucursal (coexiste con admin)
drop policy if exists gestion_update_sucursal on public.gestion;
create policy gestion_update_sucursal on public.gestion for update using (
  exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role = 'sucursal'
    and p.id_sucursal is not null
    and gestion.id_sucursal = p.id_sucursal
  )
);

-- 4) Reportes: responsable solo ve hallazgos de su sucursal
drop policy if exists reportes_sucursal_read on public.reportes;
create policy reportes_sucursal_read on public.reportes for select using (
  exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role = 'sucursal'
    and p.id_sucursal is not null
    and reportes.id_sucursal = p.id_sucursal
  )
);

-- 5) Profiles: admin puede actualizar roles/tel/sucursal de otros usuarios del panel
drop policy if exists profiles_admin_update on public.profiles;
create policy profiles_admin_update on public.profiles for update using (
  exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin')
);

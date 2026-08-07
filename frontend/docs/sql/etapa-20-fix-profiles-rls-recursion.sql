-- Etapa 20: Fix RLS recursion on profiles causing "Cargando perfil..." to hang/error.
--
-- profiles_admin_read / profiles_admin_update checked admin status by
-- selecting from profiles itself, which re-triggers profiles' own SELECT
-- RLS (including profiles_admin_read again) on every evaluation. Postgres
-- detects this as infinite recursion on the profiles table.
--
-- Fix: move the admin check into a SECURITY DEFINER function, which runs
-- as its owner and bypasses RLS internally, breaking the cycle.

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

drop policy if exists "profiles_admin_read" on profiles;
create policy "profiles_admin_read" on profiles for select using (is_admin());

drop policy if exists "profiles_admin_update" on profiles;
create policy "profiles_admin_update" on profiles for update using (is_admin());

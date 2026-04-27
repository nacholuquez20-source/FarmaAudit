-- Etapa 3 - Resolucion con evidencia y cierre controlado
-- Run this in the Supabase SQL editor after `frontend/docs/sql/etapa-2.sql`.

alter table gestion drop constraint if exists gestion_estado_check;
alter table gestion add constraint gestion_estado_check
  check (estado in ('Abierta', 'En_proceso', 'Resuelta', 'Cerrada', 'Vencida'));

drop policy if exists "gestion_update_admin" on gestion;
drop policy if exists "gestion_update_authenticated" on gestion;
create policy "gestion_update_authenticated" on gestion for update using (
  exists (select 1 from profiles where id = auth.uid() and role in ('admin', 'auditor'))
) with check (
  exists (select 1 from profiles where id = auth.uid() and role in ('admin', 'auditor'))
);

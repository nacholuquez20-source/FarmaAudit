-- Etapa 5: edicion inline de sucursales desde el panel.
-- Permite que usuarios admin actualicen datos maestros de sucursales.

drop policy if exists sucursales_admin_update on public.sucursales;

create policy sucursales_admin_update on public.sucursales
for update
using (
  exists (
    select 1
    from public.profiles p
    where p.id = auth.uid()
      and p.role = 'admin'
  )
)
with check (
  exists (
    select 1
    from public.profiles p
    where p.id = auth.uid()
      and p.role = 'admin'
  )
);

-- Etapa 2 - Desvio timeline events
-- Run this in the Supabase SQL editor after `supabase_setup.sql`.

create table if not exists desvio_eventos (
  id uuid primary key default gen_random_uuid(),
  id_gestion text not null references gestion(id_gestion) on delete cascade,
  tipo text not null check (tipo in ('creacion', 'contacto', 'respuesta', 'cierre', 'nota', 'evidencia')),
  comentario text not null,
  actor_id uuid references auth.users(id) on delete set null,
  actor_nombre text,
  metadata jsonb default '{}'::jsonb,
  created_at timestamp with time zone default now()
);

create index if not exists idx_desvio_eventos_gestion on desvio_eventos(id_gestion);
create index if not exists idx_desvio_eventos_created_at on desvio_eventos(created_at);

alter table desvio_eventos enable row level security;

drop policy if exists "desvio_eventos_read" on desvio_eventos;
create policy "desvio_eventos_read" on desvio_eventos for select using (
  exists (select 1 from profiles where id = auth.uid())
);

drop policy if exists "desvio_eventos_insert" on desvio_eventos;
create policy "desvio_eventos_insert" on desvio_eventos for insert with check (
  exists (select 1 from profiles where id = auth.uid())
);

drop policy if exists "desvio_eventos_update_admin" on desvio_eventos;
create policy "desvio_eventos_update_admin" on desvio_eventos for update using (
  exists (select 1 from profiles where id = auth.uid() and role = 'admin')
);

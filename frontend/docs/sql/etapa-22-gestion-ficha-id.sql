-- Etapa 22: gestion.ficha_id -> audit_fiches
-- Por qué: conectar cada desvío con la auditoría que lo generó (ver
-- ARQUITECTURA_PANEL_DESVIOS.md §6). Se puebla desde Python al crear la ficha
-- (ver audit_fiches_manager.py), nunca por heurística. Las gestiones
-- históricas quedan en null a propósito — no hay backfill.

alter table gestion add column if not exists ficha_id uuid references audit_fiches(id) on delete set null;
create index if not exists idx_gestion_ficha_id on gestion(ficha_id);

-- Etapa 29: reportes.marca / gestion.marca
-- Por que: rediseno del paso 3/4 (OFERTAS) de la auditoria de WhatsApp de
-- perfumeria -- ahora cada hallazgo de ese bloque se registra con foto +
-- comentario/audio ligados a una marca puntual (una de las 4 sugeridas o
-- cualquier otra que la auditora escriba), en vez de un puntaje 1-5 por
-- marca sin evidencia asociada (ver audit_session.py / audit_handlers.py).
-- Ese dato (Desvio.marca) necesita un lugar donde persistir junto al
-- reporte/gestion para que quede visible en el panel de admin.

alter table public.reportes add column if not exists marca text;
alter table public.gestion add column if not exists marca text;

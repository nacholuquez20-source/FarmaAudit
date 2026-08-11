-- Etapa 24: seguimiento del encargado + recordatorios por sucursal
-- Por que: el dueno pidio una sola pantalla por sucursal que diga si el
-- encargado actuo o hace cuanto que no, con un boton para reclamarle por
-- WhatsApp. Hoy "actuo o no" no se calcula en ningun lado, y no hay registro
-- de a quien se le reclamo y cuando (asi que ni el cooldown ni el job
-- automatico de recordatorio pueden saber si ya se le escribio a alguien).

-- ============ 1. sucursales_dashboard: agregar silencio del encargado ============
-- Mismas columnas que etapa-21 (que a su vez no cambio nada de etapa-18),
-- solo se agrega. No rompe nada aguas abajo porque no cambia la forma de
-- las columnas existentes.

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
    ) AS desvios_vencidos,
    -- en_revision_desde no nulo = el encargado ya mando su correccion y
    -- espera que el auditor la apruebe: el turno es del auditor, no del
    -- encargado. Es el unico contador que exige accion inmediata.
    COUNT(*) FILTER (
      WHERE en_revision_desde IS NOT NULL
    ) AS desvios_para_revisar
  FROM gestion
  GROUP BY id_sucursal
),
-- Ultima vez que el ENCARGADO hizo algo (no el auditor). Mismo predicado
-- documentado en ARQUITECTURA_PANEL_DESVIOS.md: respuesta o evidencia son
-- siempre del encargado; un 'mensaje' solo cuenta si su metadata.origen
-- dice 'sucursal' (el mismo tipo lo usan auditor y encargado).
accion_encargado_agg AS (
  SELECT
    g.id_sucursal,
    MAX(e.created_at) AS ultima_accion_encargado
  FROM desvio_eventos e
  JOIN gestion g ON g.id_gestion = e.id_gestion
  WHERE e.tipo IN ('respuesta', 'evidencia')
     OR (e.tipo = 'mensaje' AND e.metadata->>'origen' = 'sucursal')
  GROUP BY g.id_sucursal
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
  END                          AS estado_salud,

  -- Columnas nuevas de esta etapa: van al final a proposito.
  -- CREATE OR REPLACE VIEW no permite insertar columnas en el medio de una
  -- vista existente (Postgres lo interpreta como un rename de columna y lo
  -- rechaza) — solo agregar al final.
  COALESCE(da.desvios_para_revisar, 0) AS desvios_para_revisar,
  ae.ultima_accion_encargado,
  CASE
    WHEN ae.ultima_accion_encargado IS NULL THEN NULL
    ELSE ((SELECT d FROM hoy_ar) - (ae.ultima_accion_encargado AT TIME ZONE 'America/Argentina/Buenos_Aires')::date)
  END                          AS dias_sin_accion
FROM sucursales s
LEFT JOIN ultima_ficha uf ON uf.sucursal_id = s.id
LEFT JOIN desvios_agg  da ON da.id_sucursal = s.id
LEFT JOIN accion_encargado_agg ae ON ae.id_sucursal = s.id
WHERE s.activo;

GRANT SELECT ON sucursales_dashboard TO authenticated;

-- ============ 2. recordatorios_sucursal: registro de a quien se le reclamo ============
-- Sin esto no se puede calcular el cooldown ni saber si el job automatico de
-- 3 dias realmente entrego algo (hoy falla en silencio para quien tiene la
-- ventana de 24h cerrada, que es casi todo el mundo).

create table if not exists recordatorios_sucursal (
  id uuid primary key default gen_random_uuid(),
  id_sucursal text not null references sucursales(id) on delete cascade,
  enviado_at timestamptz not null default now(),
  enviado_por text,                    -- null = job automatico
  canal text not null check (canal in ('bot', 'manual')),
  resultado text not null check (resultado in ('enviado', 'fallido', 'sin_ventana', 'sin_encargado')),
  detalle text,
  cantidad_desvios int
);

create index if not exists idx_recordatorios_sucursal on recordatorios_sucursal(id_sucursal, enviado_at desc);

alter table recordatorios_sucursal enable row level security;
create policy "recordatorios_sucursal_read" on recordatorios_sucursal for select using (true);
-- Solo el backend (service role, que bypasea RLS) escribe aca. Sin policy de
-- insert/update para authenticated: el auditor lee el historial pero el
-- registro del envio real lo hace el servidor, nunca el cliente.

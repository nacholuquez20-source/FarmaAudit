-- Etapa 30: coordenadas de sucursales para el mapa interactivo del Dashboard.
-- Por que: no existe ningun dato geografico en el sistema (direccion es texto
-- libre, zona es texto libre sin catalogo). En vez de geocodificar direcciones
-- argentinas automaticamente (poco confiable), el admin pinea cada sucursal a
-- mano una sola vez desde un picker nuevo en el panel de administracion.

alter table sucursales add column if not exists lat double precision;
alter table sucursales add column if not exists lng double precision;

-- Mismas columnas que etapa-24 (que a su vez no cambio nada de etapa-21/18),
-- solo se agrega lat/lng al final. CREATE OR REPLACE VIEW no permite insertar
-- columnas en el medio de una vista existente (Postgres lo interpreta como un
-- rename de columna y lo rechaza) — solo agregar al final.

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

  COALESCE(da.desvios_para_revisar, 0) AS desvios_para_revisar,
  ae.ultima_accion_encargado,
  CASE
    WHEN ae.ultima_accion_encargado IS NULL THEN NULL
    ELSE ((SELECT d FROM hoy_ar) - (ae.ultima_accion_encargado AT TIME ZONE 'America/Argentina/Buenos_Aires')::date)
  END                          AS dias_sin_accion,

  -- Columna nueva de esta etapa: al final, mismo motivo que arriba.
  s.lat,
  s.lng
FROM sucursales s
LEFT JOIN ultima_ficha uf ON uf.sucursal_id = s.id
LEFT JOIN desvios_agg  da ON da.id_sucursal = s.id
LEFT JOIN accion_encargado_agg ae ON ae.id_sucursal = s.id
WHERE s.activo;

GRANT SELECT ON sucursales_dashboard TO authenticated;

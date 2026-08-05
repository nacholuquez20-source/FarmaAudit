-- Etapa 18: Vista sucursales_dashboard — Centro de Operaciones del auditor.
-- Precalcula, por sucursal, el semáforo de salud + métricas operativas en una
-- sola query. Reemplaza el patrón "N+1" (pedir por cada sucursal sus desvíos y
-- su última auditoría) por un único SELECT del lado de la base.
--
-- Consumida directamente desde el panel con el cliente supabase-js.
-- security_invoker = true → respeta las políticas RLS de las tablas base:
--   - sucursales_read: todos los autenticados ven todas las sucursales
--   - audit_fiches_read_policy: autenticados ven todas las fichas
--   - gestion_select_scope: admin/auditor ven todo; 'sucursal' solo la suya
-- Como el Centro de Operaciones es una pantalla de admin/auditor, los agregados
-- de desvíos son exactos para su audiencia.

-- Todos los cálculos de "día" usan la zona horaria de Argentina (no UTC) para
-- que coincidan con lo que el panel calcula localmente y con la percepción real
-- de "hoy" / "hace X días" (evita corrimientos de 1 día en horario nocturno).
CREATE OR REPLACE VIEW sucursales_dashboard
WITH (security_invoker = true) AS
WITH ultima_ficha AS (
  -- Última ficha de auditoría por sucursal. Se ordena por la fecha efectiva
  -- (fecha_auditoria y, si falta, created_at) con created_at como desempate
  -- determinístico, para que "la última" sea realmente la más reciente aunque
  -- una ficha recién creada todavía no tenga fecha_auditoria.
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
  -- Conteo de desvíos abiertos y vencidos por sucursal
  SELECT
    id_sucursal,
    COUNT(*) FILTER (
      WHERE estado NOT IN ('Resuelta', 'Cerrada')
    ) AS desvios_abiertos,
    COUNT(*) FILTER (
      WHERE estado NOT IN ('Resuelta', 'Cerrada')
        AND (estado = 'Vencida' OR plazo_fecha < (SELECT d FROM hoy_ar))
    ) AS desvios_vencidos
  FROM gestion
  GROUP BY id_sucursal
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

  -- Semáforo de salud (4 estados). Se evalúan primero las condiciones críticas.
  -- 'sin_datos' (gris) separa "nunca auditada y sin desvíos pendientes" de una
  -- 'critica' real: sin este estado, un sistema recién arrancado pinta TODO en
  -- rojo y el semáforo pierde su señal. Una sucursal sin ficha PERO con desvíos
  -- vencidos/abiertos igual cae en critica/atencion (hay algo que accionar).
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
  END                          AS estado_salud
FROM sucursales s
LEFT JOIN ultima_ficha uf ON uf.sucursal_id = s.id
LEFT JOIN desvios_agg  da ON da.id_sucursal = s.id;

-- PostgREST expone la vista a los roles autenticados del panel.
GRANT SELECT ON sucursales_dashboard TO authenticated;

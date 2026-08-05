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

CREATE OR REPLACE VIEW sucursales_dashboard
WITH (security_invoker = true) AS
WITH ultima_ficha AS (
  -- Última ficha de auditoría por sucursal (la más reciente por fecha)
  SELECT DISTINCT ON (sucursal_id)
    sucursal_id,
    fecha_auditoria,
    puntuacion_promedio,
    desvios_count,
    fotos_count
  FROM audit_fiches
  ORDER BY sucursal_id, fecha_auditoria DESC NULLS LAST
),
desvios_agg AS (
  -- Conteo de desvíos abiertos y vencidos por sucursal
  SELECT
    id_sucursal,
    COUNT(*) FILTER (
      WHERE estado NOT IN ('Resuelta', 'Cerrada')
    ) AS desvios_abiertos,
    COUNT(*) FILTER (
      WHERE estado = 'Vencida'
         OR (plazo_fecha < CURRENT_DATE AND estado NOT IN ('Resuelta', 'Cerrada'))
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

  uf.fecha_auditoria           AS ultima_auditoria,
  uf.puntuacion_promedio       AS ultimo_score,
  CASE
    WHEN uf.fecha_auditoria IS NULL THEN NULL
    ELSE (CURRENT_DATE - uf.fecha_auditoria::date)
  END                          AS dias_desde_auditoria,

  COALESCE(da.desvios_abiertos, 0) AS desvios_abiertos,
  COALESCE(da.desvios_vencidos, 0) AS desvios_vencidos,

  -- Semáforo de salud: se evalúan primero las condiciones críticas.
  CASE
    WHEN COALESCE(da.desvios_vencidos, 0) > 0                                    THEN 'critica'
    WHEN uf.fecha_auditoria IS NULL                                             THEN 'critica'
    WHEN (CURRENT_DATE - uf.fecha_auditoria::date) > 30                         THEN 'critica'
    WHEN uf.puntuacion_promedio IS NOT NULL AND uf.puntuacion_promedio < 3.0    THEN 'critica'
    WHEN COALESCE(da.desvios_abiertos, 0) > 0                                   THEN 'atencion'
    WHEN (CURRENT_DATE - uf.fecha_auditoria::date) BETWEEN 15 AND 30            THEN 'atencion'
    WHEN uf.puntuacion_promedio IS NOT NULL AND uf.puntuacion_promedio < 4.0    THEN 'atencion'
    ELSE 'ok'
  END                          AS estado_salud
FROM sucursales s
LEFT JOIN ultima_ficha uf ON uf.sucursal_id = s.id
LEFT JOIN desvios_agg  da ON da.id_sucursal = s.id;

-- PostgREST expone la vista a los roles autenticados del panel.
GRANT SELECT ON sucursales_dashboard TO authenticated;

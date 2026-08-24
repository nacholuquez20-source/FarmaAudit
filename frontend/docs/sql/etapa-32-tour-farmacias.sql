-- Etapa 32: Tour de Farmacias (Fase 7) — MODULO 3 de ARQUITECTURA_DESVIOS_CAMPANIAS.md
-- Extiende el motor de Campanias (Modulo 2) en vez de duplicarlo: un tour es una
-- "campania" con tipo='tour_interno' y marca_id NULL. campania_tareas, campania_eventos,
-- campania_notificaciones, solicitudes_insumo y sus RLS (etapa-15/16) sirven tal cual.
-- Verificado contra el listado real de este directorio antes de numerar (llega a etapa-31).

-- ============ campanias: tipo + marca_id opcional para tours ============

ALTER TABLE campanias ADD COLUMN IF NOT EXISTS tipo text NOT NULL DEFAULT 'comercial'
  CHECK (tipo IN ('comercial', 'tour_interno'));

ALTER TABLE campanias ALTER COLUMN marca_id DROP NOT NULL;

ALTER TABLE campanias DROP CONSTRAINT IF EXISTS campanias_marca_segun_tipo;
ALTER TABLE campanias ADD CONSTRAINT campanias_marca_segun_tipo CHECK (
  (tipo = 'comercial' AND marca_id IS NOT NULL) OR (tipo = 'tour_interno' AND marca_id IS NULL)
);

-- ============ campania_acciones: 6 tipos nuevos, exclusivos de tour_interno ============
-- vidriera y heladera_cadena_frio se agregaron durante la auditoria de 4 agentes de la
-- spec (v5): el checklist original (iluminacion/gondolas/piso/limpieza) no cubria la
-- vidriera (exhibicion de fachada) ni la cadena de frio de heladeras (esto ultimo es
-- compliance regulatorio, no solo estetica).

ALTER TABLE campania_acciones DROP CONSTRAINT IF EXISTS campania_acciones_tipo_check;
ALTER TABLE campania_acciones ADD CONSTRAINT campania_acciones_tipo_check CHECK (
  tipo IN ('exhibicion', 'material_pop', 'burbuja_precio', 'descuento_caja', 'custom',
           'vidriera', 'iluminacion', 'gondola_orden', 'piso', 'limpieza', 'heladera_cadena_frio')
);

-- ============ campania_resultados: guarda de integridad, solo campanias comerciales ============
-- Sin esto, cualquier admin/auditor puede insertar "venta real" para un tour desde la
-- consola o un bug de UI futuro (la carga hoy es insert directo via supabase-js, sin
-- filtro de tipo en la policy). Hallazgo del arquitecto backend en la auditoria v5.

CREATE OR REPLACE FUNCTION check_campania_resultado_tipo_comercial()
RETURNS trigger AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM campanias WHERE id = NEW.campania_id AND tipo = 'comercial'
  ) THEN
    RAISE EXCEPTION 'campania_resultados solo aplica a campanias comerciales (tipo=comercial)';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_campania_resultado_tipo_comercial ON campania_resultados;
CREATE TRIGGER trg_campania_resultado_tipo_comercial
  BEFORE INSERT ON campania_resultados
  FOR EACH ROW EXECUTE FUNCTION check_campania_resultado_tipo_comercial();

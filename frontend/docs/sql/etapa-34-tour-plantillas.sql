-- Etapa 34: plantillas reutilizables para los puntos "desde cero" del Tour de
-- Farmacias. El checklist clasico (vidriera/iluminacion/gondola_orden/piso/limpieza/
-- heladera_cadena_frio) ya tiene identidad estable entre lanzamientos via
-- campania_acciones.tipo (etapa-32) -- el hueco real es que un punto ESCRITO A MANO
-- ("Gondolas de dermocosmetica...") no tiene ninguna relacion con el mismo punto
-- tipeado de nuevo el mes siguiente, asi que no se puede comparar una sucursal en
-- el tiempo para nada que no sea el checklist por defecto.
--
-- Diseño: un catalogo separado (tour_plantillas / tour_plantilla_puntos), NO una
-- entidad nueva por campania. campania_acciones.plantilla_punto_id es nullable y
-- solo se completa cuando el punto se cargo eligiendo un item de una plantilla
-- guardada -- un punto "desde cero" sin guardar sigue siendo tipo='custom' sin
-- identidad, exactamente como hoy. No se toca el CHECK de campania_acciones.tipo.
-- Verificado contra el listado real de este directorio antes de numerar (llega a etapa-33).

CREATE TABLE IF NOT EXISTS tour_plantillas (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre               text NOT NULL,
  creado_por_telefono  text,
  created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tour_plantilla_puntos (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plantilla_id  uuid NOT NULL REFERENCES tour_plantillas(id) ON DELETE CASCADE,
  descripcion   text NOT NULL,
  orden         int NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tour_plantilla_puntos_plantilla ON tour_plantilla_puntos(plantilla_id);

ALTER TABLE campania_acciones ADD COLUMN IF NOT EXISTS plantilla_punto_id uuid
  REFERENCES tour_plantilla_puntos(id);

CREATE INDEX IF NOT EXISTS idx_campania_acciones_plantilla_punto
  ON campania_acciones(plantilla_punto_id);

-- ============ RLS: mismo criterio que campanias/campania_acciones (etapa-15) ============
-- admin y auditor, full access. El bot escribe con service role (bypassa RLS, como
-- el resto de las escrituras del bot vía WhatsApp) -- esto habilita al wizard web,
-- si en algun momento se agrega gestion de plantillas ahi.

ALTER TABLE tour_plantillas ENABLE ROW LEVEL SECURITY;
ALTER TABLE tour_plantilla_puntos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "tour_plantillas_admin_auditor" ON tour_plantillas;
CREATE POLICY "tour_plantillas_admin_auditor" ON tour_plantillas FOR ALL USING (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
) WITH CHECK (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
);

DROP POLICY IF EXISTS "tour_plantilla_puntos_admin_auditor" ON tour_plantilla_puntos;
CREATE POLICY "tour_plantilla_puntos_admin_auditor" ON tour_plantilla_puntos FOR ALL USING (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
) WITH CHECK (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
);

-- Migration: Create audit_fiches table to store PDF metadata
-- Nota: la tabla de reportes se llama "reportes" (plural) y su id es TEXT de 12 chars,
-- no UUID. Por eso id_reporte es TEXT.

CREATE TABLE IF NOT EXISTS audit_fiches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_reporte TEXT NOT NULL REFERENCES reportes(id) ON DELETE CASCADE,
  sucursal_id VARCHAR(50) NOT NULL,
  auditor_nombre VARCHAR(255),
  responsable_desvios VARCHAR(255),
  fecha_auditoria TIMESTAMP WITH TIME ZONE,
  url_pdf TEXT,
  google_drive_id TEXT,
  estado VARCHAR(50) DEFAULT 'completada', -- completada, enviada, descargada
  desvios_count INT DEFAULT 0,
  fotos_count INT DEFAULT 0,
  puntuacion_promedio DECIMAL(3, 2),

  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for faster filtering
CREATE INDEX IF NOT EXISTS idx_audit_fiches_sucursal ON audit_fiches(sucursal_id);
CREATE INDEX IF NOT EXISTS idx_audit_fiches_fecha ON audit_fiches(fecha_auditoria);
CREATE INDEX IF NOT EXISTS idx_audit_fiches_auditor ON audit_fiches(auditor_nombre);
CREATE INDEX IF NOT EXISTS idx_audit_fiches_reporte ON audit_fiches(id_reporte);

-- Row Level Security
ALTER TABLE audit_fiches ENABLE ROW LEVEL SECURITY;

-- Policy: usuarios autenticados del panel pueden leer
DROP POLICY IF EXISTS audit_fiches_read_policy ON audit_fiches;
CREATE POLICY audit_fiches_read_policy ON audit_fiches
  FOR SELECT TO authenticated USING (true);

-- El bot inserta con service key (saltea RLS); estas policies quedan por si
-- algun dia se inserta/actualiza desde el panel autenticado
DROP POLICY IF EXISTS audit_fiches_insert_policy ON audit_fiches;
CREATE POLICY audit_fiches_insert_policy ON audit_fiches
  FOR INSERT TO authenticated WITH CHECK (true);

DROP POLICY IF EXISTS audit_fiches_update_policy ON audit_fiches;
CREATE POLICY audit_fiches_update_policy ON audit_fiches
  FOR UPDATE TO authenticated USING (true);

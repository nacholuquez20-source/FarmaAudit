-- Migration: Create audit_fiches table to store PDF metadata

CREATE TABLE IF NOT EXISTS audit_fiches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_reporte UUID NOT NULL REFERENCES reporte(id) ON DELETE CASCADE,
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
CREATE INDEX idx_audit_fiches_sucursal ON audit_fiches(sucursal_id);
CREATE INDEX idx_audit_fiches_fecha ON audit_fiches(fecha_auditoria);
CREATE INDEX idx_audit_fiches_auditor ON audit_fiches(auditor_nombre);
CREATE INDEX idx_audit_fiches_reporte ON audit_fiches(id_reporte);

-- Row Level Security
ALTER TABLE audit_fiches ENABLE ROW LEVEL SECURITY;

-- Policy: allow authenticated users to read
CREATE POLICY audit_fiches_read_policy ON audit_fiches
  FOR SELECT USING (true);

-- Policy: allow service role to insert/update
CREATE POLICY audit_fiches_insert_policy ON audit_fiches
  FOR INSERT WITH CHECK (true);

CREATE POLICY audit_fiches_update_policy ON audit_fiches
  FOR UPDATE USING (true);

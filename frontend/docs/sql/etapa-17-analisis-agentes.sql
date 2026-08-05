-- Etapa 17: Tabla de resultados de análisis multi-agente
-- Almacena los resultados del análisis de los 5 agentes IA por ficha de auditoría.
-- Ejecutar en Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS analisis_auditoria (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ficha_id        UUID        NOT NULL REFERENCES audit_fiches(id) ON DELETE CASCADE,
  sucursal_id     VARCHAR(50),
  fecha_auditoria TIMESTAMPTZ,

  -- Resultados por agente (JSONB para flexibilidad de esquema)
  agente_campo       JSONB,  -- auditor de campo
  agente_calidad     JSONB,  -- analista de tendencias/calidad
  agente_perfumeria  JSONB,  -- especialista perfumería argentina
  agente_normativo   JSONB,  -- farmacéutico / ANMAT
  agente_negocio     JSONB,  -- modelo de negocio / impacto económico
  sintesis           JSONB,  -- diagnóstico ejecutivo y plan de acción

  generado_en TIMESTAMPTZ DEFAULT now(),
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- Cada ficha tiene un análisis máximo (evita duplicados, los nuevos reemplazan)
CREATE UNIQUE INDEX IF NOT EXISTS analisis_auditoria_ficha_id_idx
  ON analisis_auditoria (ficha_id);

-- Índice para consultas por sucursal
CREATE INDEX IF NOT EXISTS analisis_auditoria_sucursal_idx
  ON analisis_auditoria (sucursal_id);

-- RLS: sólo admin/auditor pueden leer; sólo service_role puede escribir
ALTER TABLE analisis_auditoria ENABLE ROW LEVEL SECURITY;

CREATE POLICY analisis_auditoria_select ON analisis_auditoria
  FOR SELECT USING (auth.role() IN ('authenticated'));

-- NOTA: El backend escribe con service_role (omite RLS), por eso no
-- necesita política de INSERT/UPDATE explícita para usuarios de panel.

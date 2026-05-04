-- Etapa 8 - Sistema robusto de recoleccion multi-mensaje para respuestas de auditoria

CREATE TABLE IF NOT EXISTS respuesta_pregunta (
  id text PRIMARY KEY,
  id_sesion text NOT NULL,
  telefono_auditor text NOT NULL,
  pregunta_numero int NOT NULL,
  bloque_id text NOT NULL,
  estado text NOT NULL DEFAULT 'recolectando'
    CHECK (estado IN ('recolectando', 'completada', 'descartada')),
  timestamp_inicio timestamptz DEFAULT now(),
  timestamp_ultimo_mensaje timestamptz DEFAULT now(),
  timeout_segundos int NOT NULL DEFAULT 120,
  confirmado_por_auditor boolean DEFAULT false,
  timeout_prompt_enviado boolean DEFAULT false,
  mensajes_json text DEFAULT '[]',
  media_ids_json text DEFAULT '[]',
  respuesta_consolidada text,
  desvios_json text,
  razon_descarte text,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_respuesta_pregunta_sesion
  ON respuesta_pregunta(id_sesion)
  WHERE estado = 'recolectando';

CREATE INDEX IF NOT EXISTS idx_respuesta_pregunta_phone
  ON respuesta_pregunta(telefono_auditor)
  WHERE estado = 'recolectando';

CREATE INDEX IF NOT EXISTS idx_respuesta_pregunta_estado
  ON respuesta_pregunta(estado, timestamp_ultimo_mensaje);

CREATE TABLE IF NOT EXISTS respuesta_pregunta_audit_log (
  id text PRIMARY KEY,
  id_respuesta text NOT NULL REFERENCES respuesta_pregunta(id) ON DELETE CASCADE,
  evento text NOT NULL,
  detalles_json text,
  timestamp timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_respuesta
  ON respuesta_pregunta_audit_log(id_respuesta);

ALTER TABLE IF EXISTS sesiones_auditoria
ADD COLUMN IF NOT EXISTS id_respuesta_actual text REFERENCES respuesta_pregunta(id) ON DELETE SET NULL;

ALTER TABLE IF EXISTS sesiones_auditoria
ADD COLUMN IF NOT EXISTS respuestas_completadas_json text DEFAULT '[]';

ALTER TABLE IF EXISTS conversaciones
ADD COLUMN IF NOT EXISTS id_respuesta_actual text REFERENCES respuesta_pregunta(id) ON DELETE SET NULL;

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'auditoria-respuestas',
  'auditoria-respuestas',
  false,
  10485760,
  ARRAY['image/jpeg', 'image/png', 'image/webp', 'audio/mpeg', 'audio/ogg', 'audio/mp4', 'application/pdf']
)
ON CONFLICT (id) DO UPDATE
SET
  public = false,
  file_size_limit = 10485760,
  allowed_mime_types = ARRAY['image/jpeg', 'image/png', 'image/webp', 'audio/mpeg', 'audio/ogg', 'audio/mp4', 'application/pdf'];

DROP POLICY IF EXISTS "storage_auditoria_respuestas_upload" ON storage.objects;
CREATE POLICY "storage_auditoria_respuestas_upload"
ON storage.objects
FOR INSERT
WITH CHECK (
  bucket_id = 'auditoria-respuestas'
  AND auth.uid() IS NOT NULL
);

DROP POLICY IF EXISTS "storage_auditoria_respuestas_read" ON storage.objects;
CREATE POLICY "storage_auditoria_respuestas_read"
ON storage.objects
FOR SELECT
USING (
  bucket_id = 'auditoria-respuestas'
  AND auth.uid() IS NOT NULL
);

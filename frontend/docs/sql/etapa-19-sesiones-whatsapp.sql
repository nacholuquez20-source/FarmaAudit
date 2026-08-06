-- Etapa 19: Persistencia de las sesiones de auditoría por WhatsApp (flujo v2)
-- Ejecutar en Supabase SQL Editor. Es idempotente: se puede correr más de una vez.
--
-- Por qué existe: hasta ahora la sesión de auditoría vivía SOLO en un dict del
-- proceso Python (audit_session.py). Cualquier redeploy de Railway borraba las
-- auditorías en curso sin avisarle a nadie, y el auditor seguía mandando fotos a
-- un bot que ya no sabía quién era. Con WhatsApp como único canal de captura eso
-- dejó de ser tolerable.

CREATE TABLE IF NOT EXISTS sesiones_whatsapp (
  -- La PK por teléfono expresa en el esquema la invariante "un auditor tiene
  -- como máximo una auditoría en curso", que antes sólo existía implícitamente
  -- en la forma del dict indexado por teléfono.
  telefono         TEXT PRIMARY KEY,

  id_sesion        TEXT        NOT NULL,

  -- Columnas desnormalizadas desde `data` para que el job de expiración y las
  -- consultas de diagnóstico no tengan que abrir el JSON.
  estado           TEXT        NOT NULL,
  sucursal_id      TEXT,
  expires_at       TIMESTAMPTZ NOT NULL,
  last_message_at  TIMESTAMPTZ NOT NULL,

  -- AuditSession.to_dict() completo: scores por bloque, marcas, fotos, desvíos,
  -- cola de verificación y campos post-auditoría.
  data             JSONB       NOT NULL,

  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- El job de expiración barre por estas dos columnas.
CREATE INDEX IF NOT EXISTS idx_sesiones_whatsapp_expires
  ON sesiones_whatsapp (expires_at);

CREATE INDEX IF NOT EXISTS idx_sesiones_whatsapp_last_message
  ON sesiones_whatsapp (last_message_at);

-- RLS: nadie del panel toca esto.
--
-- El bot escribe con la service key, que omite RLS por completo. Las sesiones en
-- curso son estado interno del canal de WhatsApp: el panel no las lee ni las
-- escribe, así que la política correcta es negar todo para usuarios de panel.
-- Mismo criterio que webhook_dedup (supabase_setup.sql).
ALTER TABLE sesiones_whatsapp ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS sesiones_whatsapp_deny_all ON sesiones_whatsapp;
CREATE POLICY sesiones_whatsapp_deny_all ON sesiones_whatsapp
  FOR ALL USING (false) WITH CHECK (false);

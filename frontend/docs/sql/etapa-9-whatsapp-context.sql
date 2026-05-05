-- Etapa 9 - Contexto de mensajes salientes de WhatsApp
-- Permite detectar cuando el auditor responde citando el mensaje del bot
-- que enuncia un bloque, para registrar aclaraciones del bloque correcto.

CREATE TABLE IF NOT EXISTS whatsapp_bot_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  whatsapp_message_id text UNIQUE NOT NULL,
  telefono text NOT NULL,
  id_sesion text REFERENCES sesiones_auditoria(id_sesion) ON DELETE CASCADE,
  bloque_id text,
  bloque_nombre text,
  tipo text NOT NULL DEFAULT 'perfumeria_block',
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_bot_messages_wamid
  ON whatsapp_bot_messages(whatsapp_message_id);

CREATE INDEX IF NOT EXISTS idx_whatsapp_bot_messages_sesion
  ON whatsapp_bot_messages(id_sesion, bloque_id);

CREATE INDEX IF NOT EXISTS idx_whatsapp_bot_messages_phone
  ON whatsapp_bot_messages(telefono, created_at DESC);

ALTER TABLE whatsapp_bot_messages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "whatsapp_bot_messages_admin_auditor_read" ON whatsapp_bot_messages;
CREATE POLICY "whatsapp_bot_messages_admin_auditor_read"
  ON whatsapp_bot_messages FOR SELECT
  USING (
    auth.uid() IS NOT NULL
    AND (SELECT role FROM profiles WHERE id = auth.uid()) IN ('admin', 'auditor')
  );

-- El backend usa SUPABASE_SERVICE_KEY y bypassea RLS para INSERT/UPSERT.

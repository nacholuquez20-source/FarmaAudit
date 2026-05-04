-- Etapa 6 - Evidencias en Storage, chat interno y notificaciones in-app

-- 1. Nuevo tipo de evento para chat interno
ALTER TABLE desvio_eventos
DROP CONSTRAINT IF EXISTS desvio_eventos_tipo_check;

ALTER TABLE desvio_eventos
ADD CONSTRAINT desvio_eventos_tipo_check
CHECK (tipo IN ('creacion','contacto','respuesta','cierre','nota','evidencia','mensaje'));

-- 2. Notificaciones in-app
CREATE TABLE IF NOT EXISTS desvio_notificaciones (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  id_gestion  text NOT NULL REFERENCES gestion(id_gestion) ON DELETE CASCADE,
  user_id     uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tipo        text NOT NULL CHECK (tipo IN ('mensaje_nuevo','estado_cambio','vencimiento_proximo')),
  leida       boolean NOT NULL DEFAULT false,
  created_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notif_user ON desvio_notificaciones(user_id, leida);
CREATE INDEX IF NOT EXISTS idx_notif_gestion ON desvio_notificaciones(id_gestion);

ALTER TABLE desvio_notificaciones ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "notif_own_read" ON desvio_notificaciones;
CREATE POLICY "notif_own_read"
ON desvio_notificaciones
FOR SELECT
USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "notif_own_update" ON desvio_notificaciones;
CREATE POLICY "notif_own_update"
ON desvio_notificaciones
FOR UPDATE
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "notif_insert_auth" ON desvio_notificaciones;
CREATE POLICY "notif_insert_auth"
ON desvio_notificaciones
FOR INSERT
WITH CHECK (auth.uid() IS NOT NULL);

-- 3. Bucket privado para evidencias. Tambien puede crearse desde Dashboard:
--    Storage -> New bucket -> desvio-evidencias -> Private -> Max 10MB.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'desvio-evidencias',
  'desvio-evidencias',
  false,
  10485760,
  ARRAY['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
)
ON CONFLICT (id) DO UPDATE
SET
  public = false,
  file_size_limit = 10485760,
  allowed_mime_types = ARRAY['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];

-- 4. RLS en objetos de Storage
DROP POLICY IF EXISTS "storage_evidencias_upload" ON storage.objects;
CREATE POLICY "storage_evidencias_upload"
ON storage.objects
FOR INSERT
WITH CHECK (
  bucket_id = 'desvio-evidencias'
  AND auth.uid() IS NOT NULL
  AND EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid())
);

DROP POLICY IF EXISTS "storage_evidencias_read" ON storage.objects;
CREATE POLICY "storage_evidencias_read"
ON storage.objects
FOR SELECT
USING (
  bucket_id = 'desvio-evidencias'
  AND auth.uid() IS NOT NULL
  AND EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid())
);

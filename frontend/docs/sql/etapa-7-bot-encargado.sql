-- Etapa 7 - Bot WhatsApp para encargados de sucursal

-- Garantiza que profiles tenga la sucursal asignada para usuarios role='sucursal'.
ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS id_sucursal text REFERENCES sucursales(id);

-- Extender tipos de evento en desvio_eventos para mensajes internos/bot.
ALTER TABLE desvio_eventos
DROP CONSTRAINT IF EXISTS desvio_eventos_tipo_check;

ALTER TABLE desvio_eventos
ADD CONSTRAINT desvio_eventos_tipo_check
CHECK (tipo IN ('creacion','contacto','respuesta','cierre','nota','evidencia','mensaje'));

-- Tabla de notificaciones in-app para auditor/admin.
CREATE TABLE IF NOT EXISTS desvio_notificaciones (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  id_gestion  text NOT NULL REFERENCES gestion(id_gestion) ON DELETE CASCADE,
  user_id     uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tipo        text NOT NULL CHECK (
    tipo IN ('mensaje_nuevo','encargado_respondio','estado_cambio','vencimiento_proximo')
  ),
  leida       boolean NOT NULL DEFAULT false,
  created_at  timestamptz DEFAULT now()
);

ALTER TABLE desvio_notificaciones
DROP CONSTRAINT IF EXISTS desvio_notificaciones_tipo_check;

ALTER TABLE desvio_notificaciones
ADD CONSTRAINT desvio_notificaciones_tipo_check
CHECK (tipo IN ('mensaje_nuevo','encargado_respondio','estado_cambio','vencimiento_proximo'));

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

-- Bucket privado para evidencias del bot y la app.
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

DROP POLICY IF EXISTS "storage_evidencias_upload" ON storage.objects;
CREATE POLICY "storage_evidencias_upload"
ON storage.objects
FOR INSERT
WITH CHECK (
  bucket_id = 'desvio-evidencias'
  AND auth.uid() IS NOT NULL
);

DROP POLICY IF EXISTS "storage_evidencias_read" ON storage.objects;
CREATE POLICY "storage_evidencias_read"
ON storage.objects
FOR SELECT
USING (
  bucket_id = 'desvio-evidencias'
  AND auth.uid() IS NOT NULL
);

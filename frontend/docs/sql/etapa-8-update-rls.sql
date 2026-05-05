-- Etapa 8 UPDATE - Agregar RLS sin romper la tabla existente

-- 1. Agregar columna user_id_auditor (si no existe)
ALTER TABLE IF EXISTS respuesta_pregunta
ADD COLUMN IF NOT EXISTS user_id_auditor uuid REFERENCES auth.users(id) ON DELETE CASCADE;

-- 2. Mejorar constraint estado (drop + recreate con nombre)
ALTER TABLE IF EXISTS respuesta_pregunta
DROP CONSTRAINT IF EXISTS desvio_eventos_tipo_check;

ALTER TABLE IF EXISTS respuesta_pregunta
DROP CONSTRAINT IF EXISTS estado_check;

ALTER TABLE IF EXISTS respuesta_pregunta
ADD CONSTRAINT estado_check
CHECK (estado IN ('recolectando', 'completada', 'descartada'));

-- 3. Habilitar RLS en respuesta_pregunta
ALTER TABLE IF EXISTS respuesta_pregunta ENABLE ROW LEVEL SECURITY;

-- 4. Crear RLS policies en respuesta_pregunta
DROP POLICY IF EXISTS "respuesta_own_select" ON respuesta_pregunta;
CREATE POLICY "respuesta_own_select"
  ON respuesta_pregunta FOR SELECT
  USING (
    auth.uid() = user_id_auditor OR
    (SELECT role FROM profiles WHERE id = auth.uid()) = 'admin'
  );

DROP POLICY IF EXISTS "respuesta_own_update" ON respuesta_pregunta;
CREATE POLICY "respuesta_own_update"
  ON respuesta_pregunta FOR UPDATE
  USING (auth.uid() = user_id_auditor);

DROP POLICY IF EXISTS "respuesta_bot_insert" ON respuesta_pregunta;
CREATE POLICY "respuesta_bot_insert"
  ON respuesta_pregunta FOR INSERT
  WITH CHECK (auth.uid() IS NOT NULL);

-- 5. Habilitar RLS en respuesta_pregunta_audit_log
ALTER TABLE IF EXISTS respuesta_pregunta_audit_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "audit_log_own_read" ON respuesta_pregunta_audit_log;
CREATE POLICY "audit_log_own_read"
  ON respuesta_pregunta_audit_log FOR SELECT
  USING (
    id_respuesta IN (
      SELECT id FROM respuesta_pregunta
      WHERE auth.uid() = user_id_auditor
    )
    OR (SELECT role FROM profiles WHERE id = auth.uid()) = 'admin'
  );

-- 6. Actualizar Storage policies con RLS mejorado (path-based)
DROP POLICY IF EXISTS "storage_auditoria_respuestas_upload" ON storage.objects;
CREATE POLICY "storage_auditoria_respuestas_upload"
ON storage.objects
FOR INSERT
WITH CHECK (
  bucket_id = 'auditoria-respuestas'
  AND auth.uid() IS NOT NULL
  AND (
    -- El archivo comienza con el UUID del auditor (user_id)
    name LIKE CONCAT(auth.uid()::text, '/%')
    OR
    -- O el teléfono del auditor (fallback para compatibilidad)
    name LIKE CONCAT((SELECT telefono FROM profiles WHERE id = auth.uid()), '/%')
    OR
    -- Admin puede subir en cualquier lado
    (SELECT role FROM profiles WHERE id = auth.uid()) = 'admin'
  )
);

DROP POLICY IF EXISTS "storage_auditoria_respuestas_read" ON storage.objects;
CREATE POLICY "storage_auditoria_respuestas_read"
ON storage.objects
FOR SELECT
USING (
  bucket_id = 'auditoria-respuestas'
  AND auth.uid() IS NOT NULL
  AND (
    -- El auditor puede leer sus propios archivos
    name LIKE CONCAT(auth.uid()::text, '/%')
    OR
    -- O archivos del teléfono (fallback)
    name LIKE CONCAT((SELECT telefono FROM profiles WHERE id = auth.uid()), '/%')
    OR
    -- Admin puede leer todo
    (SELECT role FROM profiles WHERE id = auth.uid()) = 'admin'
  )
);

-- ✅ FIN - Sin cambios de datos, solo estructura + seguridad

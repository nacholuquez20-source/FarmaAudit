-- Etapa 11 - Agregar soporte para auditoría libre de perfumería con bloques
-- Solo agrega la columna bloques_auditoria_json a sesiones_auditoria

-- Agregar columna si no existe
ALTER TABLE IF EXISTS public.sesiones_auditoria
ADD COLUMN IF NOT EXISTS bloques_auditoria_json text DEFAULT '{}';

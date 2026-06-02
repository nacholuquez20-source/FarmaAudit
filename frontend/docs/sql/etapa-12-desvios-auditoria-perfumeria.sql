-- Etapa 12 - Tabla para gestionar desvíos de auditoría perfumería
-- Permite que auditores gestionen desvíos encontrados, reciban respuestas de responsables y cierren casos

CREATE TABLE IF NOT EXISTS public.desvios_auditoria_perfumeria (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  id_sesion TEXT NOT NULL REFERENCES public.sesiones_auditoria(id_sesion) ON DELETE CASCADE,
  sucursal_id TEXT NOT NULL,
  sucursal_nombre TEXT,
  bloque TEXT NOT NULL, -- LIMPIEZA, STOCK, OFERTAS, BURBUJAS
  descripcion TEXT NOT NULL,
  severidad TEXT DEFAULT 'Media', -- Alta, Media, Baja
  foto_url TEXT,

  -- Responsable de la sucursal
  responsable TEXT,
  tel_responsable TEXT,

  -- Auditor que detectó
  auditor_nombre TEXT,
  auditor_telefono TEXT,

  -- Estados del desvío
  estado TEXT DEFAULT 'abierto', -- abierto, respondido, cerrado

  -- Timestamps
  timestamp_creacion TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  timestamp_notificacion TIMESTAMP WITH TIME ZONE,
  timestamp_respuesta TIMESTAMP WITH TIME ZONE,
  timestamp_cierre TIMESTAMP WITH TIME ZONE,

  -- Respuesta del responsable
  respuesta_responsable TEXT,
  respuesta_foto_url TEXT,
  respuesta_timestamp TIMESTAMP WITH TIME ZONE,

  -- Cierre
  cerrado_por TEXT, -- nombre del auditor que cerró
  motivo_cierre TEXT, -- Solucionado, Válido como está, Duplicado, etc

  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índices para queries comunes
CREATE INDEX IF NOT EXISTS idx_desvios_auditoria_sucursal_estado
  ON public.desvios_auditoria_perfumeria(sucursal_id, estado);

CREATE INDEX IF NOT EXISTS idx_desvios_auditoria_auditor
  ON public.desvios_auditoria_perfumeria(auditor_telefono);

CREATE INDEX IF NOT EXISTS idx_desvios_auditoria_responsable
  ON public.desvios_auditoria_perfumeria(tel_responsable);

CREATE INDEX IF NOT EXISTS idx_desvios_auditoria_estado_timestamp
  ON public.desvios_auditoria_perfumeria(estado, timestamp_creacion DESC);

-- RLS: Los auditores ven los desvíos que ellos crearon o de su zona
ALTER TABLE public.desvios_auditoria_perfumeria ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Auditores ven desvíos de su zona" ON public.desvios_auditoria_perfumeria;
CREATE POLICY "Auditores ven desvíos de su zona"
  ON public.desvios_auditoria_perfumeria
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.maestro_auditores ma
      JOIN public.sucursales s ON ma.cuadrilla = s.zona
      WHERE ma.telefono = auth.jwt() ->> 'phone_number'
      AND s.id = desvios_auditoria_perfumeria.sucursal_id
    )
  )
);

-- Responsables ven desvíos de su sucursal
DROP POLICY IF EXISTS "Responsables ven desvíos de su sucursal" ON public.desvios_auditoria_perfumeria;
CREATE POLICY "Responsables ven desvíos de su sucursal"
  ON public.desvios_auditoria_perfumeria
  FOR SELECT
  USING (
    tel_responsable = auth.jwt() ->> 'phone_number'
  )
);

-- Auditores pueden actualizar desvíos (cerrar, comentar)
DROP POLICY IF EXISTS "Auditores pueden actualizar desvíos" ON public.desvios_auditoria_perfumeria;
CREATE POLICY "Auditores pueden actualizar desvíos"
  ON public.desvios_auditoria_perfumeria
  FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM public.maestro_auditores ma
      JOIN public.sucursales s ON ma.cuadrilla = s.zona
      WHERE ma.telefono = auth.jwt() ->> 'phone_number'
      AND s.id = desvios_auditoria_perfumeria.sucursal_id
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.maestro_auditores ma
      JOIN public.sucursales s ON ma.cuadrilla = s.zona
      WHERE ma.telefono = auth.jwt() ->> 'phone_number'
      AND s.id = desvios_auditoria_perfumeria.sucursal_id
    )
  );

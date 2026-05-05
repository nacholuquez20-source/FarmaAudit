-- Etapa 10 - Bandeja de revision para desvios detectados por WhatsApp
-- El bot guarda hallazgos como borradores; el frontend los aprueba o descarta.

CREATE TABLE IF NOT EXISTS public.desvios_borrador (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  id_respuesta text REFERENCES public.respuesta_pregunta(id) ON DELETE SET NULL,
  id_sesion text REFERENCES public.sesiones_auditoria(id_sesion) ON DELETE SET NULL,
  id_sucursal text REFERENCES public.sucursales(id) ON DELETE SET NULL,
  sucursal text NOT NULL DEFAULT '',
  bloque_id text NOT NULL DEFAULT '',
  bloque_nombre text NOT NULL DEFAULT '',
  descripcion text NOT NULL,
  severidad_sugerida text NOT NULL DEFAULT 'Media'
    CHECK (severidad_sugerida IN ('Alta', 'Media', 'Baja')),
  estado text NOT NULL DEFAULT 'pendiente'
    CHECK (estado IN ('pendiente', 'aprobado', 'descartado', 'convertido')),
  evidencias_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  respuesta_consolidada text,
  auditor_nombre text,
  confianza numeric,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  id_reporte text,
  id_gestion text,
  aprobado_por uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  aprobado_at timestamptz,
  descartado_por uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  descartado_at timestamptz,
  razon_descarte text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_desvios_borrador_estado
  ON public.desvios_borrador(estado, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_desvios_borrador_sesion
  ON public.desvios_borrador(id_sesion, id_respuesta);

CREATE INDEX IF NOT EXISTS idx_desvios_borrador_sucursal
  ON public.desvios_borrador(id_sucursal, estado);

ALTER TABLE public.desvios_borrador ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "desvios_borrador_select_scope" ON public.desvios_borrador;
CREATE POLICY "desvios_borrador_select_scope"
  ON public.desvios_borrador FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = auth.uid()
        AND p.role IN ('admin', 'auditor')
    )
    OR EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = auth.uid()
        AND p.role = 'sucursal'
        AND p.id_sucursal IS NOT NULL
        AND p.id_sucursal = desvios_borrador.id_sucursal
    )
  );

DROP POLICY IF EXISTS "desvios_borrador_update_admin_auditor" ON public.desvios_borrador;
CREATE POLICY "desvios_borrador_update_admin_auditor"
  ON public.desvios_borrador FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = auth.uid()
        AND p.role IN ('admin', 'auditor')
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = auth.uid()
        AND p.role IN ('admin', 'auditor')
    )
  );

-- El backend usa SUPABASE_SERVICE_KEY y bypassea RLS para INSERT.

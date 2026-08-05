-- Etapa 15: infraestructura del Modulo Campanias (Fase 2)
-- Ver ARQUITECTURA_DESVIOS_CAMPANIAS.md, Modulo 2, seccion 2.1.
-- Esta etapa solo crea el esquema + RLS para admin/auditor. La vista del
-- responsable de sucursal (/mis-campanias) y el bot de WhatsApp llegan en
-- Fase 3/4, con su propia migracion de RLS scoped a sucursal.

-- ============ Segmentacion de sucursales (para el paso "Alcance" del wizard) ============

ALTER TABLE sucursales ADD COLUMN IF NOT EXISTS categoria char(1);
ALTER TABLE sucursales ADD COLUMN IF NOT EXISTS tiene_perfumeria boolean NOT NULL DEFAULT false;

-- ============ Catalogo de marcas ============

CREATE TABLE IF NOT EXISTS marcas (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre      text NOT NULL UNIQUE,
  activo      boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ============ Campanias ============

CREATE TABLE IF NOT EXISTS campanias (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre            text NOT NULL,
  marca_id          uuid NOT NULL REFERENCES marcas(id),
  estado            text NOT NULL DEFAULT 'Borrador' CHECK (
    estado IN ('Borrador', 'Activa', 'En_seguimiento', 'Finalizada', 'Cancelada')
  ),
  fecha_inicio      date,
  fecha_fin         date,
  -- Vigencia del acuerdo comercial laboratorio<->cadena (texto, no daterange:
  -- consistente con el resto del schema que usa columnas date planas, mas
  -- simple de consumir desde supabase-js/PostgREST que un rango nativo).
  acuerdo_desde     date,
  acuerdo_hasta     date,
  contraprestacion  text,
  creado_por        uuid REFERENCES profiles(id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campanias_marca ON campanias(marca_id);
CREATE INDEX IF NOT EXISTS idx_campanias_estado ON campanias(estado);

-- ============ Acciones sugeridas por campania ============
-- "burbuja_precio" (carteleria fisica, verificable con foto) y "descuento_caja"
-- (activacion del descuento en el sistema de caja, informativa/administrativa,
-- NO la verifica el encargado con una foto) se modelan como acciones distintas
-- a proposito: son cosas distintas en la operacion real de la sucursal.
-- No usar el nombre "burbujas" a secas: colisiona con el bloque de auditoria
-- de perfumeria BURBUJAS ("Displays & Senalizacion", ver audit_session.py).

CREATE TABLE IF NOT EXISTS campania_acciones (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campania_id           uuid NOT NULL REFERENCES campanias(id) ON DELETE CASCADE,
  tipo                  text NOT NULL CHECK (
    tipo IN ('exhibicion', 'material_pop', 'burbuja_precio', 'descuento_caja', 'custom')
  ),
  descripcion           text,
  requiere_foto         boolean NOT NULL DEFAULT true,
  verificable_por_foto  boolean NOT NULL DEFAULT true,
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campania_acciones_campania ON campania_acciones(campania_id);

-- ============ Tareas por sucursal ============
-- Estado simplificado (sin "En_ejecucion" persistente): nadie declara que
-- "esta por empezar" una tarea en la operacion real. "En ejecucion" es un
-- estado DERIVADO en la UI/bot a partir de vista_at IS NOT NULL AND estado = 'Pendiente'.

CREATE TABLE IF NOT EXISTS campania_tareas (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campania_id      uuid NOT NULL REFERENCES campanias(id) ON DELETE CASCADE,
  accion_id        uuid NOT NULL REFERENCES campania_acciones(id) ON DELETE CASCADE,
  id_sucursal      text NOT NULL REFERENCES sucursales(id),
  responsable      text,
  tel_responsable  text,
  estado           text NOT NULL DEFAULT 'Pendiente' CHECK (
    estado IN ('Pendiente', 'Completada', 'Bloqueada_por_insumo', 'Verificada')
  ),
  vista_at         timestamptz,
  plazo_fecha      date,
  evidencia_path   text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campania_tareas_campania ON campania_tareas(campania_id);
CREATE INDEX IF NOT EXISTS idx_campania_tareas_sucursal ON campania_tareas(id_sucursal, estado);

-- ============ Trazabilidad de eventos por tarea ============
-- Analoga a desvio_eventos, pero para tareas de campania (no mezclar en la
-- misma tabla: son entidades distintas).

CREATE TABLE IF NOT EXISTS campania_eventos (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tarea_id     uuid NOT NULL REFERENCES campania_tareas(id) ON DELETE CASCADE,
  tipo         text NOT NULL CHECK (
    tipo IN ('creacion', 'vista', 'completada', 'evidencia', 'bloqueo_insumo', 'rechazo', 'verificacion', 'nota')
  ),
  comentario   text,
  actor_id     uuid REFERENCES profiles(id),
  actor_nombre text,
  metadata     jsonb,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campania_eventos_tarea ON campania_eventos(tarea_id);

-- ============ Notificaciones in-app (analoga a desvio_notificaciones) ============

CREATE TABLE IF NOT EXISTS campania_notificaciones (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tarea_id    uuid NOT NULL REFERENCES campania_tareas(id) ON DELETE CASCADE,
  user_id     uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tipo        text NOT NULL CHECK (
    tipo IN ('tarea_completada', 'insumo_solicitado', 'insumo_recibido')
  ),
  leida       boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campania_notif_user ON campania_notificaciones(user_id, leida);
CREATE INDEX IF NOT EXISTS idx_campania_notif_tarea ON campania_notificaciones(tarea_id);

-- ============ Solicitudes de insumo ============
-- Bifurcada por "proveedor": el material POP/carteleria de marca lo trae el
-- APM/repositor del LABORATORIO, no el admin de la cadena. Si proveedor =
-- laboratorio_apm, el flujo NO es "aprobar y enviar" sino "escalar al contacto
-- de trade de la cadena para reclamar al labo" (estado Escalado_a_labo, sin
-- boton interno de aprobacion). Solo proveedor = cadena sigue el circuito
-- interno normal (Aprobado -> Enviado -> Recibido).

CREATE TABLE IF NOT EXISTS solicitudes_insumo (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tarea_id       uuid NOT NULL REFERENCES campania_tareas(id) ON DELETE CASCADE,
  tipo_insumo    text NOT NULL CHECK (tipo_insumo IN ('carteleria', 'material_pop', 'stock', 'otro')),
  detalle        text,
  cantidad       text,
  proveedor      text NOT NULL CHECK (proveedor IN ('laboratorio_apm', 'cadena')),
  estado         text NOT NULL DEFAULT 'Solicitado' CHECK (
    estado IN ('Solicitado', 'Escalado_a_labo', 'Aprobado', 'Rechazado', 'Enviado', 'Recibido')
  ),
  contacto_trade text,
  aprobado_por   uuid REFERENCES profiles(id),
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_solicitudes_insumo_tarea ON solicitudes_insumo(tarea_id);
CREATE INDEX IF NOT EXISTS idx_solicitudes_insumo_estado ON solicitudes_insumo(estado);

-- ============ Resultados de venta real (carga manual, sell-out) ============
-- El compliance de tareas ("% completado") no mide si la campania vendio algo.
-- Carga manual minima: venta del periodo de campania vs. periodo base.
-- Integracion POS automatica queda para una fase futura.

CREATE TABLE IF NOT EXISTS campania_resultados (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campania_id              uuid NOT NULL REFERENCES campanias(id) ON DELETE CASCADE,
  id_sucursal              text NOT NULL REFERENCES sucursales(id),
  venta_periodo_campania   numeric,
  venta_periodo_base       numeric,
  unidad                   text NOT NULL DEFAULT 'unidades' CHECK (unidad IN ('unidades', 'pesos')),
  cargado_por              uuid REFERENCES profiles(id),
  created_at               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campania_resultados_campania ON campania_resultados(campania_id);

-- ============ Row Level Security ============
-- Alcance de esta etapa: admin y auditor (quienes arman/siguen campanias).
-- El responsable de sucursal (rol 'sucursal') todavia no tiene UI para esto
-- (llega en Fase 3/4 con /mis-campanias) -- se agrega su policy scoped en esa
-- migracion, no aca, para no adivinar una policy que nadie va a poder probar.

ALTER TABLE marcas ENABLE ROW LEVEL SECURITY;
ALTER TABLE campanias ENABLE ROW LEVEL SECURITY;
ALTER TABLE campania_acciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE campania_tareas ENABLE ROW LEVEL SECURITY;
ALTER TABLE campania_eventos ENABLE ROW LEVEL SECURITY;
ALTER TABLE campania_notificaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE solicitudes_insumo ENABLE ROW LEVEL SECURITY;
ALTER TABLE campania_resultados ENABLE ROW LEVEL SECURITY;

-- Marcas: admin y auditor leen (catalogo compartido para el wizard); solo admin escribe.
DROP POLICY IF EXISTS "marcas_read" ON marcas;
CREATE POLICY "marcas_read" ON marcas FOR SELECT USING (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
);
DROP POLICY IF EXISTS "marcas_admin_write" ON marcas;
CREATE POLICY "marcas_admin_write" ON marcas FOR ALL USING (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin')
) WITH CHECK (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin')
);

-- Campanias y entidades dependientes: admin y auditor full access (mismo
-- criterio que "gestion_select_scope": ambos roles gestionan campanias).
DROP POLICY IF EXISTS "campanias_admin_auditor" ON campanias;
CREATE POLICY "campanias_admin_auditor" ON campanias FOR ALL USING (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
) WITH CHECK (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
);

DROP POLICY IF EXISTS "campania_acciones_admin_auditor" ON campania_acciones;
CREATE POLICY "campania_acciones_admin_auditor" ON campania_acciones FOR ALL USING (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
) WITH CHECK (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
);

DROP POLICY IF EXISTS "campania_tareas_admin_auditor" ON campania_tareas;
CREATE POLICY "campania_tareas_admin_auditor" ON campania_tareas FOR ALL USING (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
) WITH CHECK (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
);

DROP POLICY IF EXISTS "campania_eventos_admin_auditor" ON campania_eventos;
CREATE POLICY "campania_eventos_admin_auditor" ON campania_eventos FOR ALL USING (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
) WITH CHECK (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
);

DROP POLICY IF EXISTS "campania_notif_own_read" ON campania_notificaciones;
CREATE POLICY "campania_notif_own_read" ON campania_notificaciones FOR SELECT USING (
  auth.uid() = user_id
);
DROP POLICY IF EXISTS "campania_notif_own_update" ON campania_notificaciones;
CREATE POLICY "campania_notif_own_update" ON campania_notificaciones FOR UPDATE USING (
  auth.uid() = user_id
) WITH CHECK (
  auth.uid() = user_id
);
DROP POLICY IF EXISTS "campania_notif_insert_auth" ON campania_notificaciones;
CREATE POLICY "campania_notif_insert_auth" ON campania_notificaciones FOR INSERT WITH CHECK (
  auth.uid() IS NOT NULL
);

DROP POLICY IF EXISTS "solicitudes_insumo_admin_auditor" ON solicitudes_insumo;
CREATE POLICY "solicitudes_insumo_admin_auditor" ON solicitudes_insumo FOR ALL USING (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
) WITH CHECK (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
);

DROP POLICY IF EXISTS "campania_resultados_admin_auditor" ON campania_resultados;
CREATE POLICY "campania_resultados_admin_auditor" ON campania_resultados FOR ALL USING (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
) WITH CHECK (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
);

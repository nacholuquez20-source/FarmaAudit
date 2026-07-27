-- Etapa 14: ciclo de revision de correcciones (aprobar/rechazar) + estado "depende de terceros"
-- Ver ARQUITECTURA_DESVIOS_CAMPANIAS.md, Modulo 1.

ALTER TABLE gestion ADD COLUMN IF NOT EXISTS plazo_fecha_original date;
ALTER TABLE gestion ADD COLUMN IF NOT EXISTS veces_rechazado int NOT NULL DEFAULT 0;
ALTER TABLE gestion ADD COLUMN IF NOT EXISTS en_revision_desde timestamptz;

-- Backfill: preservar el plazo original de los desvios ya existentes.
UPDATE gestion SET plazo_fecha_original = plazo_fecha WHERE plazo_fecha_original IS NULL;

ALTER TABLE gestion
DROP CONSTRAINT IF EXISTS gestion_estado_check;

ALTER TABLE gestion
ADD CONSTRAINT gestion_estado_check
CHECK (estado IN ('Abierta', 'En_proceso', 'En_revision', 'En_gestion_terceros', 'Resuelta', 'Cerrada', 'Vencida'));

CREATE INDEX IF NOT EXISTS idx_gestion_en_revision_desde ON gestion(estado, en_revision_desde);

-- Nuevo tipo de evento: rechazo de una correccion.
ALTER TABLE desvio_eventos
DROP CONSTRAINT IF EXISTS desvio_eventos_tipo_check;

ALTER TABLE desvio_eventos
ADD CONSTRAINT desvio_eventos_tipo_check
CHECK (tipo IN (
  'creacion', 'contacto', 'respuesta', 'cierre', 'nota', 'evidencia',
  'mensaje', 'auditor_hallazgo', 'verificacion_auditoria', 'reincidencia', 'rechazo'
));

-- Nuevo tipo de notificacion: alerta de SLA de revision vencido (interno, para auditor/admin).
ALTER TABLE desvio_notificaciones
DROP CONSTRAINT IF EXISTS desvio_notificaciones_tipo_check;

ALTER TABLE desvio_notificaciones
ADD CONSTRAINT desvio_notificaciones_tipo_check
CHECK (tipo IN ('mensaje_nuevo', 'encargado_respondio', 'estado_cambio', 'vencimiento_proximo', 'sla_revision_vencido'));

-- Etapa 13: columna bloque en gestion para verificación de desvíos en piso
-- Permite filtrar gestiones pendientes por bloque de auditoría (LIMPIEZA/STOCK/OFERTAS/BURBUJAS)

ALTER TABLE gestion ADD COLUMN IF NOT EXISTS bloque text;

-- Backfill por prefijo del campo desvio (path WhatsApp v2)
UPDATE gestion SET bloque = 'LIMPIEZA' WHERE bloque IS NULL AND desvio LIKE 'Limpieza & Organización:%';
UPDATE gestion SET bloque = 'STOCK'    WHERE bloque IS NULL AND desvio LIKE 'Stock & Inventario:%';
UPDATE gestion SET bloque = 'OFERTAS'  WHERE bloque IS NULL AND desvio LIKE 'Ofertas & Exhibición:%';
UPDATE gestion SET bloque = 'BURBUJAS' WHERE bloque IS NULL AND desvio LIKE 'Displays & Señalización:%';

-- Backfill por reportes.area (path endpoint web, area = bloque crudo;
-- path WhatsApp v2, area = 'Perfumeria - {label}')
UPDATE gestion g
SET bloque = r.area
FROM reportes r
WHERE g.bloque IS NULL
  AND g.id_reporte = r.id
  AND r.area IN ('LIMPIEZA', 'STOCK', 'OFERTAS', 'BURBUJAS');

UPDATE gestion g
SET bloque = CASE r.area
    WHEN 'Perfumeria - Limpieza & Organización' THEN 'LIMPIEZA'
    WHEN 'Perfumeria - Stock & Inventario' THEN 'STOCK'
    WHEN 'Perfumeria - Ofertas & Exhibición' THEN 'OFERTAS'
    WHEN 'Perfumeria - Displays & Señalización' THEN 'BURBUJAS'
  END
FROM reportes r
WHERE g.bloque IS NULL
  AND g.id_reporte = r.id
  AND r.area IN (
    'Perfumeria - Limpieza & Organización',
    'Perfumeria - Stock & Inventario',
    'Perfumeria - Ofertas & Exhibición',
    'Perfumeria - Displays & Señalización'
  );

CREATE INDEX IF NOT EXISTS idx_gestion_sucursal_bloque_estado
  ON gestion (id_sucursal, bloque, estado);

-- Permitir los nuevos tipos de evento de la verificación en piso
ALTER TABLE desvio_eventos
DROP CONSTRAINT IF EXISTS desvio_eventos_tipo_check;

ALTER TABLE desvio_eventos
ADD CONSTRAINT desvio_eventos_tipo_check
CHECK (tipo IN (
  'creacion', 'contacto', 'respuesta', 'cierre', 'nota', 'evidencia',
  'mensaje', 'auditor_hallazgo', 'verificacion_auditoria', 'reincidencia'
));

-- Etapa 31: foto de referencia ("asi debe quedar") en acciones de campania (Fase 6)
-- Ver ARQUITECTURA_DESVIOS_CAMPANIAS.md, Modulo 2 (v3) y Modulo 3 (v6, habilitado tambien
-- para tour). Numerada etapa-31: la spec original (redactada sin mirar el repo completo)
-- proponia etapa-17/18, ya tomadas; una revision posterior corrigio a etapa-20/21, tambien
-- tomadas (el repo ya llega hasta etapa-30-sucursales-geo.sql). Verificado contra el listado
-- real de frontend/docs/sql/ al momento de crear esta migracion.

ALTER TABLE campania_acciones ADD COLUMN IF NOT EXISTS imagen_referencia_path text;

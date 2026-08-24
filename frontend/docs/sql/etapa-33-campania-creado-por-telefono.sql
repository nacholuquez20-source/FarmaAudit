-- Etapa 33: trazabilidad de campanias/tours creados por WhatsApp (Fase 8)
-- Ver ARQUITECTURA_DESVIOS_CAMPANIAS.md, Modulo 4. El bot identifica al auditor solo
-- por telefono (tabla `auditores`, sin relacion a `profiles`/auth.uid()), asi que
-- `campanias.creado_por` (FK a profiles) queda NULL cuando el creador es el bot -- sin
-- esta columna se pierde de vista que auditor lanzo que campania por WhatsApp.
-- Verificado contra el listado real de este directorio antes de numerar (llega a etapa-32).

ALTER TABLE campanias ADD COLUMN IF NOT EXISTS creado_por_telefono text;

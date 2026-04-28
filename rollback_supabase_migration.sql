-- Rollback for the AuditBot Supabase migration.
-- Drops application tables in reverse dependency order.

drop table if exists resultados_perfumeria cascade;
drop table if exists control_stock cascade;
drop table if exists gestion cascade;
drop table if exists reportes cascade;
drop table if exists sesiones_auditoria cascade;
drop table if exists pendientes cascade;
drop table if exists conversaciones cascade;
drop table if exists checklist_perfumeria cascade;
drop table if exists checklist_plantillas cascade;
drop table if exists catalogo_areas cascade;
drop table if exists sucursales cascade;
drop table if exists auditores cascade;
drop table if exists webhook_dedup cascade;
drop table if exists profiles cascade;

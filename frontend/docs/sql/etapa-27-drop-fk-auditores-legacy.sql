-- Etapa 27: sacar las FK legacy hacia auditores
-- Por que: bug real en producción, encontrado 2026-08-12 — un auditor nuevo
-- cargado desde Admin → Usuarios WhatsApp (usuarios_whatsapp, etapa-21) no
-- puede iniciar una auditoría por WhatsApp. create_sesion() falla con
-- "insert or update on table sesiones_auditoria violates foreign key
-- constraint sesiones_auditoria_telefono_auditor_fkey" porque esa columna
-- sigue apuntando a la tabla legacy `auditores`, que etapa-21 dejó de
-- escribir (solo hizo backfill hacia usuarios_whatsapp, nunca al revés).
--
-- Diagnóstico (ver información_schema, corrido manualmente): dos tablas
-- tienen esta FK — sesiones_auditoria (confirmada rota) y pendientes (mismo
-- patrón, no verificada en producción todavía pero bloquearía el flujo
-- legacy de confirmación de hallazgos para cualquier auditor nuevo).
--
-- Fix: sacar la FK, no redirigirla a usuarios_whatsapp. La validación real
-- de "es un auditor activo" ya la hace resolve_whatsapp_user()/get_auditor()
-- en la capa de aplicación antes de llegar a estos INSERT (ver identity.py) —
-- la FK en la base era redundante y nunca protegía nada que la app no
-- validara ya. Consistente con la nota ya documentada del proyecto: la
-- tabla auditores es un remanente del backfill de etapa-21 pendiente de
-- borrar por completo.

alter table sesiones_auditoria drop constraint if exists sesiones_auditoria_telefono_auditor_fkey;
alter table pendientes drop constraint if exists pendientes_telefono_auditor_fkey;

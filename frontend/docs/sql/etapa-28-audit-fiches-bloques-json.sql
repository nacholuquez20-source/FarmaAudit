-- Etapa 28: audit_fiches.bloques_json
-- Por que: bug real encontrado en auditoria de codigo — get_previous_audit()
-- (audit_database.py) prometia mostrarle al auditor la tendencia "subio/bajo
-- vs. la ultima auditoria" de cada bloque, pero consultaba una tabla que no
-- existe (`reporte`, la real es `reportes`) y una columna `puntuaciones` que
-- nunca se escribia en ningun lado. El puntaje por bloque de cada auditoria
-- (session.bloques, un dict {LIMPIEZA: 3, STOCK: 4, ...}) jamas se persistia
-- fuera de la sesion efimera — ni siquiera arreglando el nombre de tabla
-- habria dato para mostrar. La comparacion devolvia None siempre, en silencio.
--
-- Fix: guardar session.bloques en audit_fiches al crear cada ficha
-- (audit_fiches_manager.py, ya en codigo) y leer de ahi la ficha mas reciente
-- de la sucursal (audit_database.py, ya en codigo). Las fichas historicas
-- quedan en null a proposito — no hay forma de reconstruir ese dato
-- retroactivamente, la comparacion simplemente no aparece para la primera
-- auditoria posterior a una ficha vieja.

alter table audit_fiches add column if not exists bloques_json jsonb;

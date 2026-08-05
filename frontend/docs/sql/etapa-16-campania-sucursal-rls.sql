-- Etapa 16: acceso del responsable de sucursal a sus tareas de campania (Fase 3)
-- Ver ARQUITECTURA_DESVIOS_CAMPANIAS.md, Modulo 2. Etapa 15 dejo estas tablas
-- solo para admin/auditor a proposito ("no adivinar una policy que nadie iba
-- a poder probar"); ahora que /mis-campanias existe, se agrega el acceso.
--
-- Sigue el mismo patron ya usado por gestion/desvio_eventos:
--  - campania_tareas es la entidad "padre" (equivalente a gestion): el
--    responsable solo ve/edita las tareas de SU sucursal.
--  - campania_eventos y solicitudes_insumo son entidades "hijas" (equivalente
--    a desvio_eventos): cualquier perfil autenticado puede leer/insertar,
--    el scoping real ya paso por la tarea padre. No se re-valida sucursal a
--    nivel de fila hija -- es el mismo criterio que ya usa desvio_eventos
--    (etapa-2.sql), no una relajacion nueva.

-- ============ campania_tareas: acceso scoped a la propia sucursal ============

DROP POLICY IF EXISTS "campania_tareas_sucursal_select" ON campania_tareas;
CREATE POLICY "campania_tareas_sucursal_select" ON campania_tareas FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM profiles p
    WHERE p.id = auth.uid() AND p.role = 'sucursal'
    AND p.id_sucursal IS NOT NULL
    AND campania_tareas.id_sucursal = p.id_sucursal
  )
);

DROP POLICY IF EXISTS "campania_tareas_sucursal_update" ON campania_tareas;
CREATE POLICY "campania_tareas_sucursal_update" ON campania_tareas FOR UPDATE USING (
  EXISTS (
    SELECT 1 FROM profiles p
    WHERE p.id = auth.uid() AND p.role = 'sucursal'
    AND p.id_sucursal IS NOT NULL
    AND campania_tareas.id_sucursal = p.id_sucursal
  )
);

-- ============ campania_eventos: cualquier perfil autenticado (como desvio_eventos) ============

DROP POLICY IF EXISTS "campania_eventos_admin_auditor" ON campania_eventos;
DROP POLICY IF EXISTS "campania_eventos_read" ON campania_eventos;
CREATE POLICY "campania_eventos_read" ON campania_eventos FOR SELECT USING (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid())
);
DROP POLICY IF EXISTS "campania_eventos_insert" ON campania_eventos;
CREATE POLICY "campania_eventos_insert" ON campania_eventos FOR INSERT WITH CHECK (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid())
);

-- ============ solicitudes_insumo: lectura/alta abierta a autenticados, resolucion solo admin/auditor ============

DROP POLICY IF EXISTS "solicitudes_insumo_admin_auditor" ON solicitudes_insumo;
DROP POLICY IF EXISTS "solicitudes_insumo_read" ON solicitudes_insumo;
CREATE POLICY "solicitudes_insumo_read" ON solicitudes_insumo FOR SELECT USING (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid())
);
DROP POLICY IF EXISTS "solicitudes_insumo_insert" ON solicitudes_insumo;
CREATE POLICY "solicitudes_insumo_insert" ON solicitudes_insumo FOR INSERT WITH CHECK (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid())
);
DROP POLICY IF EXISTS "solicitudes_insumo_admin_auditor_update" ON solicitudes_insumo;
CREATE POLICY "solicitudes_insumo_admin_auditor_update" ON solicitudes_insumo FOR UPDATE USING (
  EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'auditor'))
);

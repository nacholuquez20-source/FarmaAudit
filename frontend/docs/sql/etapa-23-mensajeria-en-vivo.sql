-- Etapa 23: identidad viva del responsable + ventana de mensajeria
-- Por que: gestion.tel_responsable es una foto fija al crear el desvio: si
-- cambia el responsable de la sucursal, el job de recordatorio y los botones
-- de contacto siguen hablandole al telefono viejo (ARQUITECTURA_PANEL_DESVIOS.md
-- §4.4). La resolucion pasa a ser siempre en vivo contra usuarios_whatsapp.

alter table usuarios_whatsapp add column if not exists ultimo_mensaje_entrante_at timestamptz;

-- "El" responsable activo de una sucursal no estaba garantizado unico. Sin
-- esto, una sucursal con dos filas responsable_sucursal activas por error de
-- carga hace que la resolucion en vivo elija una al azar. Verificado contra
-- produccion antes de esta migracion: no hay duplicados hoy.
create unique index if not exists idx_usuarios_whatsapp_responsable_unico
  on usuarios_whatsapp(id_sucursal)
  where rol = 'responsable_sucursal' and activo;

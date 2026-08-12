-- Etapa 26: informes_respuesta — circuito de vuelta auditor <- encargado
-- Por que: el encargado responde un desvio por WhatsApp (router.py ya lo
-- guarda en desvio_eventos), pero el auditor solo se entera si abre el panel.
-- Este job (informes_respuesta.py) agrupa las respuestas por sucursal+auditor,
-- espera 45 min sin actividad nueva, genera un PDF con lo detectado vs. lo
-- respondido y se lo manda por WhatsApp. Esta tabla es el registro de cada
-- corte generado — sin ella no hay forma de saber que ya se informo (para no
-- reenviar lo mismo) ni de diagnosticar un envio fallido (mismo principio que
-- recordatorios_sucursal en etapa-24).

create table if not exists informes_respuesta (
  id uuid primary key default gen_random_uuid(),
  id_sucursal text not null references sucursales(id) on delete cascade,
  auditor_telefono text not null,
  -- Hasta que evento (desvio_eventos.created_at) cubre este informe. El
  -- proximo corte para este mismo (sucursal, auditor) solo mira eventos
  -- posteriores a este valor.
  corte_at timestamptz not null,
  gestion_ids jsonb not null default '[]'::jsonb,
  estado text not null check (estado in ('enviado', 'sin_ventana', 'fallido', 'sin_auditor')),
  pdf_path text,
  generado_at timestamptz not null default now(),
  enviado_at timestamptz
);

create index if not exists idx_informes_respuesta_grupo
  on informes_respuesta(id_sucursal, auditor_telefono, corte_at desc);

alter table informes_respuesta enable row level security;

-- Igual que audit_fiches (etapa-25): auditor_telefono es un dato personal.
-- A diferencia de recordatorios_sucursal (que no guarda telefonos y es
-- legible por cualquier autenticado), acá se restringe la lectura a
-- admin/auditor — un encargado de sucursal no tiene ningun uso para esta
-- tabla y no deberia poder ver el telefono de un auditor.
create policy "informes_respuesta_admin_auditor_read" on informes_respuesta for select using (
  exists (select 1 from profiles p where p.id = auth.uid() and p.role in ('admin', 'auditor'))
);
-- Sin policy de insert/update para authenticated: el registro lo hace
-- siempre el backend (service role, bypasea RLS), nunca el cliente.

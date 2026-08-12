-- Etapa 25: audit_fiches.auditor_telefono
-- Por que: para avisarle al auditor por WhatsApp cuando el encargado responde
-- un desvio (circuito de vuelta), hace falta un telefono, no solo un nombre
-- libre. audit_fiches.auditor_nombre es texto sin FK — no alcanza para
-- resolver un destinatario de forma confiable.
--
-- Se puebla desde Python al crear la ficha (audit_fiches_manager.py, ya en
-- codigo), nunca por heuristica en las fichas nuevas. Para las fichas
-- historicas se intenta un backfill por nombre exacto contra
-- usuarios_whatsapp — las que no calzan quedan en null a proposito: se ven
-- bien en el panel igual, simplemente no disparan WhatsApp.

alter table audit_fiches add column if not exists auditor_telefono text;

-- audit_fiches_read_policy deja leer TODAS las fichas a cualquier autenticado
-- (incluido el rol 'sucursal' — un encargado). Sin este revoke, el telefono
-- personal del auditor quedaria expuesto a cualquier encargado que abra el
-- panel (el frontend lee con select('*') en varios lugares). El backend usa
-- la service key, que bypasea grants/RLS, asi que sigue pudiendo leer y
-- escribir esta columna sin problema.
revoke select (auditor_telefono) on audit_fiches from authenticated, anon;

-- Backfill best-effort: solo cuando el nombre matchea exactamente un unico
-- auditor activo. Si el nombre es ambiguo (dos auditores con el mismo
-- nombre) o no matchea a nadie, queda null — mejor no enviar que enviarle a
-- la persona equivocada.
with pares as (
  select distinct nombre, telefono
  from usuarios_whatsapp
  where rol = 'auditor' and activo
),
unicos as (
  select nombre, telefono
  from pares
  where nombre in (select nombre from pares group by nombre having count(*) = 1)
)
update audit_fiches af
set auditor_telefono = u.telefono
from unicos u
where af.auditor_telefono is null
  and af.auditor_nombre is not null
  and u.nombre = af.auditor_nombre;

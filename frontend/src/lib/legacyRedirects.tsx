import { Navigate, useSearchParams } from 'react-router-dom';

// Redirects de rutas viejas hacia los módulos consolidados (ver plan de
// consolidación de navegación: 7 módulos -> 4). No son <Navigate to="..."/>
// estáticos porque hay deep-links reales que dependen de sus query params
// (DesvioInfoCard.tsx, SucursalDetail.tsx) — perderlos rompería esos links
// en silencio.

// /auditorias -> /sucursales?tab=fichas, preservando `ficha` (abre el modal
// de una ficha puntual) y `sucursal_id` (preselecciona el filtro).
export function RedirectAuditoriasToSucursales() {
  const [params] = useSearchParams();
  const forwarded = new URLSearchParams();
  const ficha = params.get('ficha');
  const sucursalId = params.get('sucursal_id');
  if (ficha) forwarded.set('ficha', ficha);
  if (sucursalId) forwarded.set('sucursal_id', sucursalId);
  forwarded.set('tab', 'fichas');
  return <Navigate to={`/sucursales?${forwarded.toString()}`} replace />;
}

// /desvios -> /hoy?s=pendientes, preservando `v` (bandeja activa). El `v`
// se reenvía tal cual sin resolver acá los alias legacy (?v=revision /
// ?v=gestion) -- DesviosBandejaPanel ya sabe mapearlos, no hace falta
// duplicar esa tabla en dos lugares.
export function RedirectDesviosToHoy() {
  const [params] = useSearchParams();
  const forwarded = new URLSearchParams();
  forwarded.set('s', 'pendientes');
  const v = params.get('v');
  if (v) forwarded.set('v', v);
  return <Navigate to={`/hoy?${forwarded.toString()}`} replace />;
}

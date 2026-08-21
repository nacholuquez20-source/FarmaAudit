import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Sun } from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { PrioridadBuckets } from '../components/hoy/PrioridadBuckets';
import { SucursalesGrid } from '../components/hoy/SucursalesGrid';
import { DesviosBandejaPanel } from '../components/hoy/DesviosBandejaPanel';
import { useSucursalesPrioridad } from '../hooks/useSucursalesPrioridad';
import { useMountedTabs } from '../hooks/useMountedTabs';
import type { SucursalDashboard } from '../types';

type HoyTab = 'sucursales' | 'pendientes';

function isHoyTab(value: string | null): value is HoyTab {
  return value === 'sucursales' || value === 'pendientes';
}

function saludo(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Buenos días';
  if (h < 19) return 'Buenas tardes';
  return 'Buenas noches';
}

function fechaLarga(): string {
  const s = new Date().toLocaleDateString('es-AR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function contarPorSalud(rows: SucursalDashboard[]): Record<SucursalDashboard['estado_salud'], number> {
  return rows.reduce(
    (acc, s) => {
      acc[s.estado_salud] += 1;
      return acc;
    },
    { critica: 0, atencion: 0, ok: 0, sin_datos: 0 } as Record<SucursalDashboard['estado_salud'], number>,
  );
}

// Módulo "Hoy" — el de mayor uso diario. Fusiona los buckets de prioridad +
// el grid filtrable de sucursales (pestaña "sucursales", default) con la
// bandeja de desvíos por turno (pestaña "pendientes"). Un solo
// useSucursalesPrioridad() alimenta buckets y grid para no duplicar el
// fetch de getSucursalesDashboard() que antes pedían por separado.
export default function Hoy() {
  const [params, setParams] = useSearchParams();
  const sParam = params.get('s');
  const activeTab: HoyTab = isHoyTab(sParam) ? sParam : 'sucursales';
  const { isMounted, markVisited } = useMountedTabs(activeTab);

  // Solo admin/auditor llegan a /hoy (ProtectedRoute allowRoles), asi que el
  // estado de contacto (RLS admin-only) siempre se puede pedir.
  const { rows, enRevision, contacto, contactoLoaded, loading, error, recargarContacto } =
    useSucursalesPrioridad(true);

  const conteos = useMemo(() => contarPorSalud(rows), [rows]);

  const setTab = (tab: HoyTab) => {
    markVisited(tab);
    setParams({ s: tab }, { replace: true });
  };

  return (
    <AppLayout title="Hoy" contentClassName="max-w-none px-0 py-0">
      <div className="border-b border-slate-200 bg-white px-5 lg:px-8">
        <div className="flex gap-0 overflow-x-auto">
          {([
            { key: 'sucursales' as const, label: 'Sucursales' },
            { key: 'pendientes' as const, label: 'Mis pendientes' },
          ]).map((tab) => {
            const active = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setTab(tab.key)}
                className={`flex shrink-0 items-center gap-2 border-b-2 px-5 py-4 text-sm font-semibold transition ${
                  active
                    ? 'border-primary-navy text-primary-navy'
                    : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ display: activeTab === 'sucursales' ? 'block' : 'none' }}>
        {isMounted('sucursales') && (
          <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            {/* Saludo + fecha */}
            <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="flex items-center gap-2 text-lg font-semibold text-gray-900">
                  <Sun className="h-5 w-5 text-primary-orange" />
                  {saludo()}
                </p>
                <p className="text-sm text-gray-500">{fechaLarga()}</p>
              </div>
              {!loading && (
                <div className="flex flex-wrap gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1 text-sm">
                    <span className="h-2.5 w-2.5 rounded-full bg-red-500" /> {conteos.critica} críticas
                  </span>
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1 text-sm">
                    <span className="h-2.5 w-2.5 rounded-full bg-amber-500" /> {conteos.atencion} atención
                  </span>
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1 text-sm">
                    <span className="h-2.5 w-2.5 rounded-full bg-green-500" /> {conteos.ok} al día
                  </span>
                  {conteos.sin_datos > 0 && (
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1 text-sm text-gray-500">
                      <span className="h-2.5 w-2.5 rounded-full bg-gray-300" /> {conteos.sin_datos} sin datos
                    </span>
                  )}
                </div>
              )}
            </div>

            <PrioridadBuckets rows={rows} enRevision={enRevision} loading={loading} error={error} />

            <SucursalesGrid
              data={rows}
              loading={loading}
              contacto={contacto}
              contactoLoaded={contactoLoaded}
              onReminderSent={recargarContacto}
            />
          </div>
        )}
      </div>

      <div style={{ display: activeTab === 'pendientes' ? 'block' : 'none' }}>
        {isMounted('pendientes') && <DesviosBandejaPanel />}
      </div>
    </AppLayout>
  );
}

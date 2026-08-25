import { useEffect, useState } from 'react';
import { Navigate, useNavigate, useSearchParams, Link } from 'react-router-dom';
import { ClipboardCheck } from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { KPICard } from '../components/KPICard';
import { AuditoriasDesviosTable } from '../components/hoy/AuditoriasDesviosTable';
import { useAuth } from '../hooks/useAuth';
import { useDashboardStats } from '../hooks/useDashboardStats';
import { getFichaById } from '../lib/api';

function formatTime(date: Date | null): string {
  if (!date) return '—';
  return date.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });
}

const PERIOD_OPTIONS: { value: string; days: number | null; label: string }[] = [
  { value: '7', days: 7, label: 'Últimos 7 días' },
  { value: '14', days: 14, label: 'Últimos 14 días' },
  { value: '30', days: 30, label: 'Últimos 30 días' },
  { value: 'all', days: null, label: 'Todo el histórico' },
];

function periodSuffix(days: number | null): string {
  return days ? `${days}d` : 'histórico';
}

// Módulo "Sucursales": un solo panel (KPIs + tabla de Auditorías), sin
// pestañas — reemplaza la vieja Analítica (semáforo + ranking crítico) y la
// galería de fichas de perfumería, que se solapaban en contenido. La vista
// por zona/mapa sigue viva en /dashboard (Dashboard.tsx, sin tocar) para
// auditor/sucursal — no se duplica acá.
export default function SucursalesModule() {
  const { role, profile } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [refreshSeconds, setRefreshSeconds] = useState(0);
  const [periodValue, setPeriodValue] = useState('14');
  const periodDays = PERIOD_OPTIONS.find((option) => option.value === periodValue)?.days ?? 14;
  const { stats, loading, refreshing, error, lastUpdated, refresh } = useDashboardStats(refreshSeconds * 1000, null, periodDays);

  // Deep-link legacy desde DesvioInfoCard/legacyRedirects: ?ficha=X abría un
  // modal en la vieja galería. Ahora se resuelve la sucursal de la ficha y se
  // navega directo al detalle real de esa auditoría.
  useEffect(() => {
    const fichaId = params.get('ficha');
    if (!fichaId) return;
    let cancelled = false;
    getFichaById(fichaId)
      .then((ficha) => {
        if (!cancelled && ficha) navigate(`/sucursales/${ficha.sucursal_id}/auditorias/${ficha.id}`, { replace: true });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [params, navigate]);

  // Un encargado de sucursal tiene el módulo habilitado (para poder entrar a
  // su propia ficha desde /sucursales/:id), pero esta vista cruza datos de
  // todas las sucursales — no es para ese rol. El nav ya lo manda directo a
  // su sucursal; esto cubre el caso de un link viejo o tipeado a mano.
  if (role === 'sucursal') {
    if (!profile?.id_sucursal) {
      return (
        <AppLayout title="Sucursales">
          <FeedbackState
            title="No hay sucursal asignada a tu usuario."
            description="Pedí al administrador que cargue tu sucursal en Administración."
            tone="error"
          />
        </AppLayout>
      );
    }
    return <Navigate to={`/sucursales/${profile.id_sucursal}`} replace />;
  }

  const sucursalIdParam = params.get('sucursal_id') ?? undefined;

  return (
    <AppLayout title="Sucursales">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm text-gray-600">Última actualización: {formatTime(lastUpdated)}</p>
          {refreshing && <p className="text-sm text-blue-600">Actualizando datos...</p>}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm font-medium text-gray-700">
            Período
            <select
              value={periodValue}
              onChange={(event) => setPeriodValue(event.target.value)}
              className="ml-2 rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
            >
              {PERIOD_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-medium text-gray-700">
            Auto-refresh
            <select
              value={refreshSeconds}
              onChange={(event) => setRefreshSeconds(Number(event.target.value))}
              className="ml-2 rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
            >
              <option value={0}>Off</option>
              <option value={20}>20s</option>
              <option value={30}>30s</option>
            </select>
          </label>
          <button
            type="button"
            onClick={refresh}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
          >
            Refrescar
          </button>
        </div>
      </div>

      {error && <div className="mb-6"><FeedbackState title={error} tone="error" /></div>}

      <Link
        to="/hoy?s=pendientes&v=decidir"
        className="mb-6 flex items-center gap-4 rounded-xl border border-primary-navy/20 bg-primary-navy/5 px-5 py-4 transition hover:bg-primary-navy/10"
      >
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-navy text-white">
          <ClipboardCheck className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-primary-navy">Revisar borradores</div>
          <div className="text-xs text-slate-500">Aprobar o descartar desvios detectados por el bot de WhatsApp</div>
        </div>
        <span className="text-xs font-medium text-primary-navy">Ver →</span>
      </Link>

      {loading ? (
        <FeedbackState title="Cargando..." tone="loading" />
      ) : (
        stats && (
          <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
            <KPICard title={`Desvíos nuevos (${periodSuffix(periodDays)})`} value={stats.total_desvios} color="blue" />
            <KPICard title="Gestión abierta/en curso" value={stats.gestiones_abiertas} color="yellow" />
            <KPICard title="Vencidos (todos)" value={stats.gestiones_vencidas} color="red" />
            <KPICard title="Críticos altas activos" value={stats.criticos_activos} color="red" />
            <KPICard title="Críticos altas vencidos" value={stats.criticos_vencidos} color="red" />
            <KPICard title={`Resueltos (${periodSuffix(periodDays)})`} value={stats.gestiones_resueltas} color="green" />
            <KPICard title={`Cerrados (${periodSuffix(periodDays)})`} value={stats.gestiones_cerradas} color="green" />
            <KPICard title={`Tasa cierre (${periodSuffix(periodDays)})`} value={`${stats.tasa_cierre.toFixed(1)}%`} color="blue" />
          </div>
        )
      )}

      <AuditoriasDesviosTable initialSucursalId={sucursalIdParam} />
    </AppLayout>
  );
}

import { useEffect, useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { CalendarDays, ClipboardCheck } from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { KPICard } from '../components/KPICard';
import { useDashboardStats } from '../hooks/useDashboardStats';
import { useAuth } from '../hooks/useAuth';
import { supabase } from '../lib/supabase';
import type { DashboardView, SucursalSupervision } from '../types';

interface AuditKPIs {
  hoy: number;
  semana: number;
  puntajePromedio: number | null;
  ultimas: Array<{
    id: string;
    sucursal_id: string;
    sucursal_nombre: string;
    auditor_nombre: string | null;
    fecha_auditoria: string | null;
    puntuacion_promedio: number | null;
    desvios_count: number;
  }>;
}

function useAuditKPIs(scopedSucursal: string | null) {
  const [kpis, setKpis] = useState<AuditKPIs | null>(null);

  useEffect(() => {
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    const weekStart = new Date(todayStart);
    weekStart.setDate(todayStart.getDate() - todayStart.getDay());

    async function load() {
      try {
        // Load sucursales name map and audit fiches in parallel
        const [sucursalesRes, fichesRes] = await Promise.all([
          supabase.from('sucursales').select('id, nombre'),
          (() => {
            let q = supabase.from('audit_fiches').select('id, sucursal_id, auditor_nombre, fecha_auditoria, puntuacion_promedio, desvios_count');
            if (scopedSucursal) q = q.eq('sucursal_id', scopedSucursal);
            return q.order('fecha_auditoria', { ascending: false }).limit(200);
          })(),
        ]);

        const nombreMap = new Map<string, string>(
          (sucursalesRes.data ?? []).map((s: { id: string; nombre: string }) => [s.id, s.nombre])
        );

        const data = fichesRes.data;
        if (!data) return;

        const hoy = data.filter((f) => f.fecha_auditoria && new Date(f.fecha_auditoria) >= todayStart).length;
        const semana = data.filter((f) => f.fecha_auditoria && new Date(f.fecha_auditoria) >= weekStart).length;
        const withScore = data.filter((f) => f.puntuacion_promedio != null);
        const puntajePromedio = withScore.length
          ? withScore.reduce((s, f) => s + (f.puntuacion_promedio as number), 0) / withScore.length
          : null;

        const ultimas = data.slice(0, 5).map((f) => ({
          ...f,
          sucursal_nombre: nombreMap.get(f.sucursal_id) ?? f.sucursal_id,
        }));

        setKpis({ hoy, semana, puntajePromedio, ultimas });
      } catch {
        // non-critical
      }
    }
    void load();
  }, [scopedSucursal]);

  return kpis;
}
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

const COLORS = ['#2563eb', '#059669', '#f59e0b', '#dc2626', '#7c3aed'];

function getSemaforoStyles(semaforo: SucursalSupervision['semaforo']): string {
  if (semaforo === 'rojo') return 'bg-red-100 text-red-800 border-red-200';
  if (semaforo === 'amarillo') return 'bg-yellow-100 text-yellow-800 border-yellow-200';
  return 'bg-green-100 text-green-800 border-green-200';
}

function getSemaforoLabel(semaforo: SucursalSupervision['semaforo']): string {
  if (semaforo === 'rojo') return 'Rojo';
  if (semaforo === 'amarillo') return 'Amarillo';
  return 'Verde';
}

function formatTime(date: Date | null): string {
  if (!date) return 'Sin actualizar';
  return date.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

const ZONES_PER_PAGE = 10;

// Contenido de la analítica de calidad — se usa en dos lugares: el propio
// /dashboard (rol sucursal) y la pestaña "Analítica" de /sucursales (rol
// admin/auditor, ver SucursalesModule.tsx). Sin <AppLayout> propio: cada
// caller decide el envoltorio.
export function DashboardPanel() {
  const [refreshSeconds, setRefreshSeconds] = useState(0);
  const [vista, setVista] = useState<DashboardView>('general');
  const [zonePageIndex, setZonePageIndex] = useState(0);
  const { role, profile } = useAuth();
  const scopedSucursal = role === 'sucursal' ? profile?.id_sucursal ?? null : null;
  const { stats, loading, refreshing, error, lastUpdated, refresh } = useDashboardStats(
    refreshSeconds * 1000,
    scopedSucursal,
  );
  const mostrarVistaZona = role === 'admin' || role === 'auditor';
  const auditKpis = useAuditKPIs(scopedSucursal);

  const gestionStateData = stats
    ? [
        { name: 'Abierta', value: stats.gestiones_abiertas },
        { name: 'Resuelta', value: stats.gestiones_resueltas },
        { name: 'Cerrada', value: stats.gestiones_cerradas },
        { name: 'Vencida', value: stats.gestiones_vencidas },
      ].filter((item) => item.value > 0)
    : [];

  const severidadData = stats
    ? [
        { name: 'Alta', count: stats.severidad.alta },
        { name: 'Media', count: stats.severidad.media },
        { name: 'Baja', count: stats.severidad.baja },
      ]
    : [];

  if (loading) {
    return <FeedbackState title="Cargando supervision..." tone="loading" />;
  }

  if (role === 'sucursal' && !scopedSucursal) {
    return (
      <FeedbackState
        title="No hay sucursal asignada a tu usuario."
        description="Pedí al administrador que cargue tu sucursal y rol Responsable en la sección Administración."
        tone="error"
      />
    );
  }

  return (
    <>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm text-gray-600">Ultima actualizacion: {formatTime(lastUpdated)}</p>
          {refreshing && <p className="text-sm text-blue-600">Actualizando datos...</p>}
        </div>
        <div className="flex flex-wrap items-center gap-3">
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

      {(role === 'admin' || role === 'auditor') && (
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
      )}

      {stats && (
        <>
          {mostrarVistaZona && (
            <div className="mb-6 inline-flex rounded-lg border border-gray-200 bg-white p-1 shadow-sm">
              <button
                type="button"
                onClick={() => {
                  setVista('general');
                  setZonePageIndex(0);
                }}
                className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
                  vista === 'general' ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                Vista general
              </button>
              <button
                type="button"
                onClick={() => {
                  setVista('zona');
                  setZonePageIndex(0);
                }}
                className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
                  vista === 'zona' ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                Por zona
              </button>
            </div>
          )}

          <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
            <KPICard title="Total desvíos" value={stats.total_desvios} color="blue" />
            <KPICard title="Gestión abierta/en curso" value={stats.gestiones_abiertas} color="yellow" />
            <KPICard title="Vencidos (todos)" value={stats.gestiones_vencidas} color="red" />
            <KPICard title="Críticos altas activos" value={stats.criticos_activos} color="red" />
            <KPICard title="Críticos altas vencidos" value={stats.criticos_vencidos} color="red" />
            <KPICard title="Resueltos" value={stats.gestiones_resueltas} color="green" />
            <KPICard title="Cerrados" value={stats.gestiones_cerradas} color="green" />
            <KPICard title="Tasa cierre" value={`${stats.tasa_cierre.toFixed(1)}%`} color="blue" />
          </div>

          {vista === 'zona' && mostrarVistaZona && (
            <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <section className="rounded-lg bg-white p-6 shadow">
                <h2 className="mb-4 text-lg font-semibold">Desempeño por zona</h2>
                {stats.por_zona.length === 0 ? (
                  <FeedbackState title="Sin datos por zona." />
                ) : (
                  <ResponsiveContainer width="100%" height={320}>
                    <BarChart data={stats.por_zona}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="zona" tick={{ fontSize: 11 }} interval={0} angle={-18} height={64} />
                      <YAxis allowDecimals={false} domain={[0, 100]} />
                      <Tooltip />
                      <Bar dataKey="puntaje_promedio" name="Puntaje prom." fill="#059669" radius={[8, 8, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </section>

              <section className="rounded-lg bg-white p-6 shadow">
                <h2 className="mb-4 text-lg font-semibold">Urgencia por zona</h2>
                {stats.por_zona.length === 0 ? (
                  <FeedbackState title="Sin datos por zona." />
                ) : (
                  <ResponsiveContainer width="100%" height={320}>
                    <BarChart data={stats.por_zona}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="zona" tick={{ fontSize: 11 }} interval={0} angle={-18} height={64} />
                      <YAxis allowDecimals={false} />
                      <Tooltip />
                      <Bar dataKey="criticos_activos" name="Críticos activos" fill="#dc2626" radius={[8, 8, 0, 0]} />
                      <Bar dataKey="vencidos" name="Vencidos" fill="#f59e0b" radius={[8, 8, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </section>

              <section className="rounded-lg bg-white p-6 shadow lg:col-span-2">
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-lg font-semibold">Tabla por zona</h2>
                  <span className="text-xs text-gray-500">
                    Página {zonePageIndex + 1} de {Math.ceil(stats.por_zona.length / ZONES_PER_PAGE) || 1}
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[720px]">
                    <thead className="border-b bg-gray-100">
                      <tr>
                        <th className="px-4 py-3 text-left text-sm font-semibold">Zona</th>
                        <th className="px-4 py-3 text-right text-sm font-semibold">Sucursales</th>
                        <th className="px-4 py-3 text-right text-sm font-semibold">Desvíos</th>
                        <th className="px-4 py-3 text-right text-sm font-semibold">Abiertos</th>
                        <th className="px-4 py-3 text-right text-sm font-semibold">Vencidos</th>
                        <th className="px-4 py-3 text-right text-sm font-semibold">Críticos</th>
                        <th className="px-4 py-3 text-right text-sm font-semibold">Puntaje prom.</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.por_zona
                        .slice(zonePageIndex * ZONES_PER_PAGE, (zonePageIndex + 1) * ZONES_PER_PAGE)
                        .map((row) => (
                          <tr key={row.zona} className="border-b hover:bg-gray-50">
                            <td className="px-4 py-3 text-sm font-medium text-gray-900">{row.zona}</td>
                            <td className="px-4 py-3 text-right text-sm">{row.sucursales}</td>
                            <td className="px-4 py-3 text-right text-sm">{row.total_desvios}</td>
                            <td className="px-4 py-3 text-right text-sm">{row.abiertos}</td>
                            <td className="px-4 py-3 text-right text-sm text-amber-800">{row.vencidos}</td>
                            <td className="px-4 py-3 text-right text-sm font-semibold text-red-700">{row.criticos_activos}</td>
                            <td className="px-4 py-3 text-right text-sm font-semibold text-emerald-700">{row.puntaje_promedio}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                {Math.ceil(stats.por_zona.length / ZONES_PER_PAGE) > 1 && (
                  <div className="mt-4 flex items-center justify-center gap-2">
                    <button
                      type="button"
                      onClick={() => setZonePageIndex(Math.max(0, zonePageIndex - 1))}
                      disabled={zonePageIndex === 0}
                      className="rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      ← Anterior
                    </button>
                    <button
                      type="button"
                      onClick={() => setZonePageIndex(Math.min(Math.ceil(stats.por_zona.length / ZONES_PER_PAGE) - 1, zonePageIndex + 1))}
                      disabled={zonePageIndex >= Math.ceil(stats.por_zona.length / ZONES_PER_PAGE) - 1}
                      className="rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Siguiente →
                    </button>
                  </div>
                )}
              </section>
            </div>
          )}

          {vista === 'general' && (
          <>
          <div className="mb-8 grid grid-cols-1 gap-6 xl:grid-cols-3">
            <section className="rounded-lg bg-white p-6 shadow xl:col-span-2">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold">Semaforo por Sucursal</h2>
                <Link to="/gestion-desvios" className="text-sm font-medium text-blue-600 hover:text-blue-800">
                  Ver gestion
                </Link>
              </div>
              {stats.sucursales_estado.length === 0 ? (
                <FeedbackState title="No hay sucursales con desvios." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[760px]">
                    <thead className="border-b bg-gray-100">
                      <tr>
                        <th className="px-4 py-3 text-left text-sm font-semibold">Sucursal</th>
                        {role === 'admin' && (
                          <th className="px-4 py-3 text-left text-sm font-semibold">Zona</th>
                        )}
                        <th className="px-4 py-3 text-left text-sm font-semibold">Estado</th>
                        <th className="px-4 py-3 text-right text-sm font-semibold">Puntaje</th>
                        <th className="px-4 py-3 text-right text-sm font-semibold">Abiertos</th>
                        <th className="px-4 py-3 text-right text-sm font-semibold">Vencidos</th>
                        <th className="px-4 py-3 text-right text-sm font-semibold">Críticos</th>
                        <th className="px-4 py-3 text-right text-sm font-semibold">Altas (hist.)</th>
                        <th className="px-4 py-3 text-right text-sm font-semibold">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.sucursales_estado.map((sucursal) => (
                        <tr key={sucursal.id_sucursal || sucursal.sucursal} className="border-b hover:bg-gray-50">
                          <td className="px-4 py-4 text-sm font-medium text-gray-900">
                            <Link to={`/sucursales/${sucursal.id_sucursal}`} className="hover:text-blue-700">
                              {sucursal.sucursal}
                            </Link>
                          </td>
                          {role === 'admin' && (
                            <td className="px-4 py-4 text-sm text-gray-600">{sucursal.zona}</td>
                          )}
                          <td className="px-4 py-4 text-sm">
                            <span className={`rounded border px-3 py-1 text-xs font-semibold ${getSemaforoStyles(sucursal.semaforo)}`}>
                              {getSemaforoLabel(sucursal.semaforo)}
                            </span>
                          </td>
                          <td className="px-4 py-4 text-right text-sm font-semibold text-emerald-800">{sucursal.puntaje}</td>
                          <td className="px-4 py-4 text-right text-sm">{sucursal.abiertos}</td>
                          <td className="px-4 py-4 text-right text-sm font-semibold text-red-700">{sucursal.vencidos}</td>
                          <td className="px-4 py-4 text-right text-sm font-semibold text-red-800">{sucursal.criticos_activos}</td>
                          <td className="px-4 py-4 text-right text-sm">{sucursal.altas}</td>
                          <td className="px-4 py-4 text-right text-sm">{sucursal.total}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="rounded-lg bg-white p-6 shadow">
              <h2 className="mb-4 text-lg font-semibold">Ranking Critico</h2>
              {stats.ranking_sucursales.length === 0 ? (
                <FeedbackState title="Sin desvios abiertos." />
              ) : (
                <div className="space-y-3">
                  {stats.ranking_sucursales.map((sucursal, index) => (
                    <Link
                      key={sucursal.id_sucursal || sucursal.sucursal}
                      to={`/sucursales/${sucursal.id_sucursal}`}
                      className="block rounded-lg border border-gray-200 p-4 hover:bg-gray-50"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-xs font-semibold text-gray-500">#{index + 1}</div>
                          <div className="font-semibold text-gray-900">{sucursal.sucursal}</div>
                        </div>
                        <div className="text-right text-sm">
                          <div className="font-semibold text-red-700">{sucursal.criticos_activos} críticos</div>
                          <div className="font-semibold text-red-700">{sucursal.vencidos} vencidos</div>
                          <div className="text-gray-600">{sucursal.abiertos} abiertos</div>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </section>
          </div>

          <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <section className="rounded-lg bg-white p-6 shadow">
              <h2 className="mb-4 text-lg font-semibold">Gestiones por Estado</h2>
              {gestionStateData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie data={gestionStateData} cx="50%" cy="50%" labelLine={false} label={({ name, value }) => `${name}: ${value}`} outerRadius={88} dataKey="value">
                      {gestionStateData.map((_, index) => (
                        <Cell key={`estado-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <FeedbackState title="No hay datos disponibles" />
              )}
            </section>

            <section className="rounded-lg bg-white p-6 shadow">
              <h2 className="mb-4 text-lg font-semibold">Hallazgos por Severidad</h2>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={severidadData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#2563eb" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </section>
          </div>

          <section className="rounded-lg bg-white p-6 shadow">
            <h2 className="mb-4 text-lg font-semibold">Tendencia Ultimos 30 Dias</h2>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={stats.tendencia_ultimos_30_dias}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="fecha" tick={{ fontSize: 12 }} minTickGap={24} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Line type="monotone" dataKey="total" name="Desvios" stroke="#2563eb" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="cerrados" name="Cerrados" stroke="#059669" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </section>

          {auditKpis && role !== 'sucursal' && (
            <section className="mt-8 rounded-lg bg-white p-6 shadow">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-lg font-semibold">
                  <CalendarDays className="h-5 w-5 text-primary-navy" />
                  Auditorías de Perfumería
                </h2>
                <Link to="/sucursales?tab=fichas" className="text-sm font-medium text-blue-600 hover:text-blue-800">
                  Ver todas →
                </Link>
              </div>
              <div className="mb-6 grid grid-cols-3 gap-4">
                <div className="rounded-lg border border-gray-100 bg-gray-50 p-4 text-center">
                  <div className="text-2xl font-bold text-primary-navy">{auditKpis.hoy}</div>
                  <div className="mt-1 text-xs text-gray-500">Hoy</div>
                </div>
                <div className="rounded-lg border border-gray-100 bg-gray-50 p-4 text-center">
                  <div className="text-2xl font-bold text-primary-navy">{auditKpis.semana}</div>
                  <div className="mt-1 text-xs text-gray-500">Esta semana</div>
                </div>
                <div className="rounded-lg border border-gray-100 bg-gray-50 p-4 text-center">
                  <div className={`text-2xl font-bold ${auditKpis.puntajePromedio != null && auditKpis.puntajePromedio >= 4 ? 'text-green-600' : auditKpis.puntajePromedio != null && auditKpis.puntajePromedio >= 3 ? 'text-yellow-600' : 'text-gray-400'}`}>
                    {auditKpis.puntajePromedio != null ? `${auditKpis.puntajePromedio.toFixed(1)}/5` : '—'}
                  </div>
                  <div className="mt-1 text-xs text-gray-500">Puntaje promedio</div>
                </div>
              </div>
              {auditKpis.ultimas.length === 0 ? (
                <p className="text-sm text-gray-500">No hay auditorías registradas todavía.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="border-b bg-gray-50">
                      <tr>
                        <th className="px-3 py-2 text-left font-semibold text-gray-600">Sucursal</th>
                        <th className="px-3 py-2 text-left font-semibold text-gray-600">Auditor</th>
                        <th className="px-3 py-2 text-left font-semibold text-gray-600">Fecha</th>
                        <th className="px-3 py-2 text-center font-semibold text-gray-600">Puntaje</th>
                        <th className="px-3 py-2 text-center font-semibold text-gray-600">Desvíos</th>
                      </tr>
                    </thead>
                    <tbody>
                      {auditKpis.ultimas.map((f) => (
                        <tr key={f.id} className="border-b hover:bg-gray-50">
                          <td className="px-3 py-3">
                            <Link to={`/sucursales/${f.sucursal_id}`} className="font-medium text-gray-900 hover:text-blue-700">
                              {f.sucursal_nombre}
                            </Link>
                          </td>
                          <td className="px-3 py-3 text-gray-600">{f.auditor_nombre || '—'}</td>
                          <td className="px-3 py-3 text-gray-500">
                            {f.fecha_auditoria
                              ? new Date(f.fecha_auditoria).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
                              : '—'}
                          </td>
                          <td className="px-3 py-3 text-center">
                            {f.puntuacion_promedio != null ? (
                              <span className={`rounded-full px-2 py-0.5 text-xs font-bold text-white ${f.puntuacion_promedio >= 4 ? 'bg-green-600' : f.puntuacion_promedio >= 3 ? 'bg-yellow-500' : 'bg-red-600'}`}>
                                {f.puntuacion_promedio.toFixed(1)}
                              </span>
                            ) : '—'}
                          </td>
                          <td className="px-3 py-3 text-center">
                            <span className={f.desvios_count > 0 ? 'font-semibold text-red-600' : 'text-green-600'}>
                              {f.desvios_count}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
          </>
          )}
        </>
      )}
    </>
  );
}

// Wrapper de página completa — hoy solo lo usa la ruta /dashboard, que a su
// vez solo es alcanzable para el rol sucursal (el admin fue absorbido por
// /sucursales, ver App.tsx). El redirect es por si queda algun bookmark
// viejo apuntando a /dashboard como admin.
export default function Dashboard() {
  const { role } = useAuth();
  if (role === 'admin') return <Navigate to="/sucursales" replace />;

  return (
    <AppLayout title={role === 'sucursal' ? 'Resumen de mi sucursal' : 'Dashboard de calidad'}>
      <DashboardPanel />
    </AppLayout>
  );
}

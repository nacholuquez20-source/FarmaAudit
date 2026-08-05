import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  Calendar,
  Check,
  CircleDot,
  ClipboardCheck,
  Minus,
  MessageCircle,
  Pencil,
  Search,
  SprayCan,
  Star,
  Triangle,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { getSucursalesDashboard } from '../lib/api';
import { whatsappLink } from '../lib/utils';
import { useAuth } from '../hooks/useAuth';
import type { EstadoSalud, SucursalDashboard } from '../types';

type Filtro = 'todas' | 'critica' | 'atencion' | 'ok' | 'sin_datos' | 'perfumeria';

// Orden por urgencia: las críticas primero, "sin datos" al final (no arde).
const RANK: Record<EstadoSalud, number> = { critica: 0, atencion: 1, ok: 2, sin_datos: 3 };

// El estado se comunica por COLOR + FORMA (ícono), no solo color, para que sea
// legible con daltonismo. El borde izquierdo es el ancla visual de la tarjeta.
const SALUD_META: Record<EstadoSalud, { dot: string; border: string; icon: LucideIcon; label: string }> = {
  critica:   { dot: 'bg-red-500',   border: 'border-l-red-500',   icon: Triangle,   label: 'Crítica' },
  atencion:  { dot: 'bg-amber-500', border: 'border-l-amber-500', icon: CircleDot,  label: 'Atención' },
  ok:        { dot: 'bg-green-500', border: 'border-l-green-500', icon: Check,      label: 'Al día' },
  sin_datos: { dot: 'bg-gray-300',  border: 'border-l-gray-300',  icon: Minus,      label: 'Sin datos' },
};

function scoreClasses(score: number | null): string {
  if (score === null) return 'text-gray-400';
  if (score >= 4) return 'text-green-600';
  if (score >= 3) return 'text-amber-500';
  return 'text-red-600';
}

function diasLabel(dias: number | null): string {
  if (dias === null) return 'Sin auditar';
  if (dias === 0) return 'Hoy';
  if (dias === 1) return 'Hace 1 día';
  return `Hace ${dias} días`;
}

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div className="h-4 w-28 rounded bg-gray-200" />
        <div className="h-3 w-3 rounded-full bg-gray-200" />
      </div>
      <div className="mb-4 h-3 w-20 rounded bg-gray-200" />
      <div className="space-y-2">
        <div className="h-3 w-24 rounded bg-gray-200" />
        <div className="h-3 w-32 rounded bg-gray-200" />
        <div className="h-3 w-16 rounded bg-gray-200" />
      </div>
      <div className="mt-4 h-3 w-24 rounded bg-gray-200" />
    </div>
  );
}

export default function SucursalesDashboard() {
  const { role, profile } = useAuth();
  const navigate = useNavigate();

  const [data, setData] = useState<SucursalDashboard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [filtro, setFiltro] = useState<Filtro>('todas');

  const canAudit = role === 'admin' || role === 'auditor';

  useEffect(() => {
    let active = true;
    getSucursalesDashboard()
      .then((rows) => {
        if (active) setData(rows);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'No se pudieron cargar las sucursales.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  // La 'sucursal' rara vez cae acá (ve "Mi sucursal"), pero por las dudas la
  // acotamos a su propia sucursal.
  const scoped = useMemo(() => {
    if (role === 'sucursal' && profile?.id_sucursal) {
      return data.filter((s) => s.id === profile.id_sucursal);
    }
    return data;
  }, [data, role, profile?.id_sucursal]);

  const conteos = useMemo(() => {
    return scoped.reduce(
      (acc, s) => {
        acc[s.estado_salud] += 1;
        return acc;
      },
      { critica: 0, atencion: 0, ok: 0, sin_datos: 0 } as Record<EstadoSalud, number>,
    );
  }, [scoped]);

  const visibles = useMemo(() => {
    const q = search.trim().toLowerCase();
    return scoped
      .filter((s) => {
        if (filtro === 'perfumeria') return s.tiene_perfumeria;
        if (filtro !== 'todas') return s.estado_salud === filtro;
        return true;
      })
      .filter((s) => {
        if (!q) return true;
        return [s.nombre, s.zona, s.responsable, s.id].join(' ').toLowerCase().includes(q);
      })
      .sort((a, b) => {
        const r = RANK[a.estado_salud] - RANK[b.estado_salud];
        if (r !== 0) return r;
        // Dentro del mismo estado, más vencidos primero, luego más viejas.
        if (b.desvios_vencidos !== a.desvios_vencidos) return b.desvios_vencidos - a.desvios_vencidos;
        return (b.dias_desde_auditoria ?? 9999) - (a.dias_desde_auditoria ?? 9999);
      });
  }, [scoped, filtro, search]);

  const filtros: { key: Filtro; label: string; count?: number; dot?: string }[] = [
    { key: 'todas', label: 'Todas', count: scoped.length },
    { key: 'critica', label: 'Críticas', count: conteos.critica, dot: 'bg-red-500' },
    { key: 'atencion', label: 'Atención', count: conteos.atencion, dot: 'bg-amber-500' },
    { key: 'ok', label: 'Al día', count: conteos.ok, dot: 'bg-green-500' },
    { key: 'sin_datos', label: 'Sin datos', count: conteos.sin_datos, dot: 'bg-gray-300' },
    { key: 'perfumeria', label: '🧴 Perfumería' },
  ];

  return (
    <AppLayout title={role === 'sucursal' ? 'Mi sucursal' : 'Sucursales'}>
      {/* Barra de control + búsqueda */}
      <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="relative w-full lg:max-w-md">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            type="search"
            placeholder="Buscar sucursal, zona o encargado…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm focus:border-transparent focus:ring-2 focus:ring-primary-navy"
          />
        </div>
        {role === 'admin' && (
          <button
            type="button"
            onClick={() => navigate('/sucursales/editar')}
            className="inline-flex items-center gap-1.5 self-start rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-100"
          >
            <Pencil className="h-3.5 w-3.5" />
            Editar datos
          </button>
        )}
      </div>

      {/* Filtros rápidos / tablero de estado */}
      <div className="mb-6 flex flex-wrap gap-2">
        {filtros.map((f) => {
          const activo = filtro === f.key;
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => setFiltro(f.key)}
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium transition ${
                activo
                  ? 'border-primary-navy bg-primary-navy/10 text-primary-navy'
                  : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
              }`}
            >
              {f.dot && <span className={`h-2.5 w-2.5 rounded-full ${f.dot}`} />}
              {f.label}
              {typeof f.count === 'number' && (
                <span className="rounded-full bg-gray-100 px-1.5 text-xs font-semibold text-gray-600">
                  {f.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {error && (
        <div className="mb-4">
          <FeedbackState title={error} tone="error" />
        </div>
      )}

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : visibles.length === 0 ? (
        <FeedbackState
          title={search || filtro !== 'todas' ? 'Sin resultados con este filtro.' : 'No hay sucursales cargadas.'}
          description={search || filtro !== 'todas' ? 'Probá quitar el filtro o la búsqueda.' : undefined}
          tone="info"
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {visibles.map((s) => {
            const meta = SALUD_META[s.estado_salud];
            const Icon = meta.icon;
            const wa = whatsappLink(s.tel_responsable);
            const sinDatos = s.estado_salud === 'sin_datos';
            return (
              <div
                key={s.id}
                onClick={() => navigate(`/sucursales/${s.id}`)}
                className={`flex cursor-pointer flex-col rounded-lg border border-l-4 border-gray-200 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${meta.border}`}
              >
                {/* Header: nombre + estado (color + forma + label) */}
                <div className="mb-1 flex items-start justify-between gap-2">
                  <h3 className="font-semibold leading-tight text-gray-900">{s.nombre}</h3>
                  <span
                    className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-white ${meta.dot}`}
                    title={meta.label}
                    aria-label={meta.label}
                  >
                    <Icon className="h-3 w-3" strokeWidth={3} />
                  </span>
                </div>
                {(s.zona || s.tiene_perfumeria) && (
                  <div className="mb-3 flex items-center gap-2 text-xs text-gray-500">
                    {s.zona && <span>{s.zona}</span>}
                    {s.tiene_perfumeria && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-primary-orange/10 px-1.5 py-0.5 font-medium text-primary-orange">
                        <SprayCan className="h-3 w-3" />
                        Perfumería
                      </span>
                    )}
                  </div>
                )}

                {/* Métricas — para "sin datos" se colapsa a una línea muteada */}
                {sinDatos ? (
                  <div className="flex items-center gap-2 text-sm text-gray-400">
                    <Calendar className="h-4 w-4" />
                    Sin auditorías todavía
                  </div>
                ) : (
                  <div className="space-y-1.5 text-sm">
                    <div className="flex items-center gap-2">
                      {s.desvios_abiertos > 0 ? (
                        <>
                          <AlertTriangle className="h-4 w-4 text-red-500" />
                          <span className="text-gray-700">
                            {s.desvios_abiertos} desvío{s.desvios_abiertos === 1 ? '' : 's'}
                            {s.desvios_vencidos > 0 && (
                              <span className="font-semibold text-red-600"> · {s.desvios_vencidos} vencido{s.desvios_vencidos === 1 ? '' : 's'}</span>
                            )}
                          </span>
                        </>
                      ) : (
                        <>
                          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-green-100 text-[10px] font-bold text-green-700">✓</span>
                          <span className="text-gray-500">Sin desvíos</span>
                        </>
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-gray-600">
                      <Calendar className="h-4 w-4 text-gray-400" />
                      {diasLabel(s.dias_desde_auditoria)}
                    </div>
                    {s.ultimo_score != null && (
                      <div className="flex items-center gap-2">
                        <Star className={`h-4 w-4 ${scoreClasses(s.ultimo_score)}`} />
                        <span className={`font-semibold ${scoreClasses(s.ultimo_score)}`}>
                          {`${Number(s.ultimo_score).toFixed(1)}/5`}
                        </span>
                      </div>
                    )}
                  </div>
                )}

                {/* Footer: encargado + acciones */}
                <div className="mt-4 flex items-center justify-between border-t border-gray-100 pt-3">
                  <span className={`truncate text-xs ${s.responsable ? 'text-gray-500' : 'text-gray-300'}`} title={s.responsable || ''}>
                    👤 {s.responsable || 'Sin encargado'}
                  </span>
                  <div className="flex items-center gap-1">
                    {wa && (
                      <a
                        href={wa}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="rounded-md p-1.5 text-green-600 transition hover:bg-green-50"
                        title="Contactar por WhatsApp"
                      >
                        <MessageCircle className="h-4 w-4" />
                      </a>
                    )}
                    {canAudit && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/sucursales/${s.id}/auditoria`);
                        }}
                        className="rounded-md p-1.5 text-primary-navy transition hover:bg-primary-navy/10"
                        title="Iniciar auditoría"
                      >
                        <ClipboardCheck className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </AppLayout>
  );
}

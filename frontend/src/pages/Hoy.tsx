import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  Calendar,
  CheckCircle2,
  Eye,
  Sparkles,
  SprayCan,
  Sun,
} from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { getSucursalesDashboard } from '../lib/api';
import { esMesActual } from '../lib/utils';
import { supabase } from '../lib/supabase';
import type { SucursalDashboard } from '../types';

interface Item {
  id: string;
  nombre: string;
  zona: string | null;
  detalle: string;
}

interface Seccion {
  key: string;
  titulo: string;
  icon: typeof AlertTriangle;
  tone: string; // clases del bloque de icono
  items: Item[];
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

export default function Hoy() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<SucursalDashboard[]>([]);
  const [enRevision, setEnRevision] = useState<Map<string, number>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      getSucursalesDashboard(),
      supabase.from('gestion').select('id_sucursal').eq('estado', 'En_revision'),
    ])
      .then(([dashboard, revisionRes]) => {
        if (!active) return;
        setRows(dashboard);
        const map = new Map<string, number>();
        for (const g of revisionRes.data ?? []) {
          const key = (g as { id_sucursal: string }).id_sucursal;
          map.set(key, (map.get(key) ?? 0) + 1);
        }
        setEnRevision(map);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'No se pudo cargar el panel.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const conteos = useMemo(
    () =>
      rows.reduce(
        (acc, s) => {
          acc[s.estado_salud] += 1;
          return acc;
        },
        { critica: 0, atencion: 0, ok: 0 } as Record<SucursalDashboard['estado_salud'], number>,
      ),
    [rows],
  );

  // Cada sucursal aparece una sola vez, en su bucket más urgente.
  const secciones = useMemo<Seccion[]>(() => {
    const seen = new Set<string>();
    const take = (predicate: (s: SucursalDashboard) => boolean, detalle: (s: SucursalDashboard) => string): Item[] => {
      const out: Item[] = [];
      for (const s of rows) {
        if (seen.has(s.id) || !predicate(s)) continue;
        seen.add(s.id);
        out.push({ id: s.id, nombre: s.nombre, zona: s.zona, detalle: detalle(s) });
      }
      return out;
    };

    const vencidos = take(
      (s) => s.desvios_vencidos > 0,
      (s) => `${s.desvios_vencidos} desvío${s.desvios_vencidos === 1 ? '' : 's'} vencido${s.desvios_vencidos === 1 ? '' : 's'}`,
    ).sort((a, b) => a.nombre.localeCompare(b.nombre));

    const revision = take(
      (s) => (enRevision.get(s.id) ?? 0) > 0,
      (s) => `${enRevision.get(s.id)} esperando revisión`,
    );

    const sinAuditar = take(
      (s) => s.dias_desde_auditoria === null || s.dias_desde_auditoria > 30,
      (s) => (s.dias_desde_auditoria === null ? 'Nunca auditada' : `Hace ${s.dias_desde_auditoria} días`),
    );

    const perfumeria = take(
      (s) => s.tiene_perfumeria && !esMesActual(s.ultima_auditoria),
      () => 'Perfumería sin auditar este mes',
    );

    return [
      { key: 'vencidos', titulo: 'Desvíos vencidos', icon: AlertTriangle, tone: 'bg-red-100 text-red-600', items: vencidos },
      { key: 'revision', titulo: 'Esperando tu revisión', icon: Eye, tone: 'bg-amber-100 text-amber-600', items: revision },
      { key: 'sinAuditar', titulo: 'Sin auditar hace +30 días', icon: Calendar, tone: 'bg-blue-100 text-blue-600', items: sinAuditar },
      { key: 'perfumeria', titulo: 'Perfumerías pendientes este mes', icon: SprayCan, tone: 'bg-primary-orange/10 text-primary-orange', items: perfumeria },
    ].filter((s) => s.items.length > 0);
  }, [rows, enRevision]);

  const totalPendientes = secciones.reduce((n, s) => n + s.items.length, 0);

  return (
    <AppLayout title="Hoy">
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
          <div className="flex gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1 text-sm">
              <span className="h-2.5 w-2.5 rounded-full bg-red-500" /> {conteos.critica} críticas
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1 text-sm">
              <span className="h-2.5 w-2.5 rounded-full bg-amber-500" /> {conteos.atencion} atención
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1 text-sm">
              <span className="h-2.5 w-2.5 rounded-full bg-green-500" /> {conteos.ok} al día
            </span>
          </div>
        )}
      </div>

      {error && (
        <div className="mb-4">
          <FeedbackState title={error} tone="error" />
        </div>
      )}

      {loading ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="animate-pulse rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <div className="mb-3 h-4 w-40 rounded bg-gray-200" />
              <div className="space-y-2">
                <div className="h-10 rounded bg-gray-100" />
                <div className="h-10 rounded bg-gray-100" />
              </div>
            </div>
          ))}
        </div>
      ) : totalPendientes === 0 ? (
        <div className="rounded-lg border border-green-100 bg-green-50 p-8 text-center">
          <Sparkles className="mx-auto mb-3 h-10 w-10 text-green-500" />
          <p className="text-lg font-semibold text-green-800">¡Todo al día! 🎉</p>
          <p className="mt-1 text-sm text-green-700">No hay pendientes urgentes hoy en las sucursales.</p>
          <button
            type="button"
            onClick={() => navigate('/sucursales')}
            className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-primary-navy px-4 py-2 text-sm font-medium text-white transition hover:bg-primary-navy/90"
          >
            Ver todas las sucursales
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <div className="space-y-5">
          {secciones.map((seccion) => (
            <section key={seccion.key} className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
              <div className="flex items-center gap-2 border-b border-gray-100 px-4 py-3">
                <span className={`flex h-7 w-7 items-center justify-center rounded-full ${seccion.tone}`}>
                  <seccion.icon className="h-4 w-4" />
                </span>
                <h2 className="text-sm font-semibold text-gray-900">{seccion.titulo}</h2>
                <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-semibold text-gray-600">
                  {seccion.items.length}
                </span>
              </div>
              <ul className="divide-y divide-gray-50">
                {seccion.items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => navigate(`/sucursales/${item.id}`)}
                      className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-gray-50"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-gray-900">{item.nombre}</span>
                        <span className="block truncate text-xs text-gray-500">{item.zona || 'Sin zona'}</span>
                      </span>
                      <span className="flex shrink-0 items-center gap-2">
                        <span className="text-xs font-medium text-gray-600">{item.detalle}</span>
                        <ArrowRight className="h-4 w-4 text-gray-300" />
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}

          <div className="flex items-center justify-center gap-2 pt-1 text-sm text-gray-400">
            <CheckCircle2 className="h-4 w-4" />
            {totalPendientes} pendiente{totalPendientes === 1 ? '' : 's'} priorizado{totalPendientes === 1 ? '' : 's'}
          </div>
        </div>
      )}
    </AppLayout>
  );
}

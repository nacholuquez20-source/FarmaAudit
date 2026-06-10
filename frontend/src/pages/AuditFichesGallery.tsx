import { useCallback, useEffect, useMemo, useState } from 'react';
import { Calendar, Camera, Download, FileText, FilterX, X } from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { Button } from '../components/Button';
import { FeedbackState } from '../components/FeedbackState';
import { Input } from '../components/Input';
import { Select } from '../components/Select';
import { getSucursales } from '../lib/api';
import { supabase } from '../lib/supabase';
import type { Sucursal } from '../types';

interface Ficha {
  id: string;
  sucursal_id: string;
  auditor_nombre: string | null;
  responsable_desvios: string | null;
  fecha_auditoria: string | null;
  url_pdf: string | null;
  desvios_count: number;
  fotos_count: number;
  puntuacion_promedio: number | null;
}

const PAGE_SIZE = 12;

function scoreBadgeClasses(score: number | null): string {
  if (score === null) return 'bg-gray-400';
  if (score >= 4) return 'bg-green-600';
  if (score >= 3) return 'bg-yellow-500';
  return 'bg-red-600';
}

function formatDate(dateString: string | null): string {
  if (!dateString) return 'Sin fecha';
  return new Date(dateString).toLocaleDateString('es-AR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function AuditFichesGallery() {
  const [fichas, setFichas] = useState<Ficha[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);

  const [sucursalId, setSucursalId] = useState('');
  const [auditor, setAuditor] = useState('');
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');
  const [page, setPage] = useState(0);

  const [selected, setSelected] = useState<Ficha | null>(null);

  const sucursalNombre = useMemo(() => {
    const map = new Map(sucursales.map((s) => [s.id, s.nombre]));
    return (id: string) => map.get(id) || id;
  }, [sucursales]);

  useEffect(() => {
    getSucursales()
      .then(setSucursales)
      .catch(() => setSucursales([]));
  }, []);

  const loadFichas = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let query = supabase
        .from('audit_fiches')
        .select('*', { count: 'exact' })
        .order('fecha_auditoria', { ascending: false })
        .range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1);

      if (sucursalId) query = query.eq('sucursal_id', sucursalId);
      if (auditor.trim()) query = query.ilike('auditor_nombre', `%${auditor.trim()}%`);
      if (fechaDesde) query = query.gte('fecha_auditoria', fechaDesde);
      if (fechaHasta) query = query.lte('fecha_auditoria', `${fechaHasta}T23:59:59`);

      const { data, count, error: queryError } = await query;
      if (queryError) throw queryError;
      setFichas((data as Ficha[]) || []);
      setTotal(count ?? 0);
    } catch (err) {
      console.error('Error loading fichas:', err);
      const code = (err as { code?: string })?.code;
      setError(
        code === 'PGRST205'
          ? 'La tabla audit_fiches no existe en la base de datos. Ejecuta migration_audit_fiches.sql en Supabase.'
          : 'No se pudieron cargar las fichas. Verifica tu conexion e intenta de nuevo.'
      );
      setFichas([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [sucursalId, auditor, fechaDesde, fechaHasta, page]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadFichas(), auditor ? 350 : 0);
    return () => window.clearTimeout(timer);
  }, [loadFichas, auditor]);

  const hasFilters = Boolean(sucursalId || auditor || fechaDesde || fechaHasta);

  const clearFilters = () => {
    setSucursalId('');
    setAuditor('');
    setFechaDesde('');
    setFechaHasta('');
    setPage(0);
  };

  const updateFilter = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value);
    setPage(0);
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <AppLayout title="Fichas de Auditoria">
      {/* Filtros */}
      <div className="mb-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Select
            label="Sucursal"
            value={sucursalId}
            onChange={(e) => updateFilter(setSucursalId)(e.target.value)}
            options={[
              { value: '', label: 'Todas' },
              ...sucursales.map((s) => ({ value: s.id, label: s.nombre })),
            ]}
          />
          <Input
            label="Auditor"
            type="search"
            placeholder="Buscar por nombre..."
            value={auditor}
            onChange={(e) => updateFilter(setAuditor)(e.target.value)}
          />
          <Input
            label="Desde"
            type="date"
            value={fechaDesde}
            onChange={(e) => updateFilter(setFechaDesde)(e.target.value)}
          />
          <Input
            label="Hasta"
            type="date"
            value={fechaHasta}
            onChange={(e) => updateFilter(setFechaHasta)(e.target.value)}
          />
          <div className="flex items-end">
            <Button
              variant="secondary"
              onClick={clearFilters}
              disabled={!hasFilters}
              className="w-full"
            >
              <FilterX className="mr-2 inline h-4 w-4" />
              Limpiar
            </Button>
          </div>
        </div>
      </div>

      {/* Contenido */}
      {loading ? (
        <FeedbackState title="Cargando fichas..." />
      ) : error ? (
        <FeedbackState title="Error al cargar" description={error} tone="error" />
      ) : fichas.length === 0 ? (
        <FeedbackState
          title={hasFilters ? 'Sin resultados con estos filtros.' : 'Todavia no hay fichas de auditoria.'}
          description={
            hasFilters
              ? 'Proba quitando algun filtro.'
              : 'Las fichas se generan automaticamente al completar auditorias por WhatsApp.'
          }
          tone="info"
        />
      ) : (
        <>
          <p className="mb-3 text-sm text-gray-500">
            {total} ficha{total === 1 ? '' : 's'} · pagina {page + 1} de {totalPages}
          </p>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {fichas.map((ficha) => (
              <button
                key={ficha.id}
                type="button"
                onClick={() => setSelected(ficha)}
                className="flex flex-col rounded-lg border border-gray-200 bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-200"
              >
                <div className="mb-3 flex items-center justify-between">
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-bold text-white ${scoreBadgeClasses(ficha.puntuacion_promedio)}`}
                  >
                    {ficha.puntuacion_promedio != null
                      ? `${Number(ficha.puntuacion_promedio).toFixed(1)}/5`
                      : 'Sin puntaje'}
                  </span>
                  <span className="flex items-center gap-1 text-xs text-gray-500">
                    <Calendar className="h-3.5 w-3.5" />
                    {formatDate(ficha.fecha_auditoria)}
                  </span>
                </div>

                <h3 className="mb-1 font-semibold text-gray-900">{sucursalNombre(ficha.sucursal_id)}</h3>
                <p className="text-sm text-gray-600">Auditor: {ficha.auditor_nombre || '-'}</p>
                <p className="mb-3 text-sm text-gray-600">
                  Responsable: {ficha.responsable_desvios || '-'}
                </p>

                <div className="mt-auto flex flex-wrap items-center gap-2">
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${
                      ficha.desvios_count > 0
                        ? 'border-red-200 bg-red-50 text-red-700'
                        : 'border-green-200 bg-green-50 text-green-700'
                    }`}
                  >
                    {ficha.desvios_count} desvio{ficha.desvios_count === 1 ? '' : 's'}
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs font-medium text-gray-600">
                    <Camera className="h-3 w-3" />
                    {ficha.fotos_count}
                  </span>
                  {ficha.url_pdf && (
                    <span className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-blue-600">
                      <FileText className="h-3.5 w-3.5" />
                      PDF
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>

          {/* Paginacion */}
          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-3">
              <Button variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>
                Anterior
              </Button>
              <span className="text-sm text-gray-600">
                {page + 1} / {totalPages}
              </span>
              <Button
                variant="secondary"
                disabled={page + 1 >= totalPages}
                onClick={() => setPage(page + 1)}
              >
                Siguiente
              </Button>
            </div>
          )}
        </>
      )}

      {/* Detalle */}
      {selected && (
        <div
          className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setSelected(null)}
        >
          <div
            className="w-full max-w-md rounded-lg bg-white shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4">
              <h2 className="font-semibold text-gray-900">
                Ficha · {sucursalNombre(selected.sucursal_id)}
              </h2>
              <button
                type="button"
                onClick={() => setSelected(null)}
                className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                aria-label="Cerrar"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-3 px-5 py-4 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Fecha</span>
                <span className="font-medium text-gray-900">{formatDate(selected.fecha_auditoria)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Auditor</span>
                <span className="font-medium text-gray-900">{selected.auditor_nombre || '-'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Responsable desvios</span>
                <span className="font-medium text-gray-900">{selected.responsable_desvios || '-'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Puntuacion</span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-bold text-white ${scoreBadgeClasses(selected.puntuacion_promedio)}`}
                >
                  {selected.puntuacion_promedio != null
                    ? `${Number(selected.puntuacion_promedio).toFixed(1)}/5`
                    : 'Sin puntaje'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Desvios</span>
                <span className="font-medium text-red-600">{selected.desvios_count}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Fotos</span>
                <span className="font-medium text-gray-900">{selected.fotos_count}</span>
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t border-gray-200 px-5 py-4">
              <Button variant="secondary" onClick={() => setSelected(null)}>
                Cerrar
              </Button>
              {selected.url_pdf && (
                <Button onClick={() => window.open(selected.url_pdf as string, '_blank', 'noopener')}>
                  <Download className="mr-2 inline h-4 w-4" />
                  Descargar PDF
                </Button>
              )}
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  );
}

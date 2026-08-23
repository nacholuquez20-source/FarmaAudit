import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AlertTriangle, Brain, Calendar, Camera, CheckCircle2, Download, FileText, FilterX, Loader2, TrendingDown, TrendingUp, X } from 'lucide-react';
import { Button } from '../components/Button';
import { FeedbackState } from '../components/FeedbackState';
import { Input } from '../components/Input';
import { Select } from '../components/Select';
import { analisisAuditoria, exportControlesPdf, getFichaById, getFichaPdfUrl, getSucursales } from '../lib/api';
import type { AnalisisAuditoria } from '../lib/api';
import { supabase } from '../lib/supabase';
import { BLOQUES_FICHA, getBloqueScore } from '../lib/utils';
import type { AuditFicha, Sucursal } from '../types';
import { toast } from 'sonner';

type Ficha = AuditFicha;

const PAGE_SIZE = 24;

function scoreBadgeClasses(score: number | null): string {
  if (score === null) return 'bg-gray-400';
  if (score >= 4) return 'bg-green-600';
  if (score >= 3) return 'bg-yellow-500';
  return 'bg-red-600';
}

function formatTime(dateString: string | null): string {
  if (!dateString) return '';
  return new Date(dateString).toLocaleTimeString('es-AR', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatDateTime(dateString: string | null): string {
  if (!dateString) return 'Sin fecha';
  return new Date(dateString).toLocaleDateString('es-AR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function fichaFecha(ficha: Ficha): string | null {
  return ficha.fecha_auditoria || ficha.created_at || null;
}

function dayKey(dateString: string | null): string {
  if (!dateString) return 'sin-fecha';
  return new Date(dateString).toDateString();
}

function dayLabel(key: string): string {
  if (key === 'sin-fecha') return 'Sin fecha';
  const date = new Date(key);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);

  if (date.toDateString() === today.toDateString()) return 'Hoy';
  if (date.toDateString() === yesterday.toDateString()) return 'Ayer';

  const label = date.toLocaleDateString('es-AR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: date.getFullYear() === today.getFullYear() ? undefined : 'numeric',
  });
  return label.charAt(0).toUpperCase() + label.slice(1);
}

// Galería de fichas de perfumería — sin <AppLayout> propio, se monta dentro
// de la pestaña "Fichas" de /sucursales (ver SucursalesModule.tsx).
export function AuditFichesGalleryPanel() {
  const [searchParams] = useSearchParams();

  const [fichas, setFichas] = useState<Ficha[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);

  const [sucursalId, setSucursalId] = useState(() => searchParams.get('sucursal_id') ?? '');
  const [auditor, setAuditor] = useState('');
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');
  const [page, setPage] = useState(0);

  const [selected, setSelected] = useState<Ficha | null>(null);
  const [exporting, setExporting] = useState(false);
  const [analisis, setAnalisis] = useState<AnalisisAuditoria | null>(null);
  const [loadingAnalisis, setLoadingAnalisis] = useState(false);

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
          : 'No se pudieron cargar las auditorias. Verifica tu conexion e intenta de nuevo.'
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

  const handleAnalizar = async () => {
    if (!selected) return;
    setLoadingAnalisis(true);
    setAnalisis(null);
    try {
      const result = await analisisAuditoria(selected.id);
      setAnalisis(result);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo ejecutar el análisis');
    } finally {
      setLoadingAnalisis(false);
    }
  };

  const handleSelectFicha = (ficha: Ficha) => {
    setSelected(ficha);
    setAnalisis(null);
    setLoadingAnalisis(false);
  };

  // Deep-link desde DesvioDetail ("Ver ficha"): abre el modal de una ficha
  // puntual aunque no esté en la página actual de la grilla.
  useEffect(() => {
    const fichaId = searchParams.get('ficha');
    if (!fichaId) return;
    let cancelled = false;
    getFichaById(fichaId)
      .then((ficha) => {
        if (!cancelled && ficha) handleSelectFicha(ficha);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [searchParams]);

  const updateFilter = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value);
    setPage(0);
  };

  const setDia = (value: string) => {
    setFechaDesde(value);
    setFechaHasta(value);
    setPage(0);
  };

  const handleExportPdf = async () => {
    setExporting(true);
    try {
      const blob = await exportControlesPdf({
        sucursalId: sucursalId || undefined,
        fechaDesde: fechaDesde || undefined,
        fechaHasta: fechaHasta || undefined,
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `FarmaAudit_Controles_${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast.success('PDF de controles generado');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo exportar el PDF');
    } finally {
      setExporting(false);
    }
  };

  // Group fichas of the current page by day (already sorted desc by fecha)
  const grupos = useMemo(() => {
    const map = new Map<string, Ficha[]>();
    for (const ficha of fichas) {
      const key = dayKey(fichaFecha(ficha));
      const group = map.get(key);
      if (group) group.push(ficha);
      else map.set(key, [ficha]);
    }
    return Array.from(map.entries());
  }, [fichas]);


  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      {/* Filtros */}
      <div className="mb-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-6">
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
            label="Dia"
            type="date"
            value={fechaDesde === fechaHasta ? fechaDesde : ''}
            onChange={(e) => setDia(e.target.value)}
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
          <div className="flex items-end gap-2">
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
        <div className="mt-4 flex justify-end border-t border-gray-100 pt-4">
          <Button onClick={() => void handleExportPdf()} disabled={exporting}>
            <FileText className="mr-2 inline h-4 w-4" />
            {exporting ? 'Generando PDF...' : 'Exportar PDF de controles'}
          </Button>
        </div>
      </div>

      {/* Contenido */}
      {loading ? (
        <FeedbackState title="Cargando auditorias..." tone="loading" />
      ) : error ? (
        <FeedbackState title="Error al cargar" description={error} tone="error" />
      ) : fichas.length === 0 ? (
        <FeedbackState
          title={hasFilters ? 'Sin resultados con estos filtros.' : 'Todavia no hay auditorias registradas.'}
          description={
            hasFilters
              ? 'Proba quitando algun filtro.'
              : 'Las auditorias se registran automaticamente al completarlas por WhatsApp.'
          }
          tone="info"
        />
      ) : (
        <>
          <p className="mb-3 text-sm text-gray-500">
            {total} auditoria{total === 1 ? '' : 's'} · pagina {page + 1} de {totalPages}
          </p>

          <div className="space-y-8">
            {grupos.map(([key, grupo]) => (
              <section key={key}>
                <div className="mb-3 flex items-center gap-3">
                  <Calendar className="h-4 w-4 text-primary-navy" />
                  <h2 className="text-base font-semibold text-gray-900">{dayLabel(key)}</h2>
                  <span className="rounded-full bg-primary-navy/10 px-2 py-0.5 text-xs font-medium text-primary-navy">
                    {grupo.length} auditoria{grupo.length === 1 ? '' : 's'}
                  </span>
                  <div className="h-px flex-1 bg-gray-200" />
                </div>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {grupo.map((ficha) => (
                    <button
                      key={ficha.id}
                      type="button"
                      onClick={() => handleSelectFicha(ficha)}
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
                        <span className="text-xs text-gray-500">{formatTime(fichaFecha(ficha))}</span>
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
              </section>
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
            className={`w-full rounded-lg bg-white shadow-xl transition-all ${analisis ? 'max-w-2xl' : 'max-w-md'}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4">
              <h2 className="font-semibold text-gray-900">
                Auditoria · {sucursalNombre(selected.sucursal_id)}
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
                <span className="font-medium text-gray-900">{formatDateTime(fichaFecha(selected))}</span>
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
                <span className="text-gray-500">Puntuación</span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-bold text-white ${scoreBadgeClasses(selected.puntuacion_promedio)}`}
                >
                  {selected.puntuacion_promedio != null
                    ? `${Number(selected.puntuacion_promedio).toFixed(1)}/5`
                    : 'Sin puntaje'}
                </span>
              </div>

              <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Puntajes por bloque
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {BLOQUES_FICHA.map(({ key, label }) => {
                    const value = getBloqueScore(selected, key);
                    return (
                      <div key={key} className="flex items-center justify-between">
                        <span className="text-gray-600">{label}</span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-bold text-white ${scoreBadgeClasses(value)}`}
                        >
                          {value != null ? `${value}/5` : '-'}
                        </span>
                      </div>
                    );
                  })}
                </div>
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

            {/* Desvios de esta ficha: el detalle completo (con fotos) vive en
                la página de la sucursal, no se duplica ese listado acá. */}
            <div className="border-t border-gray-200 px-5 py-4">
              {selected.desvios_count > 0 ? (
                <Link
                  to={`/sucursales/${selected.sucursal_id}/auditorias/${selected.id}`}
                  className="flex items-center justify-center gap-2 rounded-lg border border-primary-navy/20 px-3 py-2 text-sm font-medium text-primary-navy hover:bg-primary-navy/5"
                >
                  Ver desvíos y fotos de esta auditoría
                </Link>
              ) : (
                <p className="text-sm text-gray-500">Esta ficha no generó desvíos.</p>
              )}
            </div>

            {/* Panel de análisis multi-agente */}
            {(loadingAnalisis || analisis) && (
              <div className="border-t border-gray-200 px-5 py-4">
                {loadingAnalisis && (
                  <div className="flex flex-col items-center gap-3 py-6 text-center">
                    <Loader2 className="h-8 w-8 animate-spin text-primary-navy" />
                    <p className="text-sm font-medium text-gray-700">Consultando 5 agentes especializados…</p>
                    <p className="text-xs text-gray-400">Auditor · Calidad · Perfumería · Normativo · Negocio</p>
                  </div>
                )}

                {analisis && !loadingAnalisis && (
                  <div className="space-y-4">
                    {/* Header */}
                    <div className="flex items-center gap-2">
                      <Brain className="h-4 w-4 text-primary-navy" />
                      <span className="text-sm font-semibold text-primary-navy">Análisis IA</span>
                      <span
                        className={`ml-auto rounded-full px-2.5 py-0.5 text-xs font-bold text-white ${
                          analisis.sintesis.nivel_urgencia === 'critico'
                            ? 'bg-red-600'
                            : analisis.sintesis.nivel_urgencia === 'urgente'
                              ? 'bg-orange-500'
                              : 'bg-green-600'
                        }`}
                      >
                        {analisis.sintesis.nivel_urgencia.toUpperCase()}
                      </span>
                    </div>

                    {/* Diagnóstico */}
                    <p className="text-sm text-gray-700">{analisis.sintesis.diagnostico_integral}</p>

                    {/* Métricas rápidas */}
                    <div className="grid grid-cols-3 gap-2">
                      <div className="rounded-lg bg-gray-50 p-2 text-center">
                        <p className="text-xs text-gray-500">Riesgo global</p>
                        <p className={`text-lg font-bold ${analisis.sintesis.score_riesgo_global >= 70 ? 'text-red-600' : analisis.sintesis.score_riesgo_global >= 40 ? 'text-orange-500' : 'text-green-600'}`}>
                          {analisis.sintesis.score_riesgo_global}
                        </p>
      </div>
                      <div className="rounded-lg bg-gray-50 p-2 text-center">
                        <p className="text-xs text-gray-500">Tendencia</p>
                        <div className="flex justify-center pt-1">
                          {analisis.agentes.calidad.tendencia_general === 'mejorando'
                            ? <TrendingUp className="h-5 w-5 text-green-600" />
                            : analisis.agentes.calidad.tendencia_general === 'deteriorando'
                              ? <TrendingDown className="h-5 w-5 text-red-600" />
                              : <span className="text-sm font-semibold text-gray-500">—</span>}
                        </div>
                      </div>
                      <div className="rounded-lg bg-gray-50 p-2 text-center">
                        <p className="text-xs text-gray-500">Próxima audit.</p>
                        <p className="text-sm font-bold text-gray-800">{analisis.sintesis.proxima_auditoria_en_dias}d</p>
                      </div>
                    </div>

                    {/* Alertas de agentes */}
                    <div className="flex flex-wrap gap-2">
                      {analisis.agentes.normativo.requiere_accion_inmediata && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">
                          <AlertTriangle className="h-3 w-3" /> ANMAT: {analisis.agentes.normativo.nivel_alerta_anmat}
                        </span>
                      )}
                      {analisis.agentes.perfumeria.planograma_comprometido && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-orange-50 px-2 py-0.5 text-xs font-medium text-orange-700">
                          <AlertTriangle className="h-3 w-3" /> Planograma comprometido
                        </span>
                      )}
                      {analisis.agentes.calidad.desvios_reincidentes.length > 0 && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-yellow-50 px-2 py-0.5 text-xs font-medium text-yellow-700">
                          <AlertTriangle className="h-3 w-3" /> {analisis.agentes.calidad.desvios_reincidentes.length} desvio(s) reincidente(s)
                        </span>
                      )}
                    </div>

                    {/* Top 3 acciones */}
                    <div>
                      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Acciones inmediatas</p>
                      <ul className="space-y-1">
                        {analisis.sintesis.top_3_acciones_inmediatas.map((accion, i) => (
                          <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary-navy" />
                            {accion}
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* Mensaje para encargado (colapsable) */}
                    <details className="rounded-lg border border-gray-200 text-sm">
                      <summary className="cursor-pointer px-3 py-2 font-medium text-gray-700 hover:bg-gray-50">
                        Mensaje para el encargado
                      </summary>
                      <p className="whitespace-pre-line px-3 pb-3 pt-1 text-gray-600">
                        {analisis.sintesis.mensaje_para_encargado}
                      </p>
                    </details>
                  </div>
                )}
              </div>
            )}

            <div className="flex flex-wrap justify-end gap-2 border-t border-gray-200 px-5 py-4">
              <Button variant="secondary" onClick={() => setSelected(null)}>
                Cerrar
              </Button>
              <Button
                variant="secondary"
                onClick={() => void handleAnalizar()}
                disabled={loadingAnalisis}
              >
                {loadingAnalisis
                  ? <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
                  : <Brain className="mr-2 inline h-4 w-4" />}
                {analisis ? 'Re-analizar' : 'Analizar con IA'}
              </Button>
              {selected.url_pdf && (
                <Button onClick={() => void getFichaPdfUrl(selected).then((url) => url && window.open(url, '_blank', 'noopener'))}>
                  <Download className="mr-2 inline h-4 w-4" />
                  Descargar PDF
                </Button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

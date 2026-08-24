import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, FilterX } from 'lucide-react';
import { Button } from '../Button';
import { FeedbackState } from '../FeedbackState';
import { Input } from '../Input';
import { Select } from '../Select';
import { getFichaPdfUrl, getSucursales } from '../../lib/api';
import { supabase } from '../../lib/supabase';
import { diasDesde, formatDate, severidadColor } from '../../lib/utils';
import type { AuditFicha, Gestion, Sucursal } from '../../types';

const PAGE_SIZE = 30;
const MAX_CHIPS = 6;

// Tabla de auditorías cross-sucursal: reemplaza las bandejas "esperando" y
// "cerrado" — el estado de cada auditoría ya se ve inline (chips + columnas
// Respuesta/Demora), no hace falta separarlas en pestañas distintas.
// Mismo patrón de datos que AuditFichesGallery.tsx (fichas, filtros por
// sucursal/fecha) + el agrupamiento gestion-por-ficha de SucursalDetail.tsx,
// pero cross-sucursal y en formato tabla en vez de card grid.
export function AuditoriasDesviosTable() {
  const navigate = useNavigate();

  const [fichas, setFichas] = useState<AuditFicha[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [gestionesPorFicha, setGestionesPorFicha] = useState<Map<string, Gestion[]>>(new Map());

  const [sucursalId, setSucursalId] = useState('');
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');
  const [page, setPage] = useState(0);

  useEffect(() => {
    getSucursales()
      .then(setSucursales)
      .catch(() => setSucursales([]));
  }, []);

  const sucursalNombre = useMemo(() => {
    const map = new Map(sucursales.map((s) => [s.id, s.nombre]));
    return (id: string) => map.get(id) || id;
  }, [sucursales]);

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
      if (fechaDesde) query = query.gte('fecha_auditoria', fechaDesde);
      if (fechaHasta) query = query.lte('fecha_auditoria', `${fechaHasta}T23:59:59`);

      const { data, count, error: queryError } = await query;
      if (queryError) throw queryError;
      const fichasData = (data as AuditFicha[]) || [];
      setFichas(fichasData);
      setTotal(count ?? 0);

      const ids = fichasData.map((f) => f.id);
      if (ids.length === 0) {
        setGestionesPorFicha(new Map());
        return;
      }
      const { data: gestionData, error: gestionError } = await supabase
        .from('gestion')
        .select('*')
        .in('ficha_id', ids);
      if (gestionError) throw gestionError;
      const grouped = new Map<string, Gestion[]>();
      for (const g of (gestionData as Gestion[]) || []) {
        if (!g.ficha_id) continue;
        const list = grouped.get(g.ficha_id);
        if (list) list.push(g);
        else grouped.set(g.ficha_id, [g]);
      }
      setGestionesPorFicha(grouped);
    } catch (err) {
      console.error('Error loading auditorías:', err);
      setError('No se pudieron cargar las auditorías. Verificá tu conexión e intentá de nuevo.');
      setFichas([]);
      setTotal(0);
      setGestionesPorFicha(new Map());
    } finally {
      setLoading(false);
    }
  }, [sucursalId, fechaDesde, fechaHasta, page]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadFichas(), 0);
    return () => window.clearTimeout(timer);
  }, [loadFichas]);

  const hasFilters = Boolean(sucursalId || fechaDesde || fechaHasta);

  const clearFilters = () => {
    setSucursalId('');
    setFechaDesde('');
    setFechaHasta('');
    setPage(0);
  };

  const updateFilter = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value);
    setPage(0);
  };

  const setDia = (value: string) => {
    setFechaDesde(value);
    setFechaHasta(value);
    setPage(0);
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="p-5 lg:p-8">
      {/* Filtros */}
      <div className="mb-4 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Select
            label="Sucursal"
            value={sucursalId}
            onChange={(e) => updateFilter(setSucursalId)(e.target.value)}
            options={[{ value: '', label: 'Todas' }, ...sucursales.map((s) => ({ value: s.id, label: s.nombre }))]}
          />
          <Input
            label="Día"
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
          <div className="flex items-end">
            <Button variant="secondary" onClick={clearFilters} disabled={!hasFilters} className="w-full">
              <FilterX className="mr-2 inline h-4 w-4" />
              Limpiar
            </Button>
          </div>
        </div>
      </div>

      {loading ? (
        <FeedbackState title="Cargando auditorías..." tone="loading" />
      ) : error ? (
        <FeedbackState title="Error al cargar" description={error} tone="error" />
      ) : fichas.length === 0 ? (
        <FeedbackState
          title={hasFilters ? 'Sin auditorías con estos filtros.' : 'Todavía no hay auditorías registradas.'}
          description={hasFilters ? 'Probá quitando algún filtro.' : undefined}
          tone="info"
        />
      ) : (
        <>
          <p className="mb-3 text-sm text-gray-500">
            {total} auditoría{total === 1 ? '' : 's'} · página {page + 1} de {totalPages}
          </p>

          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
            <table className="w-full">
              <thead className="border-b bg-gray-100">
                <tr>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Fecha</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Sucursal</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Desvíos</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">PDF</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Respuesta</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Demora</th>
                </tr>
              </thead>
              <tbody>
                {fichas.map((ficha) => {
                  const ligadas = gestionesPorFicha.get(ficha.id) ?? [];
                  const resueltos = ligadas.filter((g) => g.estado === 'Resuelta' || g.estado === 'Cerrada').length;
                  const enRevision = ligadas.filter((g) => g.estado === 'En_revision').length;
                  const pendientes = ligadas.length - resueltos - enRevision;
                  const vencida = ligadas.some((g) => g.estado === 'Vencida');
                  const dias = diasDesde(ficha.fecha_auditoria || ficha.created_at);

                  return (
                    <tr
                      key={ficha.id}
                      onClick={() => navigate(`/sucursales/${ficha.sucursal_id}/auditorias/${ficha.id}`)}
                      className="cursor-pointer border-b hover:bg-gray-50"
                    >
                      <td className="whitespace-nowrap px-6 py-4 text-sm">
                        {formatDate(ficha.fecha_auditoria || ficha.created_at)}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-sm font-medium">
                        {sucursalNombre(ficha.sucursal_id)}
                      </td>
                      <td className="px-4 py-4">
                        {ligadas.length === 0 ? (
                          <span className="text-xs text-gray-300">—</span>
                        ) : (
                          <div className="flex flex-wrap items-center gap-1">
                            {ligadas.slice(0, MAX_CHIPS).map((g) => (
                              <span
                                key={g.id_gestion}
                                title={g.desvio}
                                className={`inline-flex h-6 min-w-[24px] items-center justify-center rounded-md px-1.5 text-xs font-bold ${severidadColor(g.severidad)}`}
                              >
                                {g.severidad[0]}
                              </span>
                            ))}
                            {ligadas.length > MAX_CHIPS && (
                              <span className="text-xs font-medium text-gray-500">
                                +{ligadas.length - MAX_CHIPS}
                              </span>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-4 text-center">
                        {ficha.url_pdf ? (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              void getFichaPdfUrl(ficha).then((url) => url && window.open(url, '_blank', 'noopener'));
                            }}
                            title="Ver PDF de esta auditoría"
                            className="inline-flex items-center gap-1 text-gray-400 hover:text-blue-600"
                          >
                            <FileText className="h-4 w-4" />
                          </button>
                        ) : (
                          <span className="text-xs text-gray-300">—</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4">
                        {ligadas.length === 0 ? (
                          <span className="text-xs text-gray-300">—</span>
                        ) : enRevision > 0 ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-bold text-blue-700">
                            En revisión ({enRevision})
                          </span>
                        ) : pendientes > 0 ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-bold text-gray-600">
                            {pendientes} pendiente{pendientes === 1 ? '' : 's'}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2.5 py-0.5 text-xs font-bold text-green-700">
                            Resuelto
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4">
                        {vencida ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-bold text-red-700">
                            Vencida
                          </span>
                        ) : pendientes > 0 && dias !== null ? (
                          <span className="text-sm text-gray-500">hace {dias} día{dias === 1 ? '' : 's'}</span>
                        ) : (
                          <span className="text-xs text-gray-300">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-3">
              <Button variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>
                Anterior
              </Button>
              <span className="text-sm text-gray-600">
                {page + 1} / {totalPages}
              </span>
              <Button variant="secondary" disabled={page + 1 >= totalPages} onClick={() => setPage(page + 1)}>
                Siguiente
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { useDesvios } from '../hooks/useDesvios';
import { useReportes } from '../hooks/useReportes';
import type { Gestion, GestionState, Severidad } from '../types';
import { resolveEvidenceUrl } from '../lib/api';
import { formatDate, gestionStateColor, gestionStateLabel, severidadColor } from '../lib/utils';

const severidades: Severidad[] = ['Alta', 'Media', 'Baja'];
const estados: GestionState[] = ['Abierta', 'En_proceso', 'Resuelta', 'Vencida', 'Cerrada'];

function getShortDescription(text: string): string {
  if (text.length <= 88) return text;
  return `${text.slice(0, 85)}...`;
}

function getDisplayDate(gestion: Gestion): string {
  return gestion.created_at || gestion.updated_at || gestion.plazo_fecha;
}

function EvidenceThumbnail({ source, alt }: { source?: string | null; alt: string }) {
  const [url, setUrl] = useState('');

  useEffect(() => {
    let cancelled = false;
    if (!source) {
      setUrl('');
      return;
    }

    const loadUrl = async () => {
      try {
        const resolved = await resolveEvidenceUrl(source);
        if (!cancelled) setUrl(resolved);
      } catch {
        if (!cancelled) setUrl('');
      }
    };

    void loadUrl();
    return () => {
      cancelled = true;
    };
  }, [source]);

  if (!source) return <span className="text-xs text-gray-400">Sin foto</span>;

  if (!url) {
    return <div className="h-14 w-14 shrink-0 rounded border border-gray-200 bg-gray-100" title="Cargando evidencia" />;
  }

  return (
    <a href={url} target="_blank" rel="noreferrer" className="block h-14 w-14 shrink-0">
      <img
        src={url}
        alt={alt}
        className="h-14 w-14 rounded border border-gray-300 object-cover transition hover:scale-150"
        title="Abrir evidencia"
      />
    </a>
  );
}

export default function Desvios() {
  const navigate = useNavigate();
  const { desvios, allDesvios, loading, error, filters, setFilters, resetFilters, sucursalesResumen, isOverdue } = useDesvios();
  const { reportes } = useReportes();
  const [selectedSucursal, setSelectedSucursal] = useState<string | null>(null);

  const hasActiveFilters = Object.values(filters).some(Boolean);
  const desviosDelaSucursal = selectedSucursal ? desvios.filter((d) => d.sucursal === selectedSucursal) : [];
  const reportesById = new Map(reportes.map((r) => [r.id, r]));

  return (
    <AppLayout title={selectedSucursal ? `Desvíos - ${selectedSucursal}` : 'Centro de Desvíos'}>
      {/* VISTA MAESTRO: Sucursales con desvios activos */}
      {!selectedSucursal && (
        <>
          <div className="mb-6">
            <p className="text-sm text-gray-600">
              {sucursalesResumen.length} sucursal{sucursalesResumen.length !== 1 ? 'es' : ''} con desvíos activos
            </p>
          </div>

          {loading && <FeedbackState title="Cargando desvios..." />}

          {error && <FeedbackState title={error} tone="error" />}

          {!loading && !error && sucursalesResumen.length === 0 && (
            <FeedbackState title="No hay desvíos activos." />
          )}

          {!loading && !error && sucursalesResumen.length > 0 && (
            <div className="overflow-hidden rounded-lg bg-white shadow">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[600px]">
                  <thead className="border-b bg-gray-100">
                    <tr>
                      <th className="px-4 py-3 text-left text-sm font-semibold">Sucursal</th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">Desvíos Activos</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold">Próximo Vencimiento</th>
                      <th className="px-4 py-3 text-right text-sm font-semibold">Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sucursalesResumen.map((sucursal) => (
                      <tr key={sucursal.nombre} className="border-b hover:bg-gray-50">
                        <td className="px-4 py-4 text-sm font-medium text-gray-900">{sucursal.nombre}</td>
                        <td className="px-4 py-4 text-center">
                          <span className="inline-block rounded-full bg-red-100 px-3 py-1 text-sm font-semibold text-red-700">
                            {sucursal.desviosActivos}
                          </span>
                        </td>
                        <td className="px-4 py-4 text-sm">
                          {sucursal.proximoVencimiento ? (
                            <div className={isOverdue({ plazo_fecha: sucursal.proximoVencimiento } as Gestion) ? 'font-semibold text-red-700' : 'text-gray-700'}>
                              {formatDate(sucursal.proximoVencimiento)}
                              {isOverdue({ plazo_fecha: sucursal.proximoVencimiento } as Gestion) && (
                                <div className="text-xs font-medium text-red-600">Vencido</div>
                              )}
                            </div>
                          ) : (
                            <span className="text-gray-500">-</span>
                          )}
                        </td>
                        <td className="px-4 py-4 text-right">
                          <button
                            type="button"
                            onClick={() => setSelectedSucursal(sucursal.nombre)}
                            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
                          >
                            Ver desvíos
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* VISTA DETALLE: Desvios de la sucursal seleccionada */}
      {selectedSucursal && (
        <>
          <div className="mb-6 flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                setSelectedSucursal(null);
                resetFilters();
              }}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
            >
              ← Volver
            </button>
            <p className="text-sm text-gray-600">
              {desviosDelaSucursal.length} de {allDesvios.filter((d) => d.sucursal === selectedSucursal).length} desvíos visibles
            </p>
          </div>

          <div className="mb-6 rounded-lg bg-white p-4 shadow">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-5">
              <label className="text-sm font-medium text-gray-700 lg:col-span-2">
                Buscar
                <input
                  type="search"
                  value={filters.search}
                  onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))}
                  placeholder="Descripción, área o responsable"
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
                />
              </label>

              <label className="text-sm font-medium text-gray-700">
                Severidad
                <select
                  value={filters.severidad}
                  onChange={(event) => setFilters((current) => ({ ...current, severidad: event.target.value as '' | Severidad }))}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Todas</option>
                  {severidades.map((severidad) => (
                    <option key={severidad} value={severidad}>
                      {severidad}
                    </option>
                  ))}
                </select>
              </label>

              <label className="text-sm font-medium text-gray-700">
                Estado
                <select
                  value={filters.estado}
                  onChange={(event) => setFilters((current) => ({ ...current, estado: event.target.value as '' | GestionState }))}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Todos</option>
                  {estados.map((estado) => (
                    <option key={estado} value={estado}>
                      {gestionStateLabel(estado)}
                    </option>
                  ))}
                </select>
              </label>

              {hasActiveFilters && (
                <div className="flex items-end">
                  <button
                    type="button"
                    onClick={resetFilters}
                    className="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
                  >
                    Limpiar filtros
                  </button>
                </div>
              )}
            </div>
          </div>

          {loading && <FeedbackState title="Cargando desvios..." />}

          {error && <FeedbackState title={error} tone="error" />}

          {!loading && !error && desviosDelaSucursal.length === 0 && (
            <FeedbackState title="No se encontraron desvíos con los filtros seleccionados." />
          )}

          {!loading && !error && desviosDelaSucursal.length > 0 && (
            <div className="overflow-hidden rounded-lg bg-white shadow">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1200px]">
                  <thead className="border-b bg-gray-100">
                    <tr>
                      <th className="px-4 py-3 text-left text-sm font-semibold">Fecha</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold">Área</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold">Descripción y evidencia</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold">Severidad</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold">Estado</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold">Vencimiento</th>
                      <th className="px-4 py-3 text-right text-sm font-semibold">Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {desviosDelaSucursal.map((desvio) => {
                      const reporte = reportesById.get(desvio.id_reporte);
                      return (
                        <tr key={desvio.id_gestion} className="border-b hover:bg-gray-50">
                          <td className="px-4 py-4 text-sm text-gray-700">{formatDate(getDisplayDate(desvio))}</td>
                          <td className="px-4 py-4 text-sm text-gray-600">{desvio.area}</td>
                          <td className="max-w-md px-4 py-4 text-sm text-gray-700" title={desvio.desvio}>
                            <div className="flex items-start gap-3">
                              <EvidenceThumbnail source={reporte?.foto_url} alt={desvio.desvio} />
                              <span>{getShortDescription(desvio.desvio)}</span>
                            </div>
                          </td>
                          <td className="px-4 py-4 text-sm">
                            <span className={`rounded px-3 py-1 text-xs font-semibold ${severidadColor(desvio.severidad)}`}>
                              {desvio.severidad}
                            </span>
                          </td>
                          <td className="px-4 py-4 text-sm">
                            <span className={`rounded px-3 py-1 text-xs font-semibold ${gestionStateColor(desvio.estado)}`}>
                              {gestionStateLabel(desvio.estado)}
                            </span>
                          </td>
                          <td className="px-4 py-4 text-sm">
                            <div className={isOverdue(desvio) ? 'font-semibold text-red-700' : 'text-gray-700'}>
                              {formatDate(desvio.plazo_fecha)}
                            </div>
                            {isOverdue(desvio) && <div className="text-xs font-medium text-red-600">Vencido</div>}
                          </td>
                          <td className="px-4 py-4 text-right text-sm">
                            <button
                              type="button"
                              onClick={() => navigate(`/desvios/${desvio.id_gestion}`)}
                              className="rounded-lg border border-gray-300 px-3 py-2 font-medium text-gray-700 hover:bg-gray-100"
                            >
                              Ver detalle
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </AppLayout>
  );
}

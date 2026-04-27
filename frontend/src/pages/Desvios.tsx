import { useNavigate } from 'react-router-dom';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { useDesvios } from '../hooks/useDesvios';
import type { Gestion, GestionState, Severidad } from '../types';
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

function getWhatsappUrl(gestion: Gestion): string | null {
  const phone = gestion.tel_responsable.replace(/\D/g, '');
  if (!phone) return null;

  const message = [
    `Hola ${gestion.responsable || ''}`.trim(),
    `Te contactamos por un desvio registrado en ${gestion.sucursal}.`,
    `Detalle: ${gestion.desvio}`,
    `Severidad: ${gestion.severidad}`,
    `Vencimiento: ${formatDate(gestion.plazo_fecha)}`,
  ].join('\n');

  return `https://wa.me/${phone}?text=${encodeURIComponent(message)}`;
}

export default function Desvios() {
  const navigate = useNavigate();
  const { desvios, allDesvios, loading, error, filters, setFilters, resetFilters, sucursales, isOverdue } = useDesvios();

  const hasActiveFilters = Object.values(filters).some(Boolean);

  return (
    <AppLayout title="Centro de Desvíos">
      <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm text-gray-600">
            {desvios.length} de {allDesvios.length} desvíos visibles
          </p>
        </div>
        {hasActiveFilters && (
          <button
            type="button"
            onClick={resetFilters}
            className="self-start rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 sm:self-auto"
          >
            Limpiar filtros
          </button>
        )}
      </div>

      <div className="mb-6 rounded-lg bg-white p-4 shadow">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-6">
          <label className="text-sm font-medium text-gray-700 lg:col-span-2">
            Buscar
            <input
              type="search"
              value={filters.search}
              onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))}
              placeholder="Sucursal, responsable o descripción"
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
            />
          </label>

          <label className="text-sm font-medium text-gray-700">
            Sucursal
            <select
              value={filters.sucursal}
              onChange={(event) => setFilters((current) => ({ ...current, sucursal: event.target.value }))}
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Todas</option>
              {sucursales.map((sucursal) => (
                <option key={sucursal} value={sucursal}>
                  {sucursal}
                </option>
              ))}
            </select>
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

          <div className="grid grid-cols-2 gap-3 lg:col-span-1">
            <label className="text-sm font-medium text-gray-700">
              Desde
              <input
                type="date"
                value={filters.fechaDesde}
                onChange={(event) => setFilters((current) => ({ ...current, fechaDesde: event.target.value }))}
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
              />
            </label>
            <label className="text-sm font-medium text-gray-700">
              Hasta
              <input
                type="date"
                value={filters.fechaHasta}
                onChange={(event) => setFilters((current) => ({ ...current, fechaHasta: event.target.value }))}
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
              />
            </label>
          </div>
        </div>
      </div>

      {loading && <FeedbackState title="Cargando desvios..." />}

      {error && <FeedbackState title={error} tone="error" />}

      {!loading && !error && desvios.length === 0 && (
        <FeedbackState title="No se encontraron desvios con los filtros seleccionados." />
      )}

      {!loading && !error && desvios.length > 0 && (
        <div className="overflow-hidden rounded-lg bg-white shadow">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1040px]">
              <thead className="border-b bg-gray-100">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Fecha</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Sucursal</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Área</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Descripción</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Severidad</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Responsable</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Estado</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Vencimiento</th>
                  <th className="px-4 py-3 text-right text-sm font-semibold">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {desvios.map((desvio) => {
                  const whatsappUrl = getWhatsappUrl(desvio);
                  return (
                    <tr key={desvio.id_gestion} className="border-b hover:bg-gray-50">
                      <td className="px-4 py-4 text-sm text-gray-700">{formatDate(getDisplayDate(desvio))}</td>
                      <td className="px-4 py-4 text-sm font-medium text-gray-900">{desvio.sucursal}</td>
                      <td className="px-4 py-4 text-sm text-gray-600">{desvio.area}</td>
                      <td className="max-w-sm px-4 py-4 text-sm text-gray-700" title={desvio.desvio}>
                        {getShortDescription(desvio.desvio)}
                      </td>
                      <td className="px-4 py-4 text-sm">
                        <span className={`rounded px-3 py-1 text-xs font-semibold ${severidadColor(desvio.severidad)}`}>
                          {desvio.severidad}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-sm text-gray-700">
                        <div className="font-medium">{desvio.responsable || '-'}</div>
                        <div className="text-xs text-gray-500">{desvio.tel_responsable || 'Sin teléfono'}</div>
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
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => navigate(`/desvios/${desvio.id_gestion}`)}
                            className="rounded-lg border border-gray-300 px-3 py-2 font-medium text-gray-700 hover:bg-gray-100"
                          >
                            Ver detalle
                          </button>
                          {whatsappUrl ? (
                            <a
                              href={whatsappUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="rounded-lg bg-green-600 px-3 py-2 font-medium text-white hover:bg-green-700"
                            >
                              Contactar
                            </a>
                          ) : (
                            <button
                              type="button"
                              disabled
                              className="rounded-lg bg-gray-200 px-3 py-2 font-medium text-gray-500"
                            >
                              Contactar
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </AppLayout>
  );
}

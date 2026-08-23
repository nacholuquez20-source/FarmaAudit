import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { whatsappAuditLink } from '../../lib/utils';
import { ClipboardCheck, MapPin } from 'lucide-react';
import { FeedbackState } from '../FeedbackState';
import { SucursalMapPicker } from '../SucursalMapPicker';
import { useSucursales } from '../../hooks/useSucursales';
import { updateSucursal } from '../../lib/api';
import type { AutosaveStatus, Sucursal, SucursalEditableField, SucursalUpdate } from '../../types';

interface EditableColumn {
  field: SucursalEditableField;
  label: string;
  className?: string;
}

const EDITABLE_COLUMNS: EditableColumn[] = [
  { field: 'nombre', label: 'Nombre', className: 'min-w-[190px]' },
  { field: 'direccion', label: 'Direccion', className: 'min-w-[220px]' },
  { field: 'zona', label: 'Zona', className: 'min-w-[120px]' },
  { field: 'responsable', label: 'Responsable', className: 'min-w-[170px]' },
  { field: 'tel_responsable', label: 'Telefono', className: 'min-w-[150px]' },
];

const SAVE_DELAY_MS = 700;

function getCellKey(id: string, field: SucursalEditableField): string {
  return `${id}:${field}`;
}

function normalizeSucursal(sucursal: Sucursal): Sucursal {
  return {
    ...sucursal,
    nombre: sucursal.nombre || '',
    direccion: sucursal.direccion || '',
    zona: sucursal.zona || '',
    responsable: sucursal.responsable || '',
    tel_responsable: sucursal.tel_responsable || '',
  };
}

function getStatusLabel(status: AutosaveStatus | undefined): string {
  if (status === 'pending') return 'Pendiente';
  if (status === 'saving') return 'Guardando';
  if (status === 'saved') return 'Guardado';
  if (status === 'error') return 'Error';
  return '';
}

function getStatusClasses(status: AutosaveStatus | undefined): string {
  if (status === 'pending') return 'border-amber-300 bg-amber-50 text-amber-800';
  if (status === 'saving') return 'border-blue-300 bg-blue-50 text-blue-800';
  if (status === 'saved') return 'border-emerald-300 bg-emerald-50 text-emerald-800';
  if (status === 'error') return 'border-red-300 bg-red-50 text-red-800';
  return 'border-transparent bg-transparent text-transparent';
}

// Solo entra un admin (montado dentro de la pestaña "Sucursales" de
// Gestión) — a diferencia de la vieja pagina Sucursales.tsx, no hace falta
// soportar el rol sucursal acá (ese rol nunca navegó a esto desde el menú).
export function SucursalesEditorTab() {
  const { sucursales, loading, error } = useSucursales();
  const [rows, setRows] = useState<Sucursal[]>([]);
  const [searchText, setSearchText] = useState('');
  const [saveStatus, setSaveStatus] = useState<Record<string, AutosaveStatus>>({});
  const [rowFlash, setRowFlash] = useState<Record<string, boolean>>({});
  const [saveErrors, setSaveErrors] = useState<Record<string, string>>({});
  const timersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const navigate = useNavigate();
  const [ubicando, setUbicando] = useState<Sucursal | null>(null);

  useEffect(() => {
    setRows(sucursales.map(normalizeSucursal));
  }, [sucursales]);

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      Object.values(timers).forEach(clearTimeout);
    };
  }, []);

  const filteredSucursales = useMemo(() => {
    const normalizedSearch = searchText.trim().toLowerCase();
    if (!normalizedSearch) return rows;

    return rows.filter((sucursal) =>
      [
        sucursal.id,
        sucursal.nombre,
        sucursal.direccion,
        sucursal.responsable,
        sucursal.tel_responsable,
        sucursal.zona,
      ]
        .join(' ')
        .toLowerCase()
        .includes(normalizedSearch),
    );
  }, [rows, searchText]);

  const persistField = async (id: string, field: SucursalEditableField, value: string) => {
    const cellKey = getCellKey(id, field);
    setSaveStatus((current) => ({ ...current, [cellKey]: 'saving' }));
    setSaveErrors((current) => {
      const next = { ...current };
      delete next[cellKey];
      return next;
    });

    try {
      const updated = await updateSucursal(id, { [field]: value } as SucursalUpdate);
      const normalized = normalizeSucursal(updated);
      setRows((current) => current.map((row) => (row.id === id ? normalized : row)));
      setSaveStatus((current) => ({ ...current, [cellKey]: 'saved' }));
      setRowFlash((current) => ({ ...current, [id]: true }));

      window.setTimeout(() => {
        setSaveStatus((current) => ({ ...current, [cellKey]: 'idle' }));
      }, 1600);
      window.setTimeout(() => {
        setRowFlash((current) => ({ ...current, [id]: false }));
      }, 900);
    } catch (err) {
      setSaveStatus((current) => ({ ...current, [cellKey]: 'error' }));
      setSaveErrors((current) => ({
        ...current,
        [cellKey]: err instanceof Error ? err.message : 'No se pudo guardar el cambio',
      }));
    }
  };

  const handleFieldChange = (id: string, field: SucursalEditableField, value: string) => {
    const cellKey = getCellKey(id, field);
    setRows((current) => current.map((row) => (row.id === id ? { ...row, [field]: value } : row)));
    setSaveStatus((current) => ({ ...current, [cellKey]: 'pending' }));

    if (timersRef.current[cellKey]) clearTimeout(timersRef.current[cellKey]);
    timersRef.current[cellKey] = setTimeout(() => {
      persistField(id, field, value.trim());
    }, SAVE_DELAY_MS);
  };

  const getRowActiveStatus = (sucursal: Sucursal): AutosaveStatus | undefined => {
    const rowStatuses = EDITABLE_COLUMNS.map((column) => saveStatus[getCellKey(sucursal.id, column.field)]);
    return rowStatuses.find((status) => status && status !== 'idle');
  };

  const handleUbicacionSaved = (updated: Sucursal) => {
    setRows((current) => current.map((row) => (row.id === updated.id ? normalizeSucursal(updated) : row)));
    setRowFlash((current) => ({ ...current, [updated.id]: true }));
    window.setTimeout(() => {
      setRowFlash((current) => ({ ...current, [updated.id]: false }));
    }, 900);
  };

  if (loading) {
    return <FeedbackState title="Cargando sucursales..." tone="loading" />;
  }

  return (
    <div>
      {error && (
        <div className="mb-4">
          <FeedbackState title={error} tone="error" />
        </div>
      )}

      <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <input
          type="text"
          placeholder="Buscar por nombre, zona, telefono o direccion..."
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          className="w-full rounded-lg border border-gray-300 px-4 py-2 focus:border-transparent focus:ring-2 focus:ring-blue-500 lg:max-w-xl"
        />
        <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-2 text-sm text-blue-800">
          Edicion activa: los cambios se guardan automaticamente.
        </div>
      </div>

      <div className="hidden overflow-hidden rounded-lg bg-white shadow xl:block">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] table-fixed">
            <thead className="border-b bg-gray-100">
              <tr>
                {EDITABLE_COLUMNS.map((column) => (
                  <th key={column.field} className={`px-4 py-3 text-left text-sm font-semibold ${column.className || ''}`}>
                    {column.label}
                  </th>
                ))}
                <th className="px-4 py-3 text-left text-sm font-semibold">Estado</th>
                <th className="px-4 py-3 text-right text-sm font-semibold">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {filteredSucursales.map((sucursal) => {
                const activeStatus = getRowActiveStatus(sucursal);
                return (
                  <tr
                    key={sucursal.id}
                    className={`border-b transition-colors duration-500 ${
                      rowFlash[sucursal.id] ? 'bg-emerald-50' : 'hover:bg-gray-50'
                    }`}
                  >
                    {EDITABLE_COLUMNS.map((column) => {
                      const cellKey = getCellKey(sucursal.id, column.field);
                      const status = saveStatus[cellKey];
                      const hasError = status === 'error';
                      return (
                        <td key={column.field} className="px-4 py-3 align-top">
                          <input
                            type="text"
                            value={sucursal[column.field]}
                            onChange={(event) => handleFieldChange(sucursal.id, column.field, event.target.value)}
                            title={saveErrors[cellKey] || column.label}
                            className={`w-full rounded-md border px-3 py-2 text-sm transition focus:border-transparent focus:ring-2 disabled:bg-gray-50 disabled:text-gray-600 ${
                              hasError
                                ? 'border-red-300 bg-red-50 focus:ring-red-500'
                                : status === 'saved'
                                  ? 'border-emerald-300 bg-emerald-50 focus:ring-emerald-500'
                                  : status === 'saving' || status === 'pending'
                                    ? 'border-blue-300 bg-blue-50 focus:ring-blue-500'
                                    : 'border-gray-300 bg-white focus:ring-blue-500'
                            }`}
                          />
                          {hasError && <p className="mt-1 text-xs text-red-700">{saveErrors[cellKey]}</p>}
                        </td>
                      );
                    })}
                    <td className="px-4 py-3 align-top">
                      <span
                        className={`inline-flex min-w-[88px] justify-center rounded-full border px-3 py-1 text-xs font-semibold transition ${getStatusClasses(
                          activeStatus,
                        )}`}
                      >
                        {getStatusLabel(activeStatus) || 'Listo'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right align-top">
                      <div className="flex items-center justify-end gap-2">
                        <a
                          href={whatsappAuditLink()}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1.5 rounded-md bg-primary-navy px-3 py-2 text-sm font-medium text-white transition hover:bg-primary-navy/90"
                        >
                          <ClipboardCheck className="h-3.5 w-3.5" />
                          Auditar
                        </a>
                        <button
                          type="button"
                          onClick={() => setUbicando(sucursal)}
                          title={sucursal.lat != null ? 'Ya ubicada — click para reubicar' : 'Sin ubicar en el mapa'}
                          className={`flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-gray-100 ${
                            sucursal.lat != null ? 'border-emerald-300 text-emerald-700' : 'border-amber-300 text-amber-700'
                          }`}
                        >
                          <MapPin className="h-3.5 w-3.5" />
                          Ubicar
                        </button>
                        <button
                          type="button"
                          onClick={() => navigate(`/sucursales/${sucursal.id}`)}
                          className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-100"
                        >
                          Ver
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid gap-4 xl:hidden">
        {filteredSucursales.map((sucursal) => {
          const activeStatus = getRowActiveStatus(sucursal);
          return (
            <section
              key={sucursal.id}
              className={`rounded-lg border border-gray-200 bg-white p-4 shadow-sm transition-colors duration-500 ${
                rowFlash[sucursal.id] ? 'bg-emerald-50' : ''
              }`}
            >
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-gray-900">{sucursal.nombre || 'Sucursal sin nombre'}</h2>
                  <p className="text-sm text-gray-500">{sucursal.zona || 'Sin zona'}</p>
                </div>
                <span
                  className={`inline-flex min-w-[88px] justify-center rounded-full border px-3 py-1 text-xs font-semibold transition ${getStatusClasses(
                    activeStatus,
                  )}`}
                >
                  {getStatusLabel(activeStatus) || 'Listo'}
                </span>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                {EDITABLE_COLUMNS.map((column) => {
                  const cellKey = getCellKey(sucursal.id, column.field);
                  const status = saveStatus[cellKey];
                  const hasError = status === 'error';
                  return (
                    <label key={column.field} className={column.field === 'direccion' ? 'sm:col-span-2' : ''}>
                      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">
                        {column.label}
                      </span>
                      <input
                        type="text"
                        value={sucursal[column.field]}
                        onChange={(event) => handleFieldChange(sucursal.id, column.field, event.target.value)}
                        title={saveErrors[cellKey] || column.label}
                        className={`w-full rounded-md border px-3 py-2 text-sm transition focus:border-transparent focus:ring-2 disabled:bg-gray-50 disabled:text-gray-600 ${
                          hasError
                            ? 'border-red-300 bg-red-50 focus:ring-red-500'
                            : status === 'saved'
                              ? 'border-emerald-300 bg-emerald-50 focus:ring-emerald-500'
                              : status === 'saving' || status === 'pending'
                                ? 'border-blue-300 bg-blue-50 focus:ring-blue-500'
                                : 'border-gray-300 bg-white focus:ring-blue-500'
                        }`}
                      />
                      {hasError && <p className="mt-1 text-xs text-red-700">{saveErrors[cellKey]}</p>}
                    </label>
                  );
                })}
              </div>

              <div className="mt-4 flex flex-wrap justify-end gap-2">
                <a
                  href={whatsappAuditLink()}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 rounded-md bg-primary-navy px-3 py-2 text-sm font-medium text-white transition hover:bg-primary-navy/90"
                >
                  <ClipboardCheck className="h-3.5 w-3.5" />
                  Auditar
                </a>
                <button
                  type="button"
                  onClick={() => setUbicando(sucursal)}
                  className={`flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-gray-100 ${
                    sucursal.lat != null ? 'border-emerald-300 text-emerald-700' : 'border-amber-300 text-amber-700'
                  }`}
                >
                  <MapPin className="h-3.5 w-3.5" />
                  Ubicar
                </button>
                <button
                  type="button"
                  onClick={() => navigate(`/sucursales/${sucursal.id}`)}
                  className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-100"
                >
                  Ver detalle
                </button>
              </div>
            </section>
          );
        })}
      </div>

      {filteredSucursales.length === 0 && (
        <div className="mt-4">
          <FeedbackState
            title="No se encontraron farmacias"
            description="Probá con otro nombre, zona, teléfono o dirección — o limpiá la búsqueda para ver todas."
          />
        </div>
      )}

      {ubicando && (
        <SucursalMapPicker
          sucursal={ubicando}
          onClose={() => setUbicando(null)}
          onSaved={handleUbicacionSaved}
        />
      )}
    </div>
  );
}

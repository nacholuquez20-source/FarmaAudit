import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { toast } from 'sonner';
import { ClipboardCheck, MapPin } from 'lucide-react';
import { Button } from '../Button';
import { ConfirmDialog } from '../ConfirmDialog';
import { FeedbackState } from '../FeedbackState';
import { Input } from '../Input';
import { SucursalMapPicker } from '../SucursalMapPicker';
import { whatsappAuditLink } from '../../lib/utils';
import { createSucursal, listUsuariosWhatsapp, setSucursalActiva, updateSucursal } from '../../lib/api';
import { useSucursales } from '../../hooks/useSucursales';
import type { AutosaveStatus, Sucursal, SucursalCreate, SucursalEditableField, SucursalUpdate, UsuarioWhatsapp } from '../../types';

const EMPTY_FORM: SucursalCreate = {
  id: '',
  nombre: '',
  direccion: '',
  responsable: '',
  tel_responsable: '',
  zona: '',
};

interface EditableColumn {
  field: SucursalEditableField;
  label: string;
  className?: string;
}

// "Responsable"/"tel_responsable" quedan afuera de esta lista a propósito: son texto
// informativo que se carga una sola vez al crear la sucursal (ver EMPTY_FORM), pero
// quien realmente recibe los mensajes del bot es el usuario de WhatsApp con
// rol='responsable_sucursal' vinculado a esta sucursal (tabla usuarios_whatsapp) — se
// muestra abajo como badge derivado, no como campo editable acá, para no tener dos
// lugares que dicen "responsable" y pueden desincronizarse en silencio.
const EDITABLE_COLUMNS: EditableColumn[] = [
  { field: 'nombre', label: 'Nombre', className: 'min-w-[190px]' },
  { field: 'direccion', label: 'Dirección', className: 'min-w-[220px]' },
  { field: 'zona', label: 'Zona', className: 'min-w-[120px]' },
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

// sucursales.id es text con formato SUC002. Propone el siguiente libre,
// dejando que el admin lo edite si necesita otro esquema de numeración.
function nextSucursalId(sucursales: Sucursal[]): string {
  let max = 0;
  for (const s of sucursales) {
    const match = /^SUC(\d+)$/i.exec(s.id.trim());
    if (match) max = Math.max(max, parseInt(match[1], 10));
  }
  return `SUC${String(max + 1).padStart(3, '0')}`;
}

// Panel único de administración de sucursales: alta, edición de datos básicos
// (autosave), ubicación en el mapa, archivado/reactivación, y el vínculo real con
// WhatsApp (quién recibe los mensajes de esa sucursal). Antes eran dos tablas
// apiladas (una para alta/archivado, otra para edición) que mostraban campos
// solapados — quedó unificado en una sola fuente de verdad visual.
export function SucursalesTab() {
  const { sucursales, loading, error: loadError, reload } = useSucursales();
  const [usuariosWhatsapp, setUsuariosWhatsapp] = useState<UsuarioWhatsapp[]>([]);

  const [rows, setRows] = useState<Sucursal[]>([]);
  const [searchText, setSearchText] = useState('');
  const [saveStatus, setSaveStatus] = useState<Record<string, AutosaveStatus>>({});
  const [rowFlash, setRowFlash] = useState<Record<string, boolean>>({});
  const [saveErrors, setSaveErrors] = useState<Record<string, string>>({});
  const timersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const navigate = useNavigate();
  const [ubicando, setUbicando] = useState<Sucursal | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<SucursalCreate>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [confirmArchive, setConfirmArchive] = useState<Sucursal | null>(null);

  useEffect(() => {
    setRows(sucursales.map(normalizeSucursal));
  }, [sucursales]);

  useEffect(() => {
    listUsuariosWhatsapp()
      .then(setUsuariosWhatsapp)
      .catch(() => {
        /* El badge de vinculación con WhatsApp queda vacío si esto falla; no bloquea el resto del panel. */
      });
  }, []);

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      Object.values(timers).forEach(clearTimeout);
    };
  }, []);

  // Responsable REAL de cada sucursal: el usuario de WhatsApp con
  // rol='responsable_sucursal' vinculado y activo. Puede no haber ninguno
  // (sucursal recién creada, o el dueño todavía no la cargó en la otra pestaña).
  const responsableWhatsappPorSucursal = useMemo(() => {
    const map = new Map<string, UsuarioWhatsapp>();
    for (const u of usuariosWhatsapp) {
      if (u.rol === 'responsable_sucursal' && u.activo && u.id_sucursal) {
        map.set(u.id_sucursal, u);
      }
    }
    return map;
  }, [usuariosWhatsapp]);

  const filteredSucursales = useMemo(() => {
    const normalizedSearch = searchText.trim().toLowerCase();
    if (!normalizedSearch) return rows;

    return rows.filter((sucursal) =>
      [sucursal.id, sucursal.nombre, sucursal.direccion, sucursal.responsable, sucursal.tel_responsable, sucursal.zona]
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

  const openForm = () => {
    setForm({ ...EMPTY_FORM, id: nextSucursalId(sucursales) });
    setFormError('');
    setShowForm(true);
  };

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!form.id.trim() || !form.nombre.trim()) {
      setFormError('ID y nombre son obligatorios.');
      return;
    }
    if (sucursales.some((s) => s.id.toLowerCase() === form.id.trim().toLowerCase())) {
      setFormError(`Ya existe una sucursal con id "${form.id}".`);
      return;
    }

    setSubmitting(true);
    setFormError('');
    try {
      const created = await createSucursal({ ...form, id: form.id.trim() });
      await reload();
      setShowForm(false);
      toast.success(`Sucursal ${created.nombre} creada correctamente`);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Error al crear la sucursal');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReactivate = async (sucursal: Sucursal) => {
    setTogglingId(sucursal.id);
    try {
      await setSucursalActiva(sucursal.id, true);
      await reload();
      toast.success(`${sucursal.nombre} reactivada`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al reactivar la sucursal');
    } finally {
      setTogglingId(null);
    }
  };

  const handleArchive = async () => {
    if (!confirmArchive) return;
    setTogglingId(confirmArchive.id);
    try {
      await setSucursalActiva(confirmArchive.id, false);
      await reload();
      toast.success(`${confirmArchive.nombre} archivada. Ya no aparece en el menú del bot.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al archivar la sucursal');
    } finally {
      setTogglingId(null);
      setConfirmArchive(null);
    }
  };

  function ResponsableBadge({ sucursal }: { sucursal: Sucursal }) {
    const responsable = responsableWhatsappPorSucursal.get(sucursal.id);
    if (responsable) {
      return (
        <div className="text-sm">
          <div className="font-medium text-gray-900">{responsable.nombre}</div>
          <div className="text-xs text-gray-500">{responsable.telefono}</div>
        </div>
      );
    }
    return (
      <Link
        to="/admin?tab=whatsapp"
        className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 hover:bg-amber-100"
        title="No hay un usuario de WhatsApp con rol Responsable de sucursal vinculado a esta sucursal"
      >
        Sin asignar en WhatsApp
      </Link>
    );
  }

  function AccionesSucursal({ sucursal }: { sucursal: Sucursal }) {
    return (
      <div className="flex flex-wrap items-center justify-end gap-2">
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
        {sucursal.activo ? (
          <Button type="button" variant="outline" size="sm" disabled={togglingId === sucursal.id} onClick={() => setConfirmArchive(sucursal)}>
            Archivar
          </Button>
        ) : (
          <Button type="button" variant="secondary" size="sm" isLoading={togglingId === sucursal.id} onClick={() => handleReactivate(sucursal)}>
            Reactivar
          </Button>
        )}
      </div>
    );
  }

  if (loading) return <FeedbackState title="Cargando sucursales..." tone="loading" />;
  if (loadError) return <FeedbackState title={loadError} tone="error" />;

  return (
    <>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Sucursales</h2>
          <p className="mt-1 text-sm text-gray-600">
            Nombre, dirección y zona se guardan solos al escribir. El teléfono que realmente recibe los mensajes
            del bot se administra en <Link to="/admin?tab=whatsapp" className="font-semibold text-primary-navy hover:underline">Usuarios WhatsApp</Link> —
            acá se muestra a quién está vinculada cada sucursal.
          </p>
        </div>
        <Button type="button" onClick={showForm ? () => setShowForm(false) : openForm}>
          {showForm ? 'Cancelar' : '+ Agregar sucursal'}
        </Button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="mb-6 rounded-lg bg-white p-6 shadow">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <Input
              label="ID"
              value={form.id}
              onChange={(e) => setForm({ ...form, id: e.target.value.toUpperCase() })}
              required
              helperText="Formato sugerido: SUC0XX"
            />
            <Input label="Nombre" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} required />
            <Input label="Zona" value={form.zona || ''} onChange={(e) => setForm({ ...form, zona: e.target.value })} />
            <Input label="Dirección" value={form.direccion || ''} onChange={(e) => setForm({ ...form, direccion: e.target.value })} />
          </div>
          {formError && <p className="mt-3 text-sm font-medium text-red-600">{formError}</p>}
          <p className="mt-3 text-xs text-gray-500">
            Después de crearla, andá a <Link to="/admin?tab=whatsapp" className="font-semibold text-primary-navy hover:underline">Usuarios WhatsApp</Link> para asignarle el responsable que va a recibir los mensajes del bot.
          </p>
          <Button type="submit" variant="success" className="mt-4" isLoading={submitting}>
            Crear sucursal
          </Button>
        </form>
      )}

      <div className="mb-4">
        <input
          type="text"
          placeholder="Buscar por nombre, zona o dirección..."
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          className="w-full rounded-lg border border-gray-300 px-4 py-2 focus:border-transparent focus:ring-2 focus:ring-blue-500 lg:max-w-xl"
        />
      </div>

      <div className="hidden overflow-hidden rounded-lg bg-white shadow xl:block">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1080px] table-fixed">
            <thead className="border-b bg-gray-100">
              <tr>
                {EDITABLE_COLUMNS.map((column) => (
                  <th key={column.field} className={`px-4 py-3 text-left text-sm font-semibold ${column.className || ''}`}>
                    {column.label}
                  </th>
                ))}
                <th className="px-4 py-3 text-left text-sm font-semibold min-w-[160px]">Responsable (WhatsApp)</th>
                <th className="px-4 py-3 text-left text-sm font-semibold">Estado</th>
                <th className="px-4 py-3 text-right text-sm font-semibold">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {filteredSucursales.length === 0 ? (
                <tr>
                  <td colSpan={EDITABLE_COLUMNS.length + 3} className="px-6 py-8 text-center text-gray-500">
                    {rows.length === 0 ? 'No hay sucursales cargadas.' : 'Ninguna sucursal coincide con la búsqueda.'}
                  </td>
                </tr>
              ) : (
                filteredSucursales.map((sucursal) => {
                  const activeStatus = getRowActiveStatus(sucursal);
                  return (
                    <tr
                      key={sucursal.id}
                      className={`border-b transition-colors duration-500 ${
                        rowFlash[sucursal.id] ? 'bg-emerald-50' : sucursal.activo ? 'hover:bg-gray-50' : 'opacity-60 hover:bg-gray-50'
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
                        <ResponsableBadge sucursal={sucursal} />
                      </td>
                      <td className="px-4 py-3 align-top">
                        <div className="flex flex-col items-start gap-1.5">
                          <span className={`rounded px-3 py-1 text-xs font-semibold ${sucursal.activo ? 'bg-green-100 text-green-800' : 'bg-gray-200 text-gray-700'}`}>
                            {sucursal.activo ? 'Activa' : 'Archivada'}
                          </span>
                          <span
                            className={`inline-flex min-w-[80px] justify-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold transition ${getStatusClasses(activeStatus)}`}
                          >
                            {getStatusLabel(activeStatus)}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 align-top text-right">
                        <AccionesSucursal sucursal={sucursal} />
                      </td>
                    </tr>
                  );
                })
              )}
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
                rowFlash[sucursal.id] ? 'bg-emerald-50' : sucursal.activo ? '' : 'opacity-60'
              }`}
            >
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-gray-900">{sucursal.nombre || 'Sucursal sin nombre'}</h2>
                  <p className="text-sm text-gray-500">{sucursal.zona || 'Sin zona'}</p>
                </div>
                <div className="flex flex-col items-end gap-1.5">
                  <span className={`rounded px-3 py-1 text-xs font-semibold ${sucursal.activo ? 'bg-green-100 text-green-800' : 'bg-gray-200 text-gray-700'}`}>
                    {sucursal.activo ? 'Activa' : 'Archivada'}
                  </span>
                  <span
                    className={`inline-flex min-w-[80px] justify-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold transition ${getStatusClasses(activeStatus)}`}
                  >
                    {getStatusLabel(activeStatus)}
                  </span>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                {EDITABLE_COLUMNS.map((column) => {
                  const cellKey = getCellKey(sucursal.id, column.field);
                  const status = saveStatus[cellKey];
                  const hasError = status === 'error';
                  return (
                    <label key={column.field} className={column.field === 'direccion' ? 'sm:col-span-2' : ''}>
                      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">{column.label}</span>
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

              <div className="mt-3">
                <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Responsable (WhatsApp)</span>
                <ResponsableBadge sucursal={sucursal} />
              </div>

              <div className="mt-4">
                <AccionesSucursal sucursal={sucursal} />
              </div>
            </section>
          );
        })}
        {filteredSucursales.length === 0 && (
          <FeedbackState
            title={rows.length === 0 ? 'No hay sucursales cargadas.' : 'Ninguna sucursal coincide con la búsqueda.'}
          />
        )}
      </div>

      <ConfirmDialog
        open={!!confirmArchive}
        title={`¿Archivar ${confirmArchive?.nombre}?`}
        description="Desaparece del menú del bot y de los selectores de alta. El historial de auditorías y desvíos se conserva y podés reactivarla en cualquier momento."
        confirmLabel="Archivar"
        tone="danger"
        loading={!!confirmArchive && togglingId === confirmArchive.id}
        onConfirm={handleArchive}
        onCancel={() => setConfirmArchive(null)}
      />

      {ubicando && <SucursalMapPicker sucursal={ubicando} onClose={() => setUbicando(null)} onSaved={handleUbicacionSaved} />}
    </>
  );
}

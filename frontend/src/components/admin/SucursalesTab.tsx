import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { toast } from 'sonner';
import { AlertCircle, Archive, ArchiveRestore, Check, Eye, Loader2, MapPin } from 'lucide-react';
import { Button } from '../Button';
import { ConfirmDialog } from '../ConfirmDialog';
import { FeedbackState } from '../FeedbackState';
import { Input } from '../Input';
import { SucursalMapPicker } from '../SucursalMapPicker';
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

  function AutosaveInput({ sucursal, column }: { sucursal: Sucursal; column: EditableColumn }) {
    const cellKey = getCellKey(sucursal.id, column.field);
    const status = saveStatus[cellKey];
    const error = saveErrors[cellKey];
    return (
      <div className="relative">
        <input
          type="text"
          value={sucursal[column.field]}
          onChange={(event) => handleFieldChange(sucursal.id, column.field, event.target.value)}
          title={error || column.label}
          className={`w-full rounded-md border bg-transparent px-2.5 py-1.5 text-sm text-gray-900 transition focus:bg-white focus:outline-none focus:ring-2 ${
            error
              ? 'border-red-300 bg-red-50 focus:border-red-400 focus:ring-red-500/30'
              : 'border-transparent hover:border-gray-200 hover:bg-gray-50 focus:border-primary-navy/40 focus:ring-primary-navy/20'
          } ${status && status !== 'idle' ? 'pr-7' : ''}`}
        />
        {status === 'saving' || status === 'pending' ? (
          <Loader2 className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-blue-500" />
        ) : status === 'saved' ? (
          <Check className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-emerald-500" />
        ) : status === 'error' ? (
          <AlertCircle className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-red-500" />
        ) : null}
        {error && <p className="mt-1 text-xs text-red-700">{error}</p>}
      </div>
    );
  }

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
    const chip = 'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium transition disabled:opacity-50';
    const isToggling = togglingId === sucursal.id;
    return (
      <div className="flex flex-wrap items-center justify-end gap-1.5">
        <button
          type="button"
          onClick={() => navigate(`/sucursales/${sucursal.id}`)}
          className={`${chip} border-gray-200 text-gray-600 hover:border-gray-300 hover:bg-gray-50 hover:text-gray-900`}
        >
          <Eye className="h-3.5 w-3.5" />
          Ver
        </button>
        <button
          type="button"
          onClick={() => setUbicando(sucursal)}
          title={sucursal.lat != null ? 'Ya ubicada — click para reubicar' : 'Sin ubicar en el mapa'}
          className={`${chip} ${
            sucursal.lat != null
              ? 'border-gray-200 text-gray-600 hover:border-gray-300 hover:bg-gray-50 hover:text-gray-900'
              : 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100'
          }`}
        >
          <MapPin className="h-3.5 w-3.5" />
          Ubicar
        </button>
        {sucursal.activo ? (
          <button
            type="button"
            disabled={isToggling}
            onClick={() => setConfirmArchive(sucursal)}
            className={`${chip} border-gray-200 text-gray-500 hover:border-red-200 hover:bg-red-50 hover:text-red-600`}
          >
            <Archive className="h-3.5 w-3.5" />
            Archivar
          </button>
        ) : (
          <button
            type="button"
            disabled={isToggling}
            onClick={() => handleReactivate(sucursal)}
            className={`${chip} border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100`}
          >
            {isToggling ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ArchiveRestore className="h-3.5 w-3.5" />}
            Reactivar
          </button>
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

      <div className="hidden overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm xl:block">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[940px] table-fixed">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                {EDITABLE_COLUMNS.map((column) => (
                  <th
                    key={column.field}
                    className={`px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 ${column.className || ''}`}
                  >
                    {column.label}
                  </th>
                ))}
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 min-w-[160px]">
                  Responsable (WhatsApp)
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 min-w-[100px]">Estado</th>
                <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-gray-500 min-w-[220px]">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filteredSucursales.length === 0 ? (
                <tr>
                  <td colSpan={EDITABLE_COLUMNS.length + 3} className="px-6 py-8 text-center text-gray-500">
                    {rows.length === 0 ? 'No hay sucursales cargadas.' : 'Ninguna sucursal coincide con la búsqueda.'}
                  </td>
                </tr>
              ) : (
                filteredSucursales.map((sucursal) => (
                  <tr
                    key={sucursal.id}
                    className={`transition-colors duration-500 ${
                      rowFlash[sucursal.id] ? 'bg-emerald-50' : sucursal.activo ? 'hover:bg-gray-50/70' : 'opacity-60 hover:bg-gray-50/70'
                    }`}
                  >
                    {EDITABLE_COLUMNS.map((column) => (
                      <td key={column.field} className="px-4 py-2 align-top">
                        <AutosaveInput sucursal={sucursal} column={column} />
                      </td>
                    ))}
                    <td className="px-4 py-2 align-top">
                      <ResponsableBadge sucursal={sucursal} />
                    </td>
                    <td className="px-4 py-2 align-top">
                      <span
                        className={`inline-flex rounded px-2.5 py-1 text-xs font-semibold ${
                          sucursal.activo ? 'bg-green-100 text-green-800' : 'bg-gray-200 text-gray-700'
                        }`}
                      >
                        {sucursal.activo ? 'Activa' : 'Archivada'}
                      </span>
                    </td>
                    <td className="px-4 py-2 align-top text-right">
                      <AccionesSucursal sucursal={sucursal} />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid gap-4 xl:hidden">
        {filteredSucursales.map((sucursal) => (
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
              <span className={`rounded px-2.5 py-1 text-xs font-semibold ${sucursal.activo ? 'bg-green-100 text-green-800' : 'bg-gray-200 text-gray-700'}`}>
                {sucursal.activo ? 'Activa' : 'Archivada'}
              </span>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {EDITABLE_COLUMNS.map((column) => (
                <label key={column.field} className={column.field === 'direccion' ? 'sm:col-span-2' : ''}>
                  <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">{column.label}</span>
                  <AutosaveInput sucursal={sucursal} column={column} />
                </label>
              ))}
            </div>

            <div className="mt-3">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Responsable (WhatsApp)</span>
              <ResponsableBadge sucursal={sucursal} />
            </div>

            <div className="mt-4">
              <AccionesSucursal sucursal={sucursal} />
            </div>
          </section>
        ))}
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

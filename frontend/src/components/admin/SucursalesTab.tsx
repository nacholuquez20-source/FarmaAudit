import { useState } from 'react';
import { toast } from 'sonner';
import { Button, ConfirmDialog, FeedbackState, Input } from '../index';
import { createSucursal, setSucursalActiva } from '../../lib/api';
import { useSucursales } from '../../hooks/useSucursales';
import type { Sucursal, SucursalCreate } from '../../types';

const EMPTY_FORM: SucursalCreate = {
  id: '',
  nombre: '',
  direccion: '',
  responsable: '',
  tel_responsable: '',
  zona: '',
};

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

export function SucursalesTab() {
  const { sucursales, loading, error: loadError, reload } = useSucursales();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<SucursalCreate>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [confirmArchive, setConfirmArchive] = useState<Sucursal | null>(null);

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

  if (loading) return <FeedbackState title="Cargando sucursales..." tone="loading" />;
  if (loadError) return <FeedbackState title={loadError} tone="error" />;

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Sucursales</h2>
          <p className="mt-1 text-sm text-gray-600">
            Alta de sucursales nuevas y baja lógica de las que dejan de operar. Una sucursal archivada
            desaparece del menú del bot y de los selectores, pero conserva su historial.
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
            <Input
              label="Nombre"
              value={form.nombre}
              onChange={(e) => setForm({ ...form, nombre: e.target.value })}
              required
            />
            <Input
              label="Zona"
              value={form.zona || ''}
              onChange={(e) => setForm({ ...form, zona: e.target.value })}
            />
            <Input
              label="Dirección"
              value={form.direccion || ''}
              onChange={(e) => setForm({ ...form, direccion: e.target.value })}
            />
            <Input
              label="Responsable"
              value={form.responsable || ''}
              onChange={(e) => setForm({ ...form, responsable: e.target.value })}
              helperText="Opcional: podés vincular el responsable desde la pestaña Usuarios WhatsApp"
            />
            <Input
              label="Teléfono responsable"
              value={form.tel_responsable || ''}
              onChange={(e) => setForm({ ...form, tel_responsable: e.target.value })}
            />
          </div>
          {formError && <p className="mt-3 text-sm font-medium text-red-600">{formError}</p>}
          <Button type="submit" variant="success" className="mt-4" isLoading={submitting}>
            Crear sucursal
          </Button>
        </form>
      )}

      <div className="overflow-x-auto rounded-lg bg-white shadow">
        <table className="w-full min-w-[900px]">
          <thead className="border-b bg-gray-100">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-semibold">ID</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Nombre</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Zona</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Responsable</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Estado</th>
              <th className="px-4 py-3 text-left text-sm font-semibold" />
            </tr>
          </thead>
          <tbody>
            {sucursales.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                  No hay sucursales cargadas.
                </td>
              </tr>
            ) : (
              sucursales.map((s) => (
                <tr key={s.id} className={`border-b hover:bg-gray-50 ${s.activo ? '' : 'opacity-60'}`}>
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">{s.id}</td>
                  <td className="px-4 py-3 font-medium">{s.nombre}</td>
                  <td className="px-4 py-3 text-gray-600">{s.zona}</td>
                  <td className="px-4 py-3 text-gray-600">{s.responsable}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded px-3 py-1 text-xs font-semibold ${
                        s.activo ? 'bg-green-100 text-green-800' : 'bg-gray-200 text-gray-700'
                      }`}
                    >
                      {s.activo ? 'Activa' : 'Archivada'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {s.activo ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={togglingId === s.id}
                        onClick={() => setConfirmArchive(s)}
                      >
                        Archivar
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        isLoading={togglingId === s.id}
                        onClick={() => handleReactivate(s)}
                      >
                        Reactivar
                      </Button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
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
    </>
  );
}

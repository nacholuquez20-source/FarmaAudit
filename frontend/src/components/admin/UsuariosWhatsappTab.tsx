import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button, FeedbackState, Input, Select } from '../index';
import {
  createUsuarioWhatsapp,
  getTiposAuditoria,
  listUsuariosWhatsapp,
  updateUsuarioWhatsapp,
} from '../../lib/api';
import { useSucursales } from '../../hooks/useSucursales';
import type { CreateUsuarioWhatsappInput, RolWhatsapp, TipoAuditoria, UsuarioWhatsapp } from '../../types';

const EMPTY_FORM: CreateUsuarioWhatsappInput = {
  telefono: '',
  nombre: '',
  rol: 'auditor',
  id_sucursal: null,
  tipos_auditoria: [],
};

function rolLabel(rol: RolWhatsapp): string {
  return rol === 'responsable_sucursal' ? 'Responsable de sucursal' : 'Auditor';
}

export function UsuariosWhatsappTab() {
  const [usuarios, setUsuarios] = useState<UsuarioWhatsapp[]>([]);
  const [tipos, setTipos] = useState<TipoAuditoria[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<CreateUsuarioWhatsappInput>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const { sucursales } = useSucursales();
  const sucursalesActivas = sucursales.filter((s) => s.activo);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        const [usuariosData, tiposData] = await Promise.all([listUsuariosWhatsapp(), getTiposAuditoria()]);
        setUsuarios(usuariosData);
        setTipos(tiposData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error al cargar usuarios de WhatsApp');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const openForm = () => {
    setForm(EMPTY_FORM);
    setFormError('');
    setShowForm(true);
  };

  const handleRolChange = (rol: RolWhatsapp) => {
    setForm((current) => ({
      ...current,
      rol,
      id_sucursal: rol === 'responsable_sucursal' ? current.id_sucursal : null,
      tipos_auditoria: rol === 'auditor' ? current.tipos_auditoria : [],
    }));
  };

  const toggleTipo = (tipoId: string) => {
    setForm((current) => {
      const selected = current.tipos_auditoria || [];
      const next = selected.includes(tipoId) ? selected.filter((t) => t !== tipoId) : [...selected, tipoId];
      return { ...current, tipos_auditoria: next };
    });
  };

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!form.telefono.trim() || !form.nombre.trim()) {
      setFormError('Teléfono y nombre son obligatorios.');
      return;
    }
    if (form.rol === 'responsable_sucursal' && !form.id_sucursal) {
      setFormError('Asigná una sucursal para un responsable.');
      return;
    }
    if (form.rol === 'auditor' && !(form.tipos_auditoria?.length)) {
      setFormError('Seleccioná al menos un tipo de auditoría que cubre este auditor.');
      return;
    }

    setSubmitting(true);
    setFormError('');
    try {
      const created = await createUsuarioWhatsapp(form);
      setUsuarios((current) => [...current, created].sort((a, b) => a.nombre.localeCompare(b.nombre)));
      setShowForm(false);
      toast.success(`${rolLabel(created.rol)} ${created.nombre} creado correctamente`);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Error al crear el usuario');
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleActive = async (usuario: UsuarioWhatsapp) => {
    setTogglingId(usuario.id);
    try {
      const updated = await updateUsuarioWhatsapp(usuario.id, { activo: !usuario.activo });
      setUsuarios((current) =>
        current.map((u) => (u.id === usuario.id ? { ...u, ...updated, tipos_auditoria: u.tipos_auditoria } : u)),
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al actualizar el usuario');
    } finally {
      setTogglingId(null);
    }
  };

  if (loading) return <FeedbackState title="Cargando usuarios de WhatsApp..." tone="loading" />;

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Usuarios de WhatsApp</h2>
          <p className="mt-1 text-sm text-gray-600">
            Un teléfono es responsable de sucursal o auditor, nunca ambos. Un auditor puede cubrir más de un
            tipo de auditoría.
          </p>
        </div>
        <Button type="button" onClick={showForm ? () => setShowForm(false) : openForm}>
          {showForm ? 'Cancelar' : '+ Agregar usuario'}
        </Button>
      </div>

      {error && (
        <div className="mb-4">
          <FeedbackState title={error} tone="error" />
        </div>
      )}

      {showForm && (
        <form onSubmit={handleCreate} className="mb-6 rounded-lg bg-white p-6 shadow">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <Select
              label="Rol"
              value={form.rol}
              onChange={(e) => handleRolChange(e.target.value as RolWhatsapp)}
              options={[
                { value: 'auditor', label: 'Auditor' },
                { value: 'responsable_sucursal', label: 'Responsable de sucursal' },
              ]}
            />
            <Input
              label="Nombre"
              value={form.nombre}
              onChange={(e) => setForm({ ...form, nombre: e.target.value })}
              required
            />
            <Input
              label="Teléfono"
              value={form.telefono}
              onChange={(e) => setForm({ ...form, telefono: e.target.value })}
              required
              placeholder="+549..."
              helperText="Igual al número de WhatsApp"
            />
          </div>

          {form.rol === 'responsable_sucursal' ? (
            <div className="mt-4 max-w-sm">
              <Select
                label="Sucursal"
                value={form.id_sucursal || ''}
                onChange={(e) => setForm({ ...form, id_sucursal: e.target.value || null })}
                placeholder="Elegí una sucursal"
                options={sucursalesActivas.map((s) => ({ value: s.id, label: s.nombre }))}
              />
            </div>
          ) : (
            <div className="mt-4">
              <div className="mb-2 text-sm font-semibold text-gray-700">Tipos de auditoría que cubre</div>
              <div className="flex flex-wrap gap-2">
                {tipos.map((tipo) => (
                  <label key={tipo.id} className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-xs">
                    <input
                      type="checkbox"
                      checked={(form.tipos_auditoria || []).includes(tipo.id)}
                      onChange={() => toggleTipo(tipo.id)}
                    />
                    {tipo.nombre}
                  </label>
                ))}
              </div>
            </div>
          )}

          {formError && <p className="mt-3 text-sm font-medium text-red-600">{formError}</p>}
          <Button type="submit" variant="success" className="mt-4" isLoading={submitting}>
            Crear usuario
          </Button>
        </form>
      )}

      <div className="overflow-x-auto rounded-lg bg-white shadow">
        <table className="w-full min-w-[900px]">
          <thead className="border-b bg-gray-100">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-semibold">Nombre</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Teléfono</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Rol</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Sucursal / Tipos</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Estado</th>
            </tr>
          </thead>
          <tbody>
            {usuarios.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                  No hay usuarios de WhatsApp registrados.
                </td>
              </tr>
            ) : (
              usuarios.map((u) => (
                <tr key={u.id} className="border-b hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{u.nombre}</td>
                  <td className="px-4 py-3 text-gray-600">{u.telefono}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded px-2 py-1 text-xs font-semibold ${
                        u.rol === 'auditor' ? 'bg-blue-100 text-blue-800' : 'bg-purple-100 text-purple-800'
                      }`}
                    >
                      {rolLabel(u.rol)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {u.rol === 'responsable_sucursal'
                      ? sucursales.find((s) => s.id === u.id_sucursal)?.nombre || u.id_sucursal || '-'
                      : (u.tipos_auditoria || [])
                          .map((tipoId) => tipos.find((t) => t.id === tipoId)?.nombre || tipoId)
                          .join(', ') || '-'}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      disabled={togglingId === u.id}
                      onClick={() => handleToggleActive(u)}
                      className={`rounded px-3 py-1 text-xs font-semibold transition disabled:opacity-50 ${
                        u.activo ? 'bg-green-100 text-green-800 hover:bg-green-200' : 'bg-red-100 text-red-800 hover:bg-red-200'
                      }`}
                    >
                      {u.activo ? 'Activo' : 'Inactivo'}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

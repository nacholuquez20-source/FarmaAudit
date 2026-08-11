import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button, FeedbackState } from '../index';
import { createPanelUser, listPanelProfiles, updatePanelProfile } from '../../lib/api';
import { MODULE_OPTIONS, normalizeModulePermissions } from '../../lib/permissions';
import { useSucursales } from '../../hooks/useSucursales';
import type { ModulePermission, Role, UserProfile } from '../../types';

const ROLES: Role[] = ['admin', 'auditor', 'sucursal'];

const EMPTY_USER_FORM = {
  email: '',
  password: '',
  role: 'auditor' as Role,
  nombre: '',
  telefono: '',
  id_sucursal: '',
  permisos_modulos: normalizeModulePermissions('auditor'),
};

function shortId(id: string): string {
  if (id.length <= 10) return id;
  return `${id.slice(0, 8)}...`;
}

function roleLabel(role: Role): string {
  if (role === 'sucursal') return 'responsable sucursal';
  return role;
}

function ModuleChecks({
  role,
  selected,
  onToggle,
}: {
  role: Role;
  selected: ModulePermission[];
  onToggle: (module: ModulePermission) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {MODULE_OPTIONS.filter((module) => module.roles.includes(role)).map((module) => (
        <label key={module.key} className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-xs">
          <input type="checkbox" checked={selected.includes(module.key)} onChange={() => onToggle(module.key)} />
          {module.label}
        </label>
      ))}
    </div>
  );
}

export function UsuariosPanelTab() {
  const [profiles, setProfiles] = useState<UserProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [savingProfileId, setSavingProfileId] = useState<string | null>(null);
  const [showUserForm, setShowUserForm] = useState(false);
  const [userForm, setUserForm] = useState(EMPTY_USER_FORM);
  const [creatingUser, setCreatingUser] = useState(false);
  const [passwordDrafts, setPasswordDrafts] = useState<Record<string, string>>({});

  const { sucursales } = useSucursales();

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        setProfiles(await listPanelProfiles());
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error al cargar usuarios del panel');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const updateDraftProfile = (id: string, patch: Partial<UserProfile>) => {
    setProfiles(
      profiles.map((row) => {
        if (row.id !== id) return row;
        const next: UserProfile = { ...row, ...patch };
        if (patch.role) {
          next.permisos_modulos = normalizeModulePermissions(patch.role, next.permisos_modulos);
          if (patch.role !== 'sucursal') next.id_sucursal = null;
        }
        return next;
      }),
    );
  };

  const toggleProfileModule = (id: string, module: ModulePermission) => {
    const row = profiles.find((profile) => profile.id === id);
    if (!row) return;
    const current = normalizeModulePermissions(row.role, row.permisos_modulos);
    const next = current.includes(module)
      ? current.filter((item) => item !== module)
      : [...current, module];
    updateDraftProfile(id, { permisos_modulos: normalizeModulePermissions(row.role, next) });
  };

  const handleUserFormRole = (role: Role) => {
    setUserForm((current) => ({
      ...current,
      role,
      id_sucursal: role === 'sucursal' ? current.id_sucursal : '',
      permisos_modulos: normalizeModulePermissions(role),
    }));
  };

  const toggleUserFormModule = (module: ModulePermission) => {
    setUserForm((current) => {
      const modules = current.permisos_modulos.includes(module)
        ? current.permisos_modulos.filter((item) => item !== module)
        : [...current.permisos_modulos, module];
      return { ...current, permisos_modulos: normalizeModulePermissions(current.role, modules) };
    });
  };

  const handleCreatePanelUser = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!userForm.email.trim() || !userForm.password.trim()) {
      setError('Email y contraseña son obligatorios.');
      return;
    }
    setCreatingUser(true);
    setError('');

    try {
      if (userForm.role === 'sucursal' && !userForm.id_sucursal) {
        setError('Asigna una sucursal a los usuarios con rol Responsable.');
        return;
      }
      const created = await createPanelUser({
        email: userForm.email,
        password: userForm.password,
        role: userForm.role,
        nombre: userForm.nombre,
        telefono: userForm.telefono || null,
        id_sucursal: userForm.role === 'sucursal' ? userForm.id_sucursal || null : null,
        permisos_modulos: userForm.permisos_modulos,
      });
      setProfiles((current) =>
        [...current, created].sort((a, b) => a.role.localeCompare(b.role) || (a.nombre || '').localeCompare(b.nombre || '')),
      );
      setUserForm(EMPTY_USER_FORM);
      setShowUserForm(false);
      toast.success(`Usuario ${created.email} creado correctamente`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al crear usuario');
    } finally {
      setCreatingUser(false);
    }
  };

  const saveProfileRow = async (row: UserProfile) => {
    setSavingProfileId(row.id);
    setError('');
    try {
      if (row.role === 'sucursal' && !row.id_sucursal) {
        setError('Asigna una sucursal a los usuarios con rol Responsable.');
        return;
      }
      const saved = await updatePanelProfile(row.id, {
        email: row.email || undefined,
        password: passwordDrafts[row.id] || undefined,
        role: row.role,
        nombre: row.nombre ?? null,
        telefono: row.telefono ?? null,
        id_sucursal: row.id_sucursal ?? null,
        permisos_modulos: normalizeModulePermissions(row.role, row.permisos_modulos),
      });
      setProfiles(profiles.map((p) => (p.id === saved.id ? saved : p)));
      setPasswordDrafts((current) => ({ ...current, [row.id]: '' }));
      toast.success('Perfil guardado correctamente');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al guardar perfil');
    } finally {
      setSavingProfileId(null);
    }
  };

  if (loading) return <FeedbackState title="Cargando usuarios del panel..." tone="loading" />;

  return (
    <>
      {error && (
        <div className="mb-4">
          <FeedbackState title={error} tone="error" />
        </div>
      )}

      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <p className="text-sm text-gray-600">
          Crea usuarios con email, contraseña, rol y permisos por módulo. Los permisos controlan navegación y
          acceso al panel web.
        </p>
        <Button type="button" onClick={() => setShowUserForm((current) => !current)}>
          {showUserForm ? 'Cancelar' : '+ Crear usuario'}
        </Button>
      </div>

      {showUserForm && (
        <form onSubmit={handleCreatePanelUser} className="mb-6 rounded-lg bg-white p-6 shadow">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <label className="text-sm font-semibold text-gray-700">
              Email
              <input
                type="email"
                required
                value={userForm.email}
                onChange={(e) => setUserForm({ ...userForm, email: e.target.value })}
                className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm"
                placeholder="usuario@empresa.com"
              />
            </label>
            <label className="text-sm font-semibold text-gray-700">
              Contraseña
              <input
                type="password"
                required
                minLength={6}
                value={userForm.password}
                onChange={(e) => setUserForm({ ...userForm, password: e.target.value })}
                className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm"
                placeholder="Mínimo 6 caracteres"
              />
            </label>
            <label className="text-sm font-semibold text-gray-700">
              Nombre
              <input
                type="text"
                required
                value={userForm.nombre}
                onChange={(e) => setUserForm({ ...userForm, nombre: e.target.value })}
                className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm"
              />
            </label>
            <label className="text-sm font-semibold text-gray-700">
              Teléfono panel
              <input
                type="text"
                value={userForm.telefono}
                onChange={(e) => setUserForm({ ...userForm, telefono: e.target.value })}
                className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm"
                placeholder="Opcional"
              />
            </label>
            <label className="text-sm font-semibold text-gray-700">
              Rol
              <select
                value={userForm.role}
                onChange={(e) => handleUserFormRole(e.target.value as Role)}
                className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm"
              >
                {ROLES.map((role) => (
                  <option key={role} value={role}>{roleLabel(role)}</option>
                ))}
              </select>
            </label>
            <label className="text-sm font-semibold text-gray-700">
              Sucursal
              <select
                value={userForm.id_sucursal}
                onChange={(e) => setUserForm({ ...userForm, id_sucursal: e.target.value })}
                disabled={userForm.role !== 'sucursal'}
                className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm disabled:bg-gray-100"
              >
                <option value="">Sin sucursal</option>
                {sucursales.map((s) => (
                  <option key={s.id} value={s.id}>{s.nombre}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="mt-5">
            <div className="mb-2 text-sm font-semibold text-gray-700">Módulos habilitados</div>
            <ModuleChecks role={userForm.role} selected={userForm.permisos_modulos} onToggle={toggleUserFormModule} />
          </div>
          <Button type="submit" variant="success" className="mt-5" isLoading={creatingUser}>
            Crear usuario
          </Button>
        </form>
      )}

      <div className="overflow-x-auto rounded-lg bg-white shadow">
        <table className="min-w-[1280px] w-full">
          <thead className="border-b bg-gray-100">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-semibold">ID</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Email</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Nombre</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Teléfono panel</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Rol</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Sucursal</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Módulos</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Nueva contraseña</th>
              <th className="px-4 py-3 text-left text-sm font-semibold" />
            </tr>
          </thead>
          <tbody>
            {profiles.map((row) => (
              <tr key={row.id} className="border-b align-top hover:bg-gray-50">
                <td className="px-4 py-3 font-mono text-xs text-gray-600">{shortId(row.id)}</td>
                <td className="px-4 py-3">
                  <input
                    type="email"
                    value={row.email ?? ''}
                    onChange={(e) => updateDraftProfile(row.id, { email: e.target.value || null })}
                    className="w-full min-w-[220px] rounded border border-gray-300 px-2 py-1 text-sm"
                  />
                </td>
                <td className="px-4 py-3">
                  <input
                    type="text"
                    value={row.nombre ?? ''}
                    onChange={(e) => updateDraftProfile(row.id, { nombre: e.target.value || null })}
                    className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
                  />
                </td>
                <td className="px-4 py-3">
                  <input
                    type="text"
                    value={row.telefono ?? ''}
                    onChange={(e) => updateDraftProfile(row.id, { telefono: e.target.value || null })}
                    className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
                  />
                </td>
                <td className="px-4 py-3">
                  <select
                    value={row.role}
                    onChange={(e) => updateDraftProfile(row.id, { role: e.target.value as Role })}
                    className="w-full rounded border border-gray-300 px-2 py-2 text-sm"
                  >
                    {ROLES.map((role) => (
                      <option key={role} value={role}>{roleLabel(role)}</option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-3">
                  <select
                    value={row.id_sucursal ?? ''}
                    onChange={(e) => updateDraftProfile(row.id, { id_sucursal: e.target.value || null })}
                    disabled={row.role !== 'sucursal'}
                    className="w-full max-w-[220px] rounded border border-gray-300 px-2 py-2 text-sm disabled:cursor-not-allowed disabled:bg-gray-100"
                  >
                    <option value="">-</option>
                    {sucursales.map((s) => (
                      <option key={s.id} value={s.id}>{s.nombre}</option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-3">
                  <div className="max-w-[340px]">
                    <ModuleChecks
                      role={row.role}
                      selected={normalizeModulePermissions(row.role, row.permisos_modulos)}
                      onToggle={(module) => toggleProfileModule(row.id, module)}
                    />
                  </div>
                </td>
                <td className="px-4 py-3">
                  <input
                    type="password"
                    minLength={6}
                    value={passwordDrafts[row.id] || ''}
                    onChange={(e) => setPasswordDrafts((current) => ({ ...current, [row.id]: e.target.value }))}
                    className="w-full min-w-[160px] rounded border border-gray-300 px-2 py-1 text-sm"
                    placeholder="Dejar vacía"
                  />
                </td>
                <td className="px-4 py-3">
                  <Button
                    type="button"
                    size="sm"
                    isLoading={savingProfileId === row.id}
                    onClick={() => saveProfileRow(row)}
                  >
                    Guardar
                  </Button>
                </td>
              </tr>
            ))}
            {profiles.length === 0 && (
              <tr>
                <td colSpan={9} className="px-6 py-8 text-center text-gray-500">
                  Sin usuarios cargados.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

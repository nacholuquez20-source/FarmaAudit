import React, { useState } from 'react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import {
  getAuditores,
  createAuditor,
  updateAuditor,
  listPanelProfiles,
  updatePanelProfile,
} from '../lib/api';
import type { AdminTabKey, Auditor, Role, UserProfile } from '../types';
import { useSucursales } from '../hooks/useSucursales';

const ROLES: Role[] = ['admin', 'auditor', 'sucursal'];

function shortId(id: string): string {
  if (id.length <= 10) return id;
  return `${id.slice(0, 8)}…`;
}

export default function Admin() {
  const [tab, setTab] = useState<AdminTabKey>('auditores');

  const [auditores, setAuditores] = useState<Auditor[]>([]);
  const [profiles, setProfiles] = useState<UserProfile[]>([]);
  const [loadingAuditores, setLoadingAuditores] = useState(true);
  const [loadingUsuarios, setLoadingUsuarios] = useState(true);
  const [error, setError] = useState('');
  const [showAuditorForm, setShowAuditorForm] = useState(false);
  const [formAuditor, setFormAuditor] = useState({ nombre: '', telefono: '', cuadrilla: '', activo: true });
  const [submittingAuditor, setSubmittingAuditor] = useState(false);
  const [savingProfileId, setSavingProfileId] = useState<string | null>(null);

  const { sucursales } = useSucursales();

  React.useEffect(() => {
    const loadAuditores = async () => {
      try {
        setLoadingAuditores(true);
        const data = await getAuditores();
        setAuditores(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error al cargar auditores');
      } finally {
        setLoadingAuditores(false);
      }
    };

    loadAuditores();
  }, []);

  React.useEffect(() => {
    const loadUsuarios = async () => {
      try {
        setLoadingUsuarios(true);
        const data = await listPanelProfiles();
        setProfiles(data);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Error al cargar usuarios del panel';
        if (message.toLowerCase().includes('id_sucursal')) {
          setError(
            'Tu base aún no tiene la columna profiles.id_sucursal. Ejecutá frontend/docs/sql/etapa-4-roles-responsables.sql en Supabase.',
          );
        } else {
          setError(message);
        }
      } finally {
        setLoadingUsuarios(false);
      }
    };

    if (tab === 'usuarios') {
      loadUsuarios();
    }
  }, [tab]);

  const handleAddAuditor = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmittingAuditor(true);
    setError('');

    try {
      const newAuditor = await createAuditor({
        nombre: formAuditor.nombre,
        telefono: formAuditor.telefono,
        cuadrilla: formAuditor.cuadrilla,
        activo: formAuditor.activo,
      });

      setAuditores([...auditores, newAuditor]);
      setFormAuditor({ nombre: '', telefono: '', cuadrilla: '', activo: true });
      setShowAuditorForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al crear auditor');
    } finally {
      setSubmittingAuditor(false);
    }
  };

  const handleToggleAuditorActive = async (telefono: string, currentStatus: boolean) => {
    try {
      const updated = await updateAuditor(telefono, { activo: !currentStatus });
      setAuditores(auditores.map((auditor) => (auditor.telefono === telefono ? updated : auditor)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al actualizar auditor');
    }
  };

  const updateDraftProfile = (id: string, patch: Partial<UserProfile>) => {
    setProfiles(
      profiles.map((row) => {
        if (row.id !== id) return row;
        const next: UserProfile = { ...row, ...patch };
        if (patch.role && patch.role !== 'sucursal') next.id_sucursal = null;
        return next;
      }),
    );
  };

  const saveProfileRow = async (row: UserProfile) => {
    setSavingProfileId(row.id);
    setError('');
    try {
      if (row.role === 'sucursal' && !row.id_sucursal) {
        setError('Asigná una sucursal a los usuarios con rol Responsable.');
        return;
      }
      const saved = await updatePanelProfile(row.id, {
        role: row.role,
        nombre: row.nombre ?? null,
        telefono: row.telefono ?? null,
        id_sucursal: row.id_sucursal ?? null,
      });
      setProfiles(profiles.map((p) => (p.id === saved.id ? saved : p)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al guardar perfil');
    } finally {
      setSavingProfileId(null);
    }
  };

  const loadingPrincipal = tab === 'auditores' ? loadingAuditores : loadingUsuarios;

  return (
    <AppLayout title="Administración">
      {error && (
        <div className="mb-4">
          <FeedbackState title={error} tone="error" />
        </div>
      )}

      <div className="mb-6 inline-flex rounded-lg border border-gray-200 bg-white p-1 shadow-sm">
        <button
          type="button"
          onClick={() => setTab('auditores')}
          className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
            tab === 'auditores' ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'
          }`}
        >
          Auditores (WhatsApp)
        </button>
        <button
          type="button"
          onClick={() => setTab('usuarios')}
          className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
            tab === 'usuarios' ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'
          }`}
        >
          Usuarios del panel
        </button>
      </div>

      {loadingPrincipal ? (
        <FeedbackState title="Cargando..." />
      ) : tab === 'auditores' ? (
        <>
          <div className="mb-6 flex items-center justify-between">
            <h2 className="text-xl font-semibold">Gestión de auditores de campo</h2>
            <button
              type="button"
              onClick={() => setShowAuditorForm(!showAuditorForm)}
              className="rounded-lg bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700"
            >
              {showAuditorForm ? 'Cancelar' : '+ Agregar teléfono auditor'}
            </button>
          </div>

          {showAuditorForm && (
            <form onSubmit={handleAddAuditor} className="mb-6 rounded-lg bg-white p-6 shadow">
              <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-3">
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Nombre</label>
                  <input
                    type="text"
                    value={formAuditor.nombre}
                    onChange={(e) => setFormAuditor({ ...formAuditor, nombre: e.target.value })}
                    required
                    className="w-full rounded-lg border border-gray-300 px-4 py-2 focus:border-transparent focus:ring-2 focus:ring-blue-500"
                    placeholder="Ej: Juan Perez"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Teléfono</label>
                  <input
                    type="text"
                    value={formAuditor.telefono}
                    onChange={(e) => setFormAuditor({ ...formAuditor, telefono: e.target.value })}
                    required
                    className="w-full rounded-lg border border-gray-300 px-4 py-2 focus:border-transparent focus:ring-2 focus:ring-blue-500"
                    placeholder="+549..."
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Cuadrilla</label>
                  <input
                    type="text"
                    value={formAuditor.cuadrilla}
                    onChange={(e) => setFormAuditor({ ...formAuditor, cuadrilla: e.target.value })}
                    required
                    className="w-full rounded-lg border border-gray-300 px-4 py-2 focus:border-transparent focus:ring-2 focus:ring-blue-500"
                    placeholder="Cuadrilla A"
                  />
                </div>
              </div>
              <button
                type="submit"
                disabled={submittingAuditor}
                className="rounded-lg bg-green-600 px-6 py-2 font-medium text-white hover:bg-green-700 disabled:opacity-50"
              >
                {submittingAuditor ? 'Creando...' : 'Crear auditor'}
              </button>
            </form>
          )}

          <div className="overflow-hidden rounded-lg bg-white shadow">
            <table className="w-full">
              <thead className="border-b bg-gray-100">
                <tr>
                  <th className="px-6 py-3 text-left font-semibold">Nombre</th>
                  <th className="px-6 py-3 text-left font-semibold">Teléfono</th>
                  <th className="px-6 py-3 text-left font-semibold">Cuadrilla</th>
                  <th className="px-6 py-3 text-left font-semibold">Estado</th>
                </tr>
              </thead>
              <tbody>
                {auditores.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-6 py-8 text-center text-gray-500">
                      No hay auditores registrados
                    </td>
                  </tr>
                ) : (
                  auditores.map((auditor) => (
                    <tr key={auditor.telefono} className="border-b hover:bg-gray-50">
                      <td className="px-6 py-4 font-medium">{auditor.nombre}</td>
                      <td className="px-6 py-4 text-gray-600">{auditor.telefono}</td>
                      <td className="px-6 py-4 text-gray-600">{auditor.cuadrilla}</td>
                      <td className="px-6 py-4">
                        <button
                          type="button"
                          onClick={() => handleToggleAuditorActive(auditor.telefono, auditor.activo)}
                          className={`rounded px-3 py-1 text-xs font-semibold transition ${
                            auditor.activo
                              ? 'bg-green-100 text-green-800 hover:bg-green-200'
                              : 'bg-red-100 text-red-800 hover:bg-red-200'
                          }`}
                        >
                          {auditor.activo ? 'Activo' : 'Inactivo'}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <>
          <p className="mb-6 text-sm text-gray-600">
            Creá usuarios y contraseñas desde Supabase Auth. Acá definís rol del panel y, para auditores que vean sólo sus
            reportes, el teléfono debe coincidir con el campo <span className="font-mono">auditor</span> en cada reporte. Los
            responsables necesitan rol <strong>sucursal</strong> y la sucursal vinculada.
          </p>

          <div className="overflow-x-auto rounded-lg bg-white shadow">
            <table className="min-w-[960px] w-full">
              <thead className="border-b bg-gray-100">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-semibold">ID</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Nombre / email guardado</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Teléfono panel</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Rol</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Sucursal</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold" />
                </tr>
              </thead>
              <tbody>
                {profiles.map((row) => (
                  <tr key={row.id} className="border-b align-top hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-xs text-gray-600">{shortId(row.id)}</td>
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
                        placeholder="Auditor → coincide con WhatsApp/reporte"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={row.role}
                        onChange={(e) => updateDraftProfile(row.id, { role: e.target.value as Role })}
                        className="w-full rounded border border-gray-300 px-2 py-2 text-sm"
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {r === 'sucursal' ? 'responsable sucursal' : r}
                          </option>
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
                        <option value="">—</option>
                        {sucursales.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.nombre}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        disabled={savingProfileId === row.id}
                        onClick={() => saveProfileRow(row)}
                        className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                      >
                        {savingProfileId === row.id ? 'Guardando…' : 'Guardar'}
                      </button>
                    </td>
                  </tr>
                ))}
                {profiles.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                      Sin perfiles cargados (o política RLS impide verlos como admin).
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </AppLayout>
  );
}

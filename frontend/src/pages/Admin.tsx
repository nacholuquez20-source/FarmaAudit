import React, { useState } from 'react';
import { getAuditores, createAuditor, updateAuditor } from '../lib/api';
import type { Auditor } from '../types';
import { AppLayout } from '../components/AppLayout';

export default function Admin() {
  const [auditores, setAuditores] = useState<Auditor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({ nombre: '', telefono: '', cuadrilla: '', activo: true });
  const [submitting, setSubmitting] = useState(false);

  React.useEffect(() => {
    const loadAuditores = async () => {
      try {
        setLoading(true);
        const data = await getAuditores();
        setAuditores(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load auditors');
      } finally {
        setLoading(false);
      }
    };

    loadAuditores();
  }, []);

  const handleAddAuditor = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');

    try {
      const newAuditor = await createAuditor({
        nombre: formData.nombre,
        telefono: formData.telefono,
        cuadrilla: formData.cuadrilla,
        activo: formData.activo,
      });

      setAuditores([...auditores, newAuditor]);
      setFormData({ nombre: '', telefono: '', cuadrilla: '', activo: true });
      setShowForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add auditor');
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleActive = async (telefono: string, currentStatus: boolean) => {
    try {
      const updated = await updateAuditor(telefono, { activo: !currentStatus });
      setAuditores(auditores.map((a) => (a.telefono === telefono ? updated : a)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update auditor');
    }
  };

  if (loading) return <div className="flex items-center justify-center h-screen">Loading...</div>;

  return (
    <AppLayout title="Admin Panel">
      {error && <div className="bg-red-100 text-red-800 p-4 rounded-lg mb-4">{error}</div>}

      <div className="mb-6 flex justify-between items-center">
        <h2 className="text-xl font-semibold">Gestión de Auditores</h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium"
        >
          {showForm ? 'Cancelar' : '+ Agregar Auditor'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleAddAuditor} className="bg-white rounded-lg p-6 shadow mb-6">
          <div className="grid grid-cols-3 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Nombre</label>
              <input
                type="text"
                value={formData.nombre}
                onChange={(e) => setFormData({ ...formData, nombre: e.target.value })}
                required
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Ej: Juan Pérez"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Teléfono</label>
              <input
                type="text"
                value={formData.telefono}
                onChange={(e) => setFormData({ ...formData, telefono: e.target.value })}
                required
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Ej: +549123456789"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Cuadrilla</label>
              <input
                type="text"
                value={formData.cuadrilla}
                onChange={(e) => setFormData({ ...formData, cuadrilla: e.target.value })}
                required
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Ej: Cuadrilla A"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700 disabled:opacity-50 font-medium"
          >
            {submitting ? 'Creando...' : 'Crear Auditor'}
          </button>
        </form>
      )}

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-100 border-b">
            <tr>
              <th className="text-left px-6 py-3 font-semibold">Nombre</th>
              <th className="text-left px-6 py-3 font-semibold">Teléfono</th>
              <th className="text-left px-6 py-3 font-semibold">Cuadrilla</th>
              <th className="text-left px-6 py-3 font-semibold">Estado</th>
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
                <tr key={auditor.telefono} className="border-b hover:bg-gray-50 transition">
                  <td className="px-6 py-4 font-medium">{auditor.nombre}</td>
                  <td className="px-6 py-4 text-gray-600">{auditor.telefono}</td>
                  <td className="px-6 py-4 text-gray-600">{auditor.cuadrilla}</td>
                  <td className="px-6 py-4">
                    <button
                      onClick={() => handleToggleActive(auditor.telefono, auditor.activo)}
                      className={`px-3 py-1 rounded text-xs font-semibold transition ${
                        auditor.activo ? 'bg-green-100 text-green-800 hover:bg-green-200' : 'bg-red-100 text-red-800 hover:bg-red-200'
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
    </AppLayout>
  );
}

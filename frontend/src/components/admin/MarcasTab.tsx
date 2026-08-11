import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button, FeedbackState, Input } from '../index';
import { createMarca, getMarcas, updateMarca } from '../../lib/api';
import type { Marca } from '../../types';

export function MarcasTab() {
  const [marcas, setMarcas] = useState<Marca[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [nombre, setNombre] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        setMarcas(await getMarcas());
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error al cargar marcas');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleAdd = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!nombre.trim()) {
      setError('El nombre de la marca es obligatorio.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const created = await createMarca(nombre.trim());
      setMarcas((current) => [...current, created].sort((a, b) => a.nombre.localeCompare(b.nombre)));
      setNombre('');
      setShowForm(false);
      toast.success(`Marca ${created.nombre} creada correctamente`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al crear marca');
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleActive = async (marca: Marca) => {
    setTogglingId(marca.id);
    try {
      const updated = await updateMarca(marca.id, { activo: !marca.activo });
      setMarcas((current) => current.map((item) => (item.id === marca.id ? updated : item)));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al actualizar marca');
    } finally {
      setTogglingId(null);
    }
  };

  if (loading) return <FeedbackState title="Cargando marcas..." tone="loading" />;

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Catálogo de marcas</h2>
          <p className="mt-1 text-sm text-gray-600">
            Marcas disponibles para armar campañas (Módulo Campañas). Solo las marcas activas aparecerán en
            el selector del asistente.
          </p>
        </div>
        <Button type="button" onClick={() => setShowForm((current) => !current)}>
          {showForm ? 'Cancelar' : '+ Agregar marca'}
        </Button>
      </div>

      {error && (
        <div className="mb-4">
          <FeedbackState title={error} tone="error" />
        </div>
      )}

      {showForm && (
        <form onSubmit={handleAdd} className="mb-6 max-w-md rounded-lg bg-white p-6 shadow">
          <Input
            label="Nombre de la marca"
            autoFocus
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            required
            placeholder="Ej: Unilever"
          />
          <Button type="submit" variant="success" className="mt-4" isLoading={submitting}>
            Crear marca
          </Button>
        </form>
      )}

      <div className="overflow-hidden rounded-lg bg-white shadow">
        <table className="w-full">
          <thead className="border-b bg-gray-100">
            <tr>
              <th className="px-6 py-3 text-left font-semibold">Marca</th>
              <th className="px-6 py-3 text-left font-semibold">Estado</th>
            </tr>
          </thead>
          <tbody>
            {marcas.length === 0 ? (
              <tr>
                <td colSpan={2} className="px-6 py-8 text-center text-gray-500">
                  No hay marcas cargadas. Agregá la primera para poder armar campañas.
                </td>
              </tr>
            ) : (
              marcas.map((marca) => (
                <tr key={marca.id} className="border-b hover:bg-gray-50">
                  <td className="px-6 py-4 font-medium">{marca.nombre}</td>
                  <td className="px-6 py-4">
                    <button
                      type="button"
                      disabled={togglingId === marca.id}
                      onClick={() => handleToggleActive(marca)}
                      className={`rounded px-3 py-1 text-xs font-semibold transition disabled:opacity-50 ${
                        marca.activo ? 'bg-green-100 text-green-800 hover:bg-green-200' : 'bg-red-100 text-red-800 hover:bg-red-200'
                      }`}
                    >
                      {marca.activo ? 'Activa' : 'Inactiva'}
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

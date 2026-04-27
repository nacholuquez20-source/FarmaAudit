import { useState, useEffect } from 'react';
import { getGestion, updateGestion } from '../lib/api';
import type { Gestion, GestionState } from '../types';

export function useGestion(params?: { sucursal_id?: string; estado?: string }) {
  const [gestiones, setGestiones] = useState<Gestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const sucursalId = params?.sucursal_id;
  const estado = params?.estado;

  useEffect(() => {
    const loadGestion = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await getGestion({ sucursal_id: sucursalId, estado });
        setGestiones(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load gestiones');
      } finally {
        setLoading(false);
      }
    };

    loadGestion();
  }, [sucursalId, estado]);

  const updateStatus = async (id: string, estado: GestionState, cerrado_por?: string) => {
    try {
      const updated = await updateGestion(id, estado, cerrado_por);
      setGestiones(gestiones.map((g) => (g.id_gestion === id ? updated : g)));
      return updated;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update gestion';
      setError(message);
      throw err;
    }
  };

  return { gestiones, loading, error, updateStatus };
}

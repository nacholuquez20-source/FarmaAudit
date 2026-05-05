import { useCallback, useEffect, useMemo, useState } from 'react';
import { approveDesvioBorrador, discardDesvioBorrador, getDesviosBorrador } from '../lib/api';
import type { DesvioBorrador } from '../types';

export function useDesviosBorrador() {
  const [borradores, setBorradores] = useState<DesvioBorrador[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getDesviosBorrador();
      setBorradores(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudieron cargar los borradores.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const pendientes = useMemo(
    () => borradores.filter((borrador) => borrador.estado === 'pendiente'),
    [borradores],
  );

  const aprobar = useCallback(async (id: string) => {
    setBusyId(id);
    try {
      await approveDesvioBorrador(id);
      await load();
    } finally {
      setBusyId(null);
    }
  }, [load]);

  const descartar = useCallback(async (id: string, reason = '') => {
    setBusyId(id);
    try {
      await discardDesvioBorrador(id, reason);
      await load();
    } finally {
      setBusyId(null);
    }
  }, [load]);

  return {
    borradores,
    pendientes,
    loading,
    error,
    busyId,
    reload: load,
    aprobar,
    descartar,
  };
}

import { useCallback, useEffect, useMemo, useState } from 'react';
import { getNotificaciones, marcarNotificacionLeida } from '../lib/api';
import type { Notificacion } from '../types';

const POLLING_MS = 30000;

export function useNotificaciones() {
  const [notificaciones, setNotificaciones] = useState<Notificacion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const data = await getNotificaciones();
      setNotificaciones(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudieron cargar las notificaciones.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    const safeRefresh = async () => {
      if (!cancelled) await refresh();
    };

    void safeRefresh();
    const interval = window.setInterval(() => void safeRefresh(), POLLING_MS);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [refresh]);

  const marcarLeida = async (id: string) => {
    await marcarNotificacionLeida(id);
    setNotificaciones((current) => current.filter((notificacion) => notificacion.id !== id));
  };

  const unreadCount = useMemo(
    () => notificaciones.filter((notificacion) => !notificacion.leida).length,
    [notificaciones],
  );

  return { notificaciones, unreadCount, loading, error, marcarLeida, refresh };
}

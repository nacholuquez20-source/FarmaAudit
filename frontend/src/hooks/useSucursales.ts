import { useState, useEffect, useCallback } from 'react';
import { getSucursales } from '../lib/api';
import type { Sucursal } from '../types';

export function useSucursales() {
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getSucursales();
      setSucursales(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sucursales');
    } finally {
      setLoading(false);
    }
  }, []);

  // La carga inicial no reusa `reload` a proposito: `reload` arranca con
  // setLoading(true), y un setState sincronico dentro de un efecto dispara un
  // render en cascada. Aca el estado ya arranca en loading, asi que el primer
  // statement puede ser el await. `cancelled` evita escribir tras desmontar.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await getSucursales();
        if (!cancelled) setSucursales(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load sucursales');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { sucursales, loading, error, reload };
}

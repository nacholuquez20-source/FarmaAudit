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

  useEffect(() => {
    reload();
  }, [reload]);

  return { sucursales, loading, error, reload };
}

import { useState, useEffect } from 'react';
import { getSucursales } from '../lib/api';
import type { Sucursal } from '../types';

export function useSucursales() {
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadSucursales = async () => {
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
    };

    loadSucursales();
  }, []);

  return { sucursales, loading, error };
}

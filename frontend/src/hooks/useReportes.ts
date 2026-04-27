import { useState, useEffect } from 'react';
import { getReportes } from '../lib/api';
import type { Reporte } from '../types';

export function useReportes(params?: { sucursal_id?: string; auditor?: string }) {
  const [reportes, setReportes] = useState<Reporte[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const sucursalId = params?.sucursal_id;
  const auditor = params?.auditor;

  useEffect(() => {
    const loadReportes = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await getReportes({ sucursal_id: sucursalId, auditor });
        setReportes(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load reportes');
      } finally {
        setLoading(false);
      }
    };

    loadReportes();
  }, [sucursalId, auditor]);

  return { reportes, loading, error };
}

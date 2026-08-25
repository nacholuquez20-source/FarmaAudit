import { useCallback, useEffect, useState } from 'react';
import { getDashboardStats } from '../lib/api';
import type { DashboardStats } from '../types';

export function useDashboardStats(refreshMs = 0, sucursalId?: string | null, periodDays: number | null = null) {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadStats = useCallback(async (background = false) => {
    try {
      if (background) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError(null);
      const data = await getDashboardStats(sucursalId, periodDays);
      setStats(data);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudieron cargar los datos del dashboard.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [sucursalId, periodDays]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      loadStats();
    }, 0);

    return () => window.clearTimeout(timeout);
  }, [loadStats]);

  useEffect(() => {
    if (!refreshMs) return undefined;

    const interval = window.setInterval(() => {
      loadStats(true);
    }, refreshMs);

    return () => window.clearInterval(interval);
  }, [loadStats, refreshMs]);

  return { stats, loading, refreshing, error, lastUpdated, refresh: () => loadStats(true) };
}

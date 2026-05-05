import { useCallback, useEffect, useMemo, useState } from 'react';
import { approveDesvioBorrador, discardDesvioBorrador, getDesviosBorrador } from '../lib/api';
import { supabase } from '../lib/supabase';
import type { DesvioBorrador } from '../types';
import { toast } from 'sonner';

export function useDesviosBorrador() {
  const [borradores, setBorradores] = useState<DesvioBorrador[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

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

  // Supabase realtime subscription
  useEffect(() => {
    const channel = supabase
      .channel('borrador-inserts')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'desvios_borrador',
        },
        (payload) => {
          const newBorrador = payload.new as DesvioBorrador;
          setBorradores((prev) => [newBorrador, ...prev]);
          toast.info('Nuevo borrador detectado por el bot');
        }
      )
      .subscribe();

    return () => {
      void supabase.removeChannel(channel);
    };
  }, []);

  const pendientes = useMemo(
    () => borradores.filter((borrador) => borrador.estado === 'pendiente'),
    [borradores],
  );

  // Optimistic update: aprobar
  const aprobar = useCallback(
    async (id: string) => {
      const snapshot = borradores;
      setBusyId(id);
      setBorradores((prev) =>
        prev.map((b) =>
          b.id === id
            ? { ...b, estado: 'aprobado' as const }
            : b
        )
      );

      try {
        const result = await approveDesvioBorrador(id);
        toast.success('Desvío aprobado', {
          description: result.id_gestion ? 'Pasó a Gestión' : undefined,
          action: result.id_gestion
            ? {
                label: 'Ver',
                onClick: () => {
                  window.open(`/desvios/${result.id_gestion}`, '_blank');
                },
              }
            : undefined,
        });
      } catch (err) {
        setBorradores(snapshot);
        toast.error('No se pudo aprobar el desvío', {
          description: err instanceof Error ? err.message : undefined,
        });
        throw err;
      } finally {
        setBusyId(null);
      }
    },
    [borradores],
  );

  // Optimistic update: descartar
  const descartar = useCallback(
    async (id: string, reason = '') => {
      const snapshot = borradores;
      setBusyId(id);
      setBorradores((prev) =>
        prev.map((b) =>
          b.id === id
            ? { ...b, estado: 'descartado' as const }
            : b
        )
      );

      try {
        await discardDesvioBorrador(id, reason);
        toast.success('Desvío descartado');
      } catch (err) {
        setBorradores(snapshot);
        toast.error('No se pudo descartar el desvío', {
          description: err instanceof Error ? err.message : undefined,
        });
        throw err;
      } finally {
        setBusyId(null);
      }
    },
    [borradores],
  );

  // Batch actions
  const aprobarSeleccionados = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;

    setSelectedIds(new Set());
    const results = await Promise.allSettled(ids.map((id) => aprobar(id)));
    const succeeded = results.filter((r) => r.status === 'fulfilled').length;
    const failed = results.filter((r) => r.status === 'rejected').length;

    if (failed > 0) {
      toast.error(`${succeeded} aprobados, ${failed} fallaron`);
    }
  }, [selectedIds, aprobar]);

  const descartarSeleccionados = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;

    setSelectedIds(new Set());
    const results = await Promise.allSettled(ids.map((id) => descartar(id, 'Descartado desde revision web')));
    const succeeded = results.filter((r) => r.status === 'fulfilled').length;
    const failed = results.filter((r) => r.status === 'rejected').length;

    if (failed > 0) {
      toast.error(`${succeeded} descartados, ${failed} fallaron`);
    }
  }, [selectedIds, descartar]);

  // Selection helpers
  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelectedIds(new Set(pendientes.map((b) => b.id)));
  }, [pendientes]);

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  return {
    borradores,
    pendientes,
    loading,
    error,
    busyId,
    selectedIds,
    reload: load,
    aprobar,
    descartar,
    aprobarSeleccionados,
    descartarSeleccionados,
    toggleSelect,
    selectAll,
    clearSelection,
  };
}

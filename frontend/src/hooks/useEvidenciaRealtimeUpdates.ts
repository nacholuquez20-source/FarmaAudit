import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import type { DesvioEvento } from '../types';

export function useEvidenciaRealtimeUpdates(idGestion: string, initialEventos: DesvioEvento[]) {
  const [eventos, setEventos] = useState<DesvioEvento[]>(initialEventos);

  useEffect(() => {
    setEventos(initialEventos);
  }, [initialEventos]);

  useEffect(() => {
    if (!idGestion) return;

    const subscription = supabase
      .from('desvio_eventos')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'desvio_eventos',
          filter: `id_gestion=eq.${idGestion}`,
        },
        (payload) => {
          const newEvento = payload.new as DesvioEvento;
          if (newEvento.tipo === 'evidencia') {
            setEventos((current) => {
              const exists = current.some((e) => e.id === newEvento.id);
              return exists ? current : [...current, newEvento];
            });
          }
        }
      )
      .subscribe();

    return () => {
      void subscription.unsubscribe();
    };
  }, [idGestion]);

  return eventos;
}

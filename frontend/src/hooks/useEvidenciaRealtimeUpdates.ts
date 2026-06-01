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
      .channel(`desvio_eventos_evidencia_${idGestion}`)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'desvio_eventos',
          filter: `id_gestion=eq.${idGestion}`,
        },
        (payload: { new: DesvioEvento }) => {
          const newEvento = payload.new;
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

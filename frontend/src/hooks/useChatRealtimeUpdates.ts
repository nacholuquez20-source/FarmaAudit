import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import type { DesvioEvento } from '../types';

export function useChatRealtimeUpdates(idGestion: string, initialMensajes: DesvioEvento[]) {
  const [mensajes, setMensajes] = useState<DesvioEvento[]>(initialMensajes);

  useEffect(() => {
    setMensajes(initialMensajes);
  }, [initialMensajes]);

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
          if (newEvento.tipo === 'mensaje') {
            setMensajes((current) => {
              const exists = current.some((m) => m.id === newEvento.id);
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

  return mensajes;
}

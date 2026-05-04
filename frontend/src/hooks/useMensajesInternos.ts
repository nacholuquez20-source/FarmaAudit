import { useMemo, useState } from 'react';
import { crearNotificacionesDesvio, enviarMensajeInterno } from '../lib/api';
import { useAuth } from './useAuth';
import type { DesvioEvento, DesvioOrigen } from '../types';

export function useMensajesInternos(idGestion: string, eventos: DesvioEvento[]) {
  const { user, profile, role } = useAuth();
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const origen: DesvioOrigen = useMemo(() => (role === 'sucursal' ? 'sucursal' : 'auditor'), [role]);

  const mensajes = useMemo(
    () => eventos.filter((evento) => evento.tipo === 'mensaje'),
    [eventos],
  );

  const enviar = async (texto: string): Promise<DesvioEvento> => {
    const comentario = texto.trim();
    if (!comentario) throw new Error('El mensaje no puede estar vacio.');

    setEnviando(true);
    setError(null);

    try {
      const evento = await enviarMensajeInterno({
        idGestion,
        comentario,
        origen,
        actorId: user?.id || '',
        actorNombre: profile?.nombre || user?.email || 'Usuario',
      });

      await crearNotificacionesDesvio({
        idGestion,
        origen,
        tipo: 'mensaje_nuevo',
      });

      return evento;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'No se pudo enviar el mensaje.';
      setError(message);
      throw err;
    } finally {
      setEnviando(false);
    }
  };

  return { mensajes, enviar, enviando, error, origen };
}

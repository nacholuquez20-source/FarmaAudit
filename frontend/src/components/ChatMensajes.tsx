import { useState } from 'react';
import { Send, Loader2 } from 'lucide-react';
import { FeedbackState } from './FeedbackState';
import { useMensajesInternos } from '../hooks/useMensajesInternos';
import { formatDateTime } from '../lib/utils';
import type { DesvioEvento, DesvioOrigen } from '../types';

interface ChatMensajesProps {
  idGestion: string;
  eventos: DesvioEvento[];
  onSent?: (evento: DesvioEvento) => void;
}

function getOrigen(evento: DesvioEvento): DesvioOrigen {
  return evento.metadata?.origen === 'sucursal' ? 'sucursal' : 'auditor';
}

function getInitials(name: string | null | undefined): string {
  if (!name) return '?';
  const parts = name.split(' ');
  return parts.map((p) => p.charAt(0).toUpperCase()).join('').slice(0, 2);
}

function getAvatarColor(origen: DesvioOrigen): string {
  return origen === 'sucursal' ? 'bg-blue-500' : 'bg-green-500';
}

export function ChatMensajes({ idGestion, eventos, onSent }: ChatMensajesProps) {
  const { mensajes, enviar, enviando, error } = useMensajesInternos(idGestion, eventos);
  const [texto, setTexto] = useState('');

  // El evento es opcional porque tambien se dispara con Ctrl+Enter desde el
  // textarea, donde no hay un submit de formulario que cancelar.
  const handleSubmit = async (event?: React.FormEvent) => {
    event?.preventDefault();
    const value = texto.trim();
    if (!value) return;

    const evento = await enviar(value);
    setTexto('');
    onSent?.(evento);
  };

  return (
    <section className="rounded-lg bg-white p-6 shadow">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Mensajes internos</h2>
        <p className="text-sm text-gray-500">Conversacion entre auditoria y sucursal dentro del desvio.</p>
      </div>

      {error && <div className="mb-4"><FeedbackState title={error} tone="warning" /></div>}

      <div className="mb-4 max-h-96 space-y-3 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-4">
        {mensajes.length === 0 ? (
          <div className="py-8 text-center text-sm text-gray-500">Todavia no hay mensajes.</div>
        ) : (
          mensajes.map((mensaje) => {
            const origen = getOrigen(mensaje);
            const fromSucursal = origen === 'sucursal';
            const initials = getInitials(mensaje.actor_nombre);
            const avatarColor = getAvatarColor(origen);

            return (
              <div key={mensaje.id} className={`flex gap-3 ${fromSucursal ? 'flex-row-reverse' : ''}`}>
                <div className={`flex-shrink-0 ${avatarColor} h-8 w-8 rounded-full flex items-center justify-center text-xs font-semibold text-white`}>
                  {initials}
                </div>
                <div className={`flex flex-col ${fromSucursal ? 'items-end' : 'items-start'} flex-1`}>
                  <div className={`flex items-baseline gap-2 text-xs`}>
                    <span className="font-semibold text-gray-900">
                      {mensaje.actor_nombre || (fromSucursal ? 'Sucursal' : 'Auditoria')}
                    </span>
                    <span className="text-gray-500">{formatDateTime(mensaje.created_at)}</span>
                  </div>
                  <div
                    className={`mt-1 max-w-[90%] rounded-lg px-4 py-3 text-sm shadow-sm ${
                      fromSucursal
                        ? 'bg-blue-600 text-white rounded-br-none'
                        : 'bg-white text-gray-800 border border-gray-200 rounded-bl-none'
                    }`}
                  >
                    <div className="whitespace-pre-wrap break-words">{mensaje.comentario}</div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row">
        <textarea
          value={texto}
          onChange={(event) => setTexto(event.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
              e.preventDefault(); // sin esto queda un salto de linea en el textarea
              void handleSubmit();
            }
          }}
          rows={2}
          placeholder="Escribir mensaje... (Ctrl+Enter para enviar)"
          className="min-h-[48px] flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-transparent focus:ring-2 focus:ring-blue-500"
        />
        <button
          type="submit"
          disabled={enviando || !texto.trim()}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-300 disabled:text-gray-600 transition"
        >
          {enviando ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          {enviando ? 'Enviando...' : 'Enviar'}
        </button>
      </form>
    </section>
  );
}

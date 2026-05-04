import { useState } from 'react';
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

export function ChatMensajes({ idGestion, eventos, onSent }: ChatMensajesProps) {
  const { mensajes, enviar, enviando, error } = useMensajesInternos(idGestion, eventos);
  const [texto, setTexto] = useState('');

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
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
            const fromSucursal = getOrigen(mensaje) === 'sucursal';
            return (
              <div key={mensaje.id} className={`flex ${fromSucursal ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[82%] rounded-lg px-4 py-3 text-sm shadow-sm ${fromSucursal ? 'bg-blue-600 text-white' : 'bg-white text-gray-800'}`}>
                  <div className={`mb-1 text-xs font-semibold ${fromSucursal ? 'text-blue-100' : 'text-gray-500'}`}>
                    {mensaje.actor_nombre || (fromSucursal ? 'Sucursal' : 'Auditoria')}
                  </div>
                  <div className="whitespace-pre-wrap break-words">{mensaje.comentario}</div>
                  <div className={`mt-2 text-[11px] ${fromSucursal ? 'text-blue-100' : 'text-gray-400'}`}>
                    {formatDateTime(mensaje.created_at)}
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
          rows={2}
          placeholder="Escribir mensaje..."
          className="min-h-[48px] flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-transparent focus:ring-2 focus:ring-blue-500"
        />
        <button
          type="submit"
          disabled={enviando || !texto.trim()}
          className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-300 disabled:text-gray-600"
        >
          {enviando ? 'Enviando...' : 'Enviar'}
        </button>
      </form>
    </section>
  );
}

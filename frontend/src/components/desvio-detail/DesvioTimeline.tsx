import { FeedbackState } from '../FeedbackState';
import { formatDateTime } from '../../lib/utils';
import type { DesvioEvento } from '../../types';

interface DesvioTimelineProps {
  eventos: DesvioEvento[];
}

export function DesvioTimeline({ eventos }: DesvioTimelineProps) {
  return (
    <section className="rounded-lg bg-white p-6 shadow lg:col-span-2">
      <h2 className="mb-4 text-lg font-semibold text-gray-900">Timeline</h2>
      {eventos.length === 0 ? (
        <FeedbackState title="Sin eventos registrados." />
      ) : (
        <div className="space-y-4">
          {eventos.map((evento) => (
            <div key={evento.id} className="border-l-2 border-blue-200 pl-4">
              <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                <div className="font-medium capitalize text-gray-900">{evento.tipo.replace('_', ' ')}</div>
                <div className="text-xs text-gray-500">{formatDateTime(evento.created_at)}</div>
              </div>
              <p className="mt-1 text-sm text-gray-700">{evento.comentario}</p>
              {evento.actor_nombre && <div className="mt-1 text-xs text-gray-500">Por {evento.actor_nombre}</div>}
              {typeof evento.metadata?.evidencia_url === 'string' && evento.metadata.evidencia_url && (
                <a
                  href={evento.metadata.evidencia_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-block text-sm font-medium text-blue-600 hover:text-blue-800"
                >
                  Abrir evidencia
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

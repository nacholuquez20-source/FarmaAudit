import { FeedbackState } from '../FeedbackState';
import { formatDateTime } from '../../lib/utils';
import { CheckCircle2, AlertCircle, MessageSquare, Image, Phone, Clock } from 'lucide-react';
import type { DesvioEvento } from '../../types';

interface DesvioTimelineProps {
  eventos: DesvioEvento[];
}

function getEventIcon(tipo: string) {
  switch (tipo) {
    case 'creacion':
      return <AlertCircle size={18} />;
    case 'cierre':
      return <CheckCircle2 size={18} />;
    case 'mensaje':
      return <MessageSquare size={18} />;
    case 'evidencia':
      return <Image size={18} />;
    case 'contacto':
      return <Phone size={18} />;
    case 'respuesta':
      return <CheckCircle2 size={18} />;
    case 'verificacion_auditoria':
      return <CheckCircle2 size={18} />;
    case 'reincidencia':
      return <AlertCircle size={18} />;
    case 'nota':
      return <Clock size={18} />;
    default:
      return <AlertCircle size={18} />;
  }
}

function getEventColor(tipo: string): { bg: string; text: string; border: string } {
  switch (tipo) {
    case 'creacion':
      return { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200' };
    case 'cierre':
      return { bg: 'bg-green-50', text: 'text-green-700', border: 'border-green-200' };
    case 'mensaje':
      return { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200' };
    case 'evidencia':
      return { bg: 'bg-purple-50', text: 'text-purple-700', border: 'border-purple-200' };
    case 'contacto':
      return { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200' };
    case 'respuesta':
      return { bg: 'bg-green-50', text: 'text-green-700', border: 'border-green-200' };
    case 'verificacion_auditoria':
      return { bg: 'bg-green-50', text: 'text-green-700', border: 'border-green-200' };
    case 'reincidencia':
      return { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200' };
    case 'nota':
      return { bg: 'bg-gray-50', text: 'text-gray-700', border: 'border-gray-200' };
    default:
      return { bg: 'bg-gray-50', text: 'text-gray-700', border: 'border-gray-200' };
  }
}

export function DesvioTimeline({ eventos }: DesvioTimelineProps) {
  return (
    <section className="rounded-lg bg-white p-6 shadow lg:col-span-2">
      <h2 className="mb-4 text-lg font-semibold text-gray-900">Timeline de eventos</h2>
      {eventos.length === 0 ? (
        <FeedbackState title="Sin eventos registrados." />
      ) : (
        <div className="space-y-3">
          {eventos.map((evento, index) => {
            const colors = getEventColor(evento.tipo);
            const isLast = index === eventos.length - 1;

            return (
              <div key={evento.id} className="relative">
                <div className={`rounded-lg border ${colors.border} ${colors.bg} p-4`}>
                  <div className="flex items-start gap-3">
                    <div className={`flex-shrink-0 mt-0.5 ${colors.text}`}>
                      {getEventIcon(evento.tipo)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
                        <div className={`font-semibold capitalize ${colors.text}`}>
                          {evento.tipo.replace('_', ' ')}
                        </div>
                        <div className="text-xs text-gray-500">{formatDateTime(evento.created_at)}</div>
                      </div>
                      <p className="mt-2 text-sm text-gray-700 break-words">{evento.comentario}</p>
                      <div className="mt-2 flex flex-col gap-1">
                        {evento.actor_nombre && (
                          <div className="text-xs text-gray-600">Por <span className="font-medium">{evento.actor_nombre}</span></div>
                        )}
                        {typeof evento.metadata?.evidencia_url === 'string' && evento.metadata.evidencia_url && (
                          <a
                            href={evento.metadata.evidencia_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-xs font-medium text-blue-600 hover:text-blue-800 hover:underline"
                          >
                            Ver evidencia →
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
                {!isLast && (
                  <div className="ml-3 h-3 border-l border-gray-200" />
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

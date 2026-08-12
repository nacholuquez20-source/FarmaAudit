import { formatDate } from '../../lib/utils';
import { StatusBadge } from '../StatusBadge';
import { SeverityBadge } from '../SeverityBadge';
import type { AuditFicha, Gestion, Reporte } from '../../types';

// El backend históricamente guardó el placeholder literal con corchetes
// ("[Por definir por el responsable]") como plan_accion — se lee como texto
// de plantilla sin completar, no como un mensaje real. Se normaliza acá para
// cubrir tanto los datos viejos como cualquier variante futura.
function planAccionLabel(planAccion: string | null | undefined): string {
  if (!planAccion || planAccion.trim().startsWith('[')) {
    return 'Sin plan de acción definido.';
  }
  return planAccion;
}

interface DesvioInfoCardProps {
  gestion: Gestion;
  reporte: Reporte | null;
  ficha: AuditFicha | null;
  dueState: { label: string; className: string };
  /** Foto que se mandó al bot cuando se detectó este desvío, ya resuelta a
      URL firmada. undefined mientras carga o si no hay foto. */
  reporteFotoUrl?: string;
}

export function DesvioInfoCard({ gestion, reporte, ficha, dueState, reporteFotoUrl }: DesvioInfoCardProps) {
  return (
    <section className="rounded-lg bg-white p-6 shadow lg:col-span-2">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={gestion.severidad} size="sm" />
          <StatusBadge status={gestion.estado} size="sm" />
          {/* Si el estado ya es 'Vencida', el badge de arriba ya lo dice — mostrar
              "Vencido" de nuevo acá es el mismo hecho dos veces con dos
              etiquetas distintas. Solo se agrega cuando aporta algo nuevo
              (En plazo / Cerrado no son valores de gestion.estado). */}
          {gestion.estado !== 'Vencida' && (
            <span className={`text-sm font-semibold ${dueState.className}`}>{dueState.label}</span>
          )}
        </div>
        {reporteFotoUrl && (
          <a href={reporteFotoUrl} target="_blank" rel="noreferrer" className="shrink-0" title="Ver foto completa">
            <img
              src={reporteFotoUrl}
              alt="Foto enviada al bot"
              className="h-20 w-20 rounded-lg object-cover ring-1 ring-gray-200 transition hover:opacity-80"
            />
          </a>
        )}
      </div>

      <h2 className="mb-2 text-xl font-semibold text-gray-900">{gestion.sucursal}</h2>
      <p className="mb-6 text-gray-700">{gestion.desvio}</p>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <div className="text-sm text-gray-500">Área</div>
          <div className="font-medium">{reporte?.area || '-'}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500">Vencimiento</div>
          <div className="font-medium">{formatDate(gestion.plazo_fecha)}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500">Fecha reporte</div>
          <div className="font-medium">{reporte?.fecha ? formatDate(reporte.fecha) : '-'}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500">Auditoría</div>
          <div className="font-medium">
            {ficha ? (
              <a href={`/auditorias?ficha=${ficha.id}`} className="text-primary-navy hover:underline">
                Ver ficha ·{' '}
                {ficha.puntuacion_promedio != null ? `${ficha.puntuacion_promedio.toFixed(1)}/5` : 'sin puntaje'}
              </a>
            ) : (
              <span className="text-gray-400">Auditoría no vinculada</span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-6 border-t border-gray-200 pt-6">
        <h3 className="mb-2 text-sm font-semibold text-gray-900">Plan de acción</h3>
        <p className="text-gray-700">{planAccionLabel(gestion.plan_accion)}</p>
      </div>
    </section>
  );
}

import { formatDate } from '../../lib/utils';
import { StatusBadge } from '../StatusBadge';
import { SeverityBadge } from '../SeverityBadge';
import type { AuditFicha, Gestion, Reporte } from '../../types';

interface DesvioInfoCardProps {
  gestion: Gestion;
  reporte: Reporte | null;
  ficha: AuditFicha | null;
  dueState: { label: string; className: string };
}

export function DesvioInfoCard({ gestion, reporte, ficha, dueState }: DesvioInfoCardProps) {
  return (
    <section className="rounded-lg bg-white p-6 shadow lg:col-span-2">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <SeverityBadge severity={gestion.severidad} size="sm" />
        <StatusBadge status={gestion.estado} size="sm" />
        <span className={`text-sm font-semibold ${dueState.className}`}>{dueState.label}</span>
      </div>

      <h2 className="mb-2 text-xl font-semibold text-gray-900">{gestion.sucursal}</h2>
      <p className="mb-6 text-gray-700">{gestion.desvio}</p>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <div className="text-sm text-gray-500">Area</div>
          <div className="font-medium">{reporte?.area || '-'}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500">Vencimiento</div>
          <div className="font-medium">{formatDate(gestion.plazo_fecha)}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500">Reporte origen</div>
          <div className="font-medium">{gestion.id_reporte || '-'}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500">Fecha reporte</div>
          <div className="font-medium">{reporte?.fecha ? formatDate(reporte.fecha) : '-'}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500">Auditoria</div>
          <div className="font-medium">
            {ficha ? (
              <a href={`/auditorias?ficha=${ficha.id}`} className="text-primary-navy hover:underline">
                Ver ficha ·{' '}
                {ficha.puntuacion_promedio != null ? `${ficha.puntuacion_promedio.toFixed(1)}/5` : 'sin puntaje'}
              </a>
            ) : (
              <span className="text-gray-400">Auditoria no vinculada</span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-6 border-t border-gray-200 pt-6">
        <h3 className="mb-2 text-sm font-semibold text-gray-900">Plan de accion</h3>
        <p className="text-gray-700">{gestion.plan_accion || 'Sin plan de accion registrado.'}</p>
      </div>
    </section>
  );
}

import { formatDate, gestionStateColor, gestionStateLabel, severidadColor } from '../../lib/utils';
import type { Gestion, Reporte } from '../../types';

interface DesvioInfoCardProps {
  gestion: Gestion;
  reporte: Reporte | null;
  dueState: { label: string; className: string };
}

export function DesvioInfoCard({ gestion, reporte, dueState }: DesvioInfoCardProps) {
  return (
    <section className="rounded-lg bg-white p-6 shadow lg:col-span-2">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className={`rounded px-3 py-1 text-xs font-semibold ${severidadColor(gestion.severidad)}`}>
          {gestion.severidad}
        </span>
        <span className={`rounded px-3 py-1 text-xs font-semibold ${gestionStateColor(gestion.estado)}`}>
          {gestionStateLabel(gestion.estado)}
        </span>
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
      </div>

      <div className="mt-6 border-t border-gray-200 pt-6">
        <h3 className="mb-2 text-sm font-semibold text-gray-900">Plan de accion</h3>
        <p className="text-gray-700">{gestion.plan_accion || 'Sin plan de accion registrado.'}</p>
      </div>
    </section>
  );
}

import { formatDate } from '../../lib/utils';
import type { Gestion } from '../../types';

interface DesvioResponsibleCardProps {
  gestion: Gestion;
}

export function DesvioResponsibleCard({ gestion }: DesvioResponsibleCardProps) {
  return (
    <aside className="rounded-lg bg-white p-6 shadow">
      <h2 className="mb-4 text-lg font-semibold text-gray-900">Responsable</h2>
      <div className="space-y-4">
        <div>
          <div className="text-sm text-gray-500">Nombre</div>
          <div className="font-medium">{gestion.responsable || '-'}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500">Telefono</div>
          <div className="font-medium">{gestion.tel_responsable || 'Sin telefono'}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500">Cierre</div>
          <div className="font-medium">{gestion.fecha_cierre ? formatDate(gestion.fecha_cierre) : 'Pendiente'}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500">Cerrado por</div>
          <div className="font-medium">{gestion.cerrado_por || '-'}</div>
        </div>
      </div>
    </aside>
  );
}

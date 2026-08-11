import { formatDate } from '../../lib/utils';
import type { Gestion, ResponsableActivo } from '../../types';

interface DesvioResponsibleCardProps {
  gestion: Gestion;
  responsableActivo: ResponsableActivo | null;
}

export function DesvioResponsibleCard({ gestion, responsableActivo }: DesvioResponsibleCardProps) {
  return (
    <aside className="rounded-lg bg-white p-6 shadow">
      <h2 className="mb-4 text-lg font-semibold text-gray-900">Responsable</h2>
      <div className="space-y-4">
        {responsableActivo?.responsable ? (
          <>
            <div>
              <div className="text-sm text-gray-500">Nombre</div>
              <div className="font-medium">{responsableActivo.responsable.nombre}</div>
            </div>
            <div>
              <div className="text-sm text-gray-500">Telefono</div>
              <div className="font-medium">{responsableActivo.responsable.telefono}</div>
              <div className="mt-1 text-xs text-gray-500">
                Ventana WhatsApp: {responsableActivo.ventana_abierta ? 'abierta' : 'cerrada'}
              </div>
            </div>
          </>
        ) : (
          <div>
            <div className="text-sm text-gray-500">Responsable</div>
            <div className="text-gray-400">
              Sin responsable activo.{' '}
              <a href="/admin?tab=whatsapp" className="text-primary-navy hover:underline">
                Ver Administración → Usuarios WhatsApp
              </a>
              .
            </div>
          </div>
        )}
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

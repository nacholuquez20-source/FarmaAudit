import { Link, useNavigate } from 'react-router-dom';
import type { Gestion, Role } from '../../types';

interface DesvioHeaderActionsProps {
  role: Role | null;
  gestion: Gestion;
  whatsappUrl: string | null;
  contacting: boolean;
  notifying: boolean;
  onBack: (path: string) => void;
  onContact: () => void;
  onNotify: () => void;
}

export function DesvioHeaderActions({
  role,
  gestion,
  whatsappUrl,
  contacting,
  notifying,
  onBack,
  onContact,
  onNotify,
}: DesvioHeaderActionsProps) {
  const navigate = useNavigate();
  const backPath = role === 'sucursal' ? '/mis-desvios' : '/gestion-desvios';
  const canManageEstado = role === 'admin' || role === 'auditor';

  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <button
        type="button"
        onClick={() => navigate(backPath)}
        className="self-start text-sm font-medium text-blue-600 hover:text-blue-800"
      >
        {role === 'sucursal' ? 'Volver a mis desvios' : 'Volver a gestion'}
      </button>
      <div className="flex gap-2">
        {canManageEstado && (
          <>
            <Link
              to={`/sucursales/${gestion.id_sucursal}`}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
            >
              Ver sucursal
            </Link>
            <button
              type="button"
              onClick={onNotify}
              disabled={!gestion.tel_responsable || notifying || gestion.estado === 'Cerrada'}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-300 disabled:text-gray-600"
            >
              {notifying ? 'Notificando...' : 'Notificar encargado'}
            </button>
            <button
              type="button"
              onClick={onContact}
              disabled={!whatsappUrl || contacting}
              className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:bg-gray-300 disabled:text-gray-600"
            >
              {contacting ? 'Contactando...' : 'Contactar responsable'}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

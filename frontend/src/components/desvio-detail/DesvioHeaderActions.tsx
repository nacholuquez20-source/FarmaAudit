import type { ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { Gestion, Role } from '../../types';

interface DesvioHeaderActionsProps {
  role: Role | null;
  gestion: Gestion;
  /** El botón de recordatorio (ReminderButton) se arma en DesvioDetail, que
   * ya tiene el estado de contacto resuelto — este componente solo lo aloja. */
  reminderSlot?: ReactNode;
}

export function DesvioHeaderActions({ role, gestion, reminderSlot }: DesvioHeaderActionsProps) {
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
      {canManageEstado && (
        <div className="flex items-center gap-3">
          <Link
            to={`/sucursales/${gestion.id_sucursal}`}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
          >
            Ver sucursal
          </Link>
          {reminderSlot}
        </div>
      )}
    </div>
  );
}

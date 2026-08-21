import { Link } from 'react-router-dom';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { useAuth } from '../hooks/useAuth';
import { useGestion } from '../hooks/useGestion';
import { formatDate, gestionStateColor, gestionStateLabel, severidadColor } from '../lib/utils';

export default function MisDesvios() {
  const { profile } = useAuth();
  const sucursalId = profile?.id_sucursal ?? null;
  const { gestiones, loading, error } = useGestion(sucursalId ? { sucursal_id: sucursalId } : undefined);

  const activos = gestiones.filter((gestion) => gestion.estado === 'Abierta' || gestion.estado === 'En_proceso' || gestion.estado === 'Vencida');

  if (!sucursalId) {
    return (
      <AppLayout title="Mis pendientes">
        <FeedbackState
          title="Tu usuario no tiene una sucursal asignada."
          description="Asigna id_sucursal al perfil desde Admin o ejecuta la migracion de roles y responsables en Supabase."
          tone="warning"
        />
      </AppLayout>
    );
  }

  return (
    <AppLayout title="Mis Desvios">
      <div className="mb-6">
        <p className="text-sm text-gray-600">{activos.length} desvios activos para responder desde la app.</p>
      </div>

      {loading && <FeedbackState title="Cargando desvíos..." tone="loading" />}
      {error && <FeedbackState title={error} tone="error" />}

      {!loading && !error && activos.length === 0 && (
        <FeedbackState title="No hay desvios activos para tu sucursal." />
      )}

      {!loading && !error && activos.length > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {activos.map((gestion) => (
            <Link
              key={gestion.id_gestion}
              to={`/mis-desvios/${gestion.id_gestion}`}
              className="rounded-lg bg-white p-5 shadow transition hover:-translate-y-0.5 hover:shadow-md"
            >
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className={`rounded px-3 py-1 text-xs font-semibold ${severidadColor(gestion.severidad)}`}>
                  {gestion.severidad}
                </span>
                <span className={`rounded px-3 py-1 text-xs font-semibold ${gestionStateColor(gestion.estado)}`}>
                  {gestionStateLabel(gestion.estado)}
                </span>
              </div>
              <h2 className="mb-2 text-lg font-semibold text-gray-900">{gestion.sucursal}</h2>
              <p className="line-clamp-3 text-sm text-gray-700">{gestion.desvio}</p>
              <div className="mt-4 grid grid-cols-1 gap-3 text-sm text-gray-600 sm:grid-cols-2">
                <div>
                  <div className="text-xs uppercase text-gray-400">Responsable</div>
                  <div className="font-medium text-gray-800">{gestion.responsable || '-'}</div>
                </div>
                <div>
                  <div className="text-xs uppercase text-gray-400">Vencimiento</div>
                  <div className="font-medium text-gray-800">{formatDate(gestion.plazo_fecha)}</div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </AppLayout>
  );
}

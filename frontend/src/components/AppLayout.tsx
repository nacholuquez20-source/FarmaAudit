import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth, logout } from '../hooks/useAuth';
import { useNotificaciones } from '../hooks/useNotificaciones';

interface AppLayoutProps {
  children: React.ReactNode;
  title: string;
  showAdmin?: boolean;
}

export function AppLayout({ children, title, showAdmin = true }: AppLayoutProps) {
  const { user, role, profile } = useAuth();
  const navigate = useNavigate();
  const { notificaciones, unreadCount, marcarLeida } = useNotificaciones();
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  const handleLogout = async () => {
    try {
      await logout();
      navigate('/login');
    } catch (err) {
      console.error('Logout failed:', err);
    }
  };

  const handleNotificationClick = async (id: string, idGestion: string) => {
    await marcarLeida(id);
    setNotificationsOpen(false);
    navigate(role === 'sucursal' ? `/mis-desvios/${idGestion}` : `/desvios/${idGestion}`);
  };

  const canAccessAdmin = showAdmin && role === 'admin';

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="border-b border-gray-200 bg-white shadow-sm">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <h1 className="text-2xl font-bold text-gray-900">{title}</h1>

            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:gap-6">
              <nav className="flex flex-wrap gap-4 text-sm">
                {role === 'admin' && (
                  <>
                    <Link to="/dashboard" className="text-gray-600 hover:text-gray-900 hover:underline">
                      Dashboard
                    </Link>
                    <Link to="/desvios" className="text-gray-600 hover:text-gray-900 hover:underline">
                      Desvios
                    </Link>
                    <Link to="/revision-desvios" className="text-gray-600 hover:text-gray-900 hover:underline">
                      Revision
                    </Link>
                    <Link to="/sucursales" className="text-gray-600 hover:text-gray-900 hover:underline">
                      Sucursales
                    </Link>
                    {canAccessAdmin && (
                      <Link to="/admin" className="text-gray-600 hover:text-gray-900 hover:underline">
                        Admin
                      </Link>
                    )}
                  </>
                )}
                {role === 'auditor' && (
                  <>
                    <Link to="/desvios" className="text-gray-600 hover:text-gray-900 hover:underline">
                      Desvios
                    </Link>
                    <Link to="/revision-desvios" className="text-gray-600 hover:text-gray-900 hover:underline">
                      Revision
                    </Link>
                    <Link to="/sucursales" className="text-gray-600 hover:text-gray-900 hover:underline">
                      Sucursales
                    </Link>
                  </>
                )}
                {role === 'sucursal' && (
                  <>
                    <Link to="/dashboard" className="text-gray-600 hover:text-gray-900 hover:underline">
                      Resumen
                    </Link>
                    <Link to="/mis-desvios" className="text-gray-600 hover:text-gray-900 hover:underline">
                      Desvios
                    </Link>
                    <Link
                      to={profile?.id_sucursal ? `/sucursales/${profile.id_sucursal}` : '/sucursales'}
                      className="text-gray-600 hover:text-gray-900 hover:underline"
                    >
                      Mi sucursal
                    </Link>
                  </>
                )}
              </nav>

              <div className="flex flex-wrap items-center gap-4">
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setNotificationsOpen((current) => !current)}
                    className="relative rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
                    aria-label="Notificaciones"
                  >
                    Notificaciones
                    {unreadCount > 0 && (
                      <span className="absolute -right-2 -top-2 min-w-5 rounded-full bg-red-600 px-1.5 py-0.5 text-xs font-bold text-white">
                        {unreadCount}
                      </span>
                    )}
                  </button>

                  {notificationsOpen && (
                    <div className="absolute right-0 z-20 mt-2 w-80 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-lg">
                      <div className="border-b border-gray-200 px-4 py-3 text-sm font-semibold text-gray-900">
                        Notificaciones
                      </div>
                      {notificaciones.length === 0 ? (
                        <div className="px-4 py-6 text-center text-sm text-gray-500">No hay pendientes.</div>
                      ) : (
                        <div className="max-h-80 overflow-y-auto">
                          {notificaciones.slice(0, 8).map((notificacion) => (
                            <button
                              key={notificacion.id}
                              type="button"
                              onClick={() => void handleNotificationClick(notificacion.id, notificacion.id_gestion)}
                              className="block w-full border-b border-gray-100 px-4 py-3 text-left text-sm hover:bg-gray-50"
                            >
                              <div className="font-medium text-gray-900">
                                {notificacion.tipo === 'mensaje_nuevo' || notificacion.tipo === 'encargado_respondio'
                                  ? 'Nueva actividad en desvio'
                                  : 'Notificacion de desvio'}
                              </div>
                              <div className="text-xs text-gray-500">{notificacion.id_gestion}</div>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <span className="text-sm text-gray-600 lg:border-l lg:border-gray-200 lg:pl-6">{user?.email}</span>
                <button onClick={handleLogout} className="text-sm font-medium text-red-600 hover:text-red-800">
                  Logout
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">{children}</div>
    </div>
  );
}

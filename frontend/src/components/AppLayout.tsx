import { Link, useNavigate } from 'react-router-dom';
import { useAuth, logout } from '../hooks/useAuth';

interface AppLayoutProps {
  children: React.ReactNode;
  title: string;
  showAdmin?: boolean;
}

export function AppLayout({ children, title, showAdmin = true }: AppLayoutProps) {
  const { user, role, profile } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await logout();
      navigate('/login');
    } catch (err) {
      console.error('Logout failed:', err);
    }
  };

  const canAccessAdmin = showAdmin && role === 'admin';

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-6">
              <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
            </div>
            <div className="flex items-center gap-6">
              <nav className="flex gap-4 text-sm">
                {role === 'admin' && (
                  <>
                    <Link to="/dashboard" className="text-gray-600 hover:text-gray-900 hover:underline">
                      Dashboard
                    </Link>
                    <Link to="/desvios" className="text-gray-600 hover:text-gray-900 hover:underline">
                      Desvíos
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
                      Desvíos
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
                    <Link to="/desvios" className="text-gray-600 hover:text-gray-900 hover:underline">
                      Desvíos
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
              <span className="text-sm text-gray-600 border-l border-gray-200 pl-6">{user?.email}</span>
              <button
                onClick={handleLogout}
                className="text-sm text-red-600 hover:text-red-800 font-medium"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">{children}</div>
    </div>
  );
}

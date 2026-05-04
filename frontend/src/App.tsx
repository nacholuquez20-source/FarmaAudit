import { lazy, Suspense, useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import { FeedbackState } from './components/FeedbackState';
import type { Role } from './types';

const Login = lazy(() => import('./pages/Login'));
const ResetPassword = lazy(() => import('./pages/ResetPassword'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Desvios = lazy(() => import('./pages/Desvios'));
const DesvioDetail = lazy(() => import('./pages/DesvioDetail'));
const Sucursales = lazy(() => import('./pages/Sucursales'));
const SucursalDetail = lazy(() => import('./pages/SucursalDetail'));
const Admin = lazy(() => import('./pages/Admin'));

function ProtectedRoute({
  children,
  adminOnly = false,
  allowRoles,
}: {
  children: React.ReactNode;
  adminOnly?: boolean;
  /** Si se define, solo estos roles pueden ver la ruta (p. ej. dashboard para admin/sucursal). */
  allowRoles?: Role[];
}) {
  const { user, role, loading } = useAuth();
  const [showLoadingError, setShowLoadingError] = useState(false);

  useEffect(() => {
    if (loading) {
      const timer = setTimeout(() => setShowLoadingError(true), 2000);
      return () => clearTimeout(timer);
    }
  }, [loading]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="text-center max-w-md">
          <FeedbackState title="Verificando sesión..." />
          {showLoadingError && (
            <div className="mt-4 space-y-3">
              <div className="text-sm text-gray-600">
                <p className="mb-2">Esto está tomando más de lo esperado.</p>
                <p className="text-xs text-gray-500 bg-gray-100 p-2 rounded mb-2">
                  💡 Verifica que las variables de entorno <code>VITE_SUPABASE_URL</code> y <code>VITE_SUPABASE_ANON_KEY</code> estén configuradas en Vercel Settings.
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => window.location.reload()}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
                >
                  Refrescar
                </button>
                <button
                  onClick={() => window.location.href = '/login'}
                  className="flex-1 px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400 text-sm"
                >
                  Ir a Login
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (adminOnly && role !== 'admin') {
    if (role === 'auditor') return <Navigate to="/desvios" replace />;
    if (role === 'sucursal') return <Navigate to="/dashboard" replace />;
    return <Navigate to="/dashboard" replace />;
  }

  if (allowRoles?.length && role && !allowRoles.includes(role)) {
    if (role === 'auditor') return <Navigate to="/desvios" replace />;
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<div className="min-h-screen bg-gray-50 p-8"><FeedbackState title="Cargando vista..." /></div>}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/reset-password" element={<ResetPassword />} />

          <Route
            path="/dashboard"
            element={
              <ProtectedRoute allowRoles={['admin', 'sucursal']}>
                <Dashboard />
              </ProtectedRoute>
            }
          />

          <Route
            path="/desvios"
            element={
              <ProtectedRoute>
                <Desvios />
              </ProtectedRoute>
            }
          />

          <Route
            path="/desvios/:id"
            element={
              <ProtectedRoute>
                <DesvioDetail />
              </ProtectedRoute>
            }
          />

          <Route
            path="/sucursales"
            element={
              <ProtectedRoute>
                <Sucursales />
              </ProtectedRoute>
            }
          />

          <Route
            path="/sucursales/:id"
            element={
              <ProtectedRoute>
                <SucursalDetail />
              </ProtectedRoute>
            }
          />

          <Route
            path="/admin"
            element={
              <ProtectedRoute adminOnly>
                <Admin />
              </ProtectedRoute>
            }
          />

          <Route path="/" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

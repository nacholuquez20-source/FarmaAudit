import { lazy, Suspense, useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { FeedbackState } from './components/FeedbackState';
import { useAuth } from './hooks/useAuth';
import type { Role } from './types';

const Login = lazy(() => import('./pages/Login'));
const ResetPassword = lazy(() => import('./pages/ResetPassword'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Desvios = lazy(() => import('./pages/Desvios'));
const DesvioDetail = lazy(() => import('./pages/DesvioDetail'));
const Sucursales = lazy(() => import('./pages/Sucursales'));
const SucursalDetail = lazy(() => import('./pages/SucursalDetail'));
const Admin = lazy(() => import('./pages/Admin'));

function LoadingGate({ title }: { title: string }) {
  const [showRetry, setShowRetry] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setShowRetry(true), 2000);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="flex h-screen items-center justify-center bg-gray-50">
      <div className="max-w-md text-center">
        <FeedbackState title={title} />
        {showRetry && (
          <div className="mt-4 space-y-3">
            <p className="text-sm text-gray-600">Esto esta tomando mas de lo esperado.</p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
              >
                Refrescar
              </button>
              <button
                type="button"
                onClick={() => {
                  window.localStorage.removeItem('farma-audit-auth');
                  window.location.href = '/login';
                }}
                className="flex-1 rounded-lg bg-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-400"
              >
                Ir a login
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ProfileError({ message }: { message: string | null }) {
  return (
    <div className="flex h-screen items-center justify-center bg-gray-50">
      <div className="max-w-md text-center">
        <FeedbackState
          title="No se pudo cargar tu perfil."
          description={message || 'Tu usuario no tiene un perfil asociado en Supabase.'}
          tone="error"
        />
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
          >
            Reintentar
          </button>
          <button
            type="button"
            onClick={() => {
              window.localStorage.removeItem('farma-audit-auth');
              window.location.href = '/login';
            }}
            className="flex-1 rounded-lg bg-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-400"
          >
            Volver al login
          </button>
        </div>
      </div>
    </div>
  );
}

function ProtectedRoute({
  children,
  adminOnly = false,
  allowRoles,
}: {
  children: React.ReactNode;
  adminOnly?: boolean;
  allowRoles?: Role[];
}) {
  const { user, role, loading, profileLoading, profileError } = useAuth();

  if (loading) return <LoadingGate title="Verificando sesion..." />;
  if (!user) return <Navigate to="/login" replace />;
  if (profileLoading) return <LoadingGate title="Cargando perfil..." />;
  if (!role) return <ProfileError message={profileError} />;

  if (adminOnly && role !== 'admin') {
    if (role === 'auditor') return <Navigate to="/desvios" replace />;
    if (role === 'sucursal') return <Navigate to="/dashboard" replace />;
    return <Navigate to="/dashboard" replace />;
  }

  if (allowRoles?.length && !allowRoles.includes(role)) {
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

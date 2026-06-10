import { lazy, Suspense, useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { FeedbackState } from './components/FeedbackState';
import { useAuth } from './hooks/useAuth';
import { firstAllowedPath, hasModuleAccess } from './lib/permissions';
import type { ModulePermission, Role } from './types';

const Login = lazy(() => import('./pages/Login'));
const ResetPassword = lazy(() => import('./pages/ResetPassword'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const DesvioDetail = lazy(() => import('./pages/DesvioDetail'));
const DesviosGestion = lazy(() => import('./pages/DesviosGestion'));
const RevisionDesvios = lazy(() => import('./pages/RevisionDesvios'));
const MisDesvios = lazy(() => import('./pages/MisDesvios'));
const Sucursales = lazy(() => import('./pages/Sucursales'));
const SucursalDetail = lazy(() => import('./pages/SucursalDetail'));
const AuditPerfumeria = lazy(() => import('./pages/AuditPerfumeria'));
const AuditFichesGallery = lazy(() => import('./pages/AuditFichesGallery'));
const Admin = lazy(() => import('./pages/Admin'));

function LoadingGate({ title }: { title: string }) {
  const [showRetry, setShowRetry] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(() => setShowRetry(true), 3000);
    return () => window.clearTimeout(timer);
  }, []);

  const handleRetry = () => {
    setShowRetry(false);
    setRetryCount(prev => prev + 1);
    window.location.reload();
  };

  return (
    <div className="flex h-screen items-center justify-center bg-gray-50">
      <div className="max-w-md text-center">
        <FeedbackState title={title} />
        {showRetry && (
          <div className="mt-4 space-y-3">
            <p className="text-sm text-gray-600">
              {retryCount === 0
                ? 'Esto esta tomando mas de lo esperado.'
                : 'Aun cargando... verifica tu conexion.'}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleRetry}
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
  module,
}: {
  children: React.ReactNode;
  adminOnly?: boolean;
  allowRoles?: Role[];
  module?: ModulePermission;
}) {
  const { user, role, profile, loading, profileLoading, profileError } = useAuth();

  if (loading) return <LoadingGate title="Verificando sesion..." />;
  if (!user) return <Navigate to="/login" replace />;
  if (profileLoading) return <LoadingGate title="Cargando perfil..." />;
  if (!role) return <ProfileError message={profileError} />;

  if (adminOnly && role !== 'admin') {
    if (role === 'auditor') return <Navigate to="/gestion-desvios" replace />;
    if (role === 'sucursal') return <Navigate to="/dashboard" replace />;
    return <Navigate to="/dashboard" replace />;
  }

  if (allowRoles?.length && !allowRoles.includes(role)) {
    if (role === 'auditor') return <Navigate to="/gestion-desvios" replace />;
    return <Navigate to="/dashboard" replace />;
  }

  if (module && !hasModuleAccess(profile, module)) {
    return <Navigate to={firstAllowedPath(profile)} replace />;
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
              <ProtectedRoute allowRoles={['admin', 'sucursal']} module="dashboard">
                <Dashboard />
              </ProtectedRoute>
            }
          />

          <Route
            path="/desvios"
            element={<Navigate to="/gestion-desvios" replace />}
          />

          <Route
            path="/desvios/:id"
            element={
              <ProtectedRoute allowRoles={['admin', 'auditor']} module="gestion_desvios">
                <DesvioDetail />
              </ProtectedRoute>
            }
          />

          <Route
            path="/gestion-desvios"
            element={
              <ProtectedRoute allowRoles={['admin', 'auditor']} module="gestion_desvios">
                <DesviosGestion />
              </ProtectedRoute>
            }
          />

          <Route
            path="/revision-desvios"
            element={
              <ProtectedRoute allowRoles={['admin', 'auditor']} module="revision_desvios">
                <RevisionDesvios />
              </ProtectedRoute>
            }
          />

          <Route
            path="/mis-desvios"
            element={
              <ProtectedRoute allowRoles={['sucursal']} module="mis_desvios">
                <MisDesvios />
              </ProtectedRoute>
            }
          />

          <Route
            path="/mis-desvios/:id"
            element={
              <ProtectedRoute allowRoles={['sucursal']} module="mis_desvios">
                <DesvioDetail />
              </ProtectedRoute>
            }
          />

          <Route
            path="/sucursales"
            element={
              <ProtectedRoute module="sucursales">
                <Sucursales />
              </ProtectedRoute>
            }
          />

          <Route
            path="/sucursales/:id"
            element={
              <ProtectedRoute module="sucursales">
                <SucursalDetail />
              </ProtectedRoute>
            }
          />

          <Route
            path="/sucursales/:id/auditoria"
            element={
              <ProtectedRoute allowRoles={['auditor', 'admin']}>
                <AuditPerfumeria />
              </ProtectedRoute>
            }
          />

          <Route
            path="/fichas"
            element={
              <ProtectedRoute allowRoles={['admin', 'auditor']}>
                <AuditFichesGallery />
              </ProtectedRoute>
            }
          />

          <Route
            path="/admin"
            element={
              <ProtectedRoute adminOnly module="admin">
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

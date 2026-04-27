import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import { FeedbackState } from './components/FeedbackState';

const Login = lazy(() => import('./pages/Login'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Desvios = lazy(() => import('./pages/Desvios'));
const DesvioDetail = lazy(() => import('./pages/DesvioDetail'));
const Sucursales = lazy(() => import('./pages/Sucursales'));
const SucursalDetail = lazy(() => import('./pages/SucursalDetail'));
const Admin = lazy(() => import('./pages/Admin'));

function ProtectedRoute({ children, adminOnly = false }: { children: React.ReactNode; adminOnly?: boolean }) {
  const { user, role, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <FeedbackState title="Cargando sesion..." />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (adminOnly && role !== 'admin') {
    return <Navigate to="/sucursales" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<div className="min-h-screen bg-gray-50 p-8"><FeedbackState title="Cargando vista..." /></div>}>
        <Routes>
          <Route path="/login" element={<Login />} />

          <Route
            path="/dashboard"
            element={
              <ProtectedRoute adminOnly>
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

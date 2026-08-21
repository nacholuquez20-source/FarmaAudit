import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import {
  AlertTriangle,
  Bell,
  ClipboardCheck,
  Home,
  LogOut,
  Megaphone,
  Settings,
  Store,
  Sun,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useAuth, logout } from '../hooks/useAuth';
import { useNotificaciones } from '../hooks/useNotificaciones';
import { hasModuleAccess } from '../lib/permissions';

interface AppLayoutProps {
  children: React.ReactNode;
  title: string;
  showAdmin?: boolean;
  contentClassName?: string;
}

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

export function AppLayout({ children, title, showAdmin = true, contentClassName }: AppLayoutProps) {
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

  const canAccessAdmin = showAdmin && role === 'admin' && hasModuleAccess(profile, 'admin');

  const navItems: NavItem[] = [];
  if (role === 'admin') {
    navItems.push({ to: '/hoy', label: 'Hoy', icon: Sun });
    if (hasModuleAccess(profile, 'campanias'))
      navItems.push({ to: '/campanias', label: 'Campanias', icon: Megaphone });
    if (hasModuleAccess(profile, 'sucursales'))
      navItems.push({ to: '/sucursales', label: 'Sucursales', icon: Store });
    if (canAccessAdmin) navItems.push({ to: '/admin', label: 'Gestión', icon: Settings });
  } else if (role === 'auditor') {
    navItems.push({ to: '/hoy', label: 'Hoy', icon: Sun });
    if (hasModuleAccess(profile, 'campanias'))
      navItems.push({ to: '/campanias', label: 'Campanias', icon: Megaphone });
    if (hasModuleAccess(profile, 'sucursales'))
      navItems.push({ to: '/sucursales', label: 'Sucursales', icon: Store });
  } else if (role === 'sucursal') {
    if (hasModuleAccess(profile, 'dashboard'))
      navItems.push({ to: '/dashboard', label: 'Resumen', icon: Home });
    if (hasModuleAccess(profile, 'mis_desvios'))
      navItems.push({ to: '/mis-desvios', label: 'Mis pendientes', icon: AlertTriangle });
    if (hasModuleAccess(profile, 'mis_campanias'))
      navItems.push({ to: '/mis-campanias', label: 'Campanias', icon: Megaphone });
    if (hasModuleAccess(profile, 'sucursales'))
      navItems.push({
        to: profile?.id_sucursal ? `/sucursales/${profile.id_sucursal}` : '/sucursales',
        label: 'Mi sucursal',
        icon: Store,
      });
  }

  const navLinkClasses = ({ isActive }: { isActive: boolean }) =>
    `flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
      isActive
        ? 'bg-primary-navy/10 text-primary-navy'
        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
    }`;

  const userInitial = (user?.email || '?').charAt(0).toUpperCase();

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="relative z-30 border-b border-gray-200 bg-white shadow-sm">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between gap-4">
            {/* Brand */}
            <NavLink to="/" className="flex shrink-0 items-center gap-2.5">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-navy text-white shadow-sm">
                <ClipboardCheck className="h-5 w-5" />
              </span>
              <span className="hidden text-lg font-bold tracking-tight text-primary-navy sm:block">
                Farma<span className="text-primary-orange">Audit</span>
              </span>
            </NavLink>

            {/* Nav (desktop) */}
            <nav className="hidden flex-1 items-center gap-1 md:flex">
              {navItems.map((item) => (
                <NavLink key={item.to} to={item.to} className={navLinkClasses}>
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </NavLink>
              ))}
            </nav>

            {/* Actions */}
            <div className="flex items-center gap-2 sm:gap-3">
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setNotificationsOpen((current) => !current)}
                  className={`relative rounded-lg p-2 transition-colors ${
                    notificationsOpen
                      ? 'bg-primary-navy/10 text-primary-navy'
                      : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
                  }`}
                  aria-label="Notificaciones"
                >
                  <Bell className="h-5 w-5" />
                  {unreadCount > 0 && (
                    <span className="absolute -right-0.5 -top-0.5 flex h-4.5 min-w-4.5 items-center justify-center rounded-full bg-severity-critico px-1 text-[10px] font-bold text-white">
                      {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                  )}
                </button>

                {notificationsOpen && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setNotificationsOpen(false)} />
                    <div className="absolute right-0 z-20 mt-2 w-80 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-lg animate-fade-in">
                      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
                        <span className="text-sm font-semibold text-gray-900">Notificaciones</span>
                        {unreadCount > 0 && (
                          <span className="rounded-full bg-primary-navy/10 px-2 py-0.5 text-xs font-medium text-primary-navy">
                            {unreadCount} sin leer
                          </span>
                        )}
                      </div>
                      {notificaciones.length === 0 ? (
                        <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
                          <Bell className="h-8 w-8 text-gray-300" />
                          <p className="text-sm text-gray-500">No hay pendientes.</p>
                        </div>
                      ) : (
                        <div className="max-h-80 overflow-y-auto">
                          {notificaciones.slice(0, 8).map((notificacion) => (
                            <button
                              key={notificacion.id}
                              type="button"
                              onClick={() => void handleNotificationClick(notificacion.id, notificacion.id_gestion)}
                              className="flex w-full items-start gap-3 border-b border-gray-100 px-4 py-3 text-left transition-colors hover:bg-gray-50"
                            >
                              <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-orange/10">
                                <AlertTriangle className="h-3.5 w-3.5 text-primary-orange" />
                              </span>
                              <span>
                                <span className="block text-sm font-medium text-gray-900">
                                  {notificacion.tipo === 'mensaje_nuevo' || notificacion.tipo === 'encargado_respondio'
                                    ? 'Nueva actividad en desvio'
                                    : notificacion.tipo === 'vencimiento_proximo'
                                      ? 'Desvio vencido'
                                      : 'Notificacion de desvio'}
                                </span>
                                <span className="block text-xs text-gray-500">{notificacion.id_gestion}</span>
                              </span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </>
                )}
              </div>

              <div className="flex items-center gap-2 border-l border-gray-200 pl-2 sm:pl-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-navy text-sm font-semibold text-white">
                  {userInitial}
                </span>
                <span className="hidden max-w-40 truncate text-sm text-gray-600 lg:block">{user?.email}</span>
                <button
                  onClick={handleLogout}
                  className="rounded-lg p-2 text-gray-500 transition-colors hover:bg-red-50 hover:text-red-600"
                  aria-label="Cerrar sesion"
                  title="Cerrar sesion"
                >
                  <LogOut className="h-4.5 w-4.5" />
                </button>
              </div>
            </div>
          </div>

          {/* Nav (mobile) — wrap en vez de scroll horizontal: con 4 items por
              rol como mucho, envolver a una segunda linea es mas robusto que
              un overflow-x-auto sin ninguna pista visual de que se puede
              deslizar (el ultimo item quedaba "cortado" sin aviso). */}
          <nav className="-mx-1 flex flex-wrap items-center gap-1 pb-2 md:hidden">
            {navItems.map((item) => (
              <NavLink key={item.to} to={item.to} className={navLinkClasses}>
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      {!contentClassName && (
        <div className="mx-auto max-w-7xl px-4 pt-6 sm:px-6 lg:px-8">
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">{title}</h1>
        </div>
      )}

      <div className={contentClassName || 'mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8'}>{children}</div>
      <Toaster position="bottom-right" richColors />
    </div>
  );
}

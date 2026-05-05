import type { ModulePermission, Role, UserProfile } from '../types';

export const MODULE_OPTIONS: { key: ModulePermission; label: string; roles: Role[] }[] = [
  { key: 'dashboard', label: 'Dashboard', roles: ['admin', 'sucursal'] },
  { key: 'desvios', label: 'Desvios', roles: ['admin', 'auditor'] },
  { key: 'gestion_desvios', label: 'Gestion de desvios', roles: ['admin', 'auditor'] },
  { key: 'revision_desvios', label: 'Revision de desvios', roles: ['admin', 'auditor'] },
  { key: 'mis_desvios', label: 'Mis desvios', roles: ['sucursal'] },
  { key: 'sucursales', label: 'Sucursales', roles: ['admin', 'auditor', 'sucursal'] },
  { key: 'admin', label: 'Administracion', roles: ['admin'] },
];

export const DEFAULT_MODULES_BY_ROLE: Record<Role, ModulePermission[]> = {
  admin: MODULE_OPTIONS.map((module) => module.key),
  auditor: ['desvios', 'gestion_desvios', 'revision_desvios', 'sucursales'],
  sucursal: ['dashboard', 'mis_desvios', 'sucursales'],
};

export function normalizeModulePermissions(role: Role, modules?: ModulePermission[] | null): ModulePermission[] {
  const allowedForRole = new Set(MODULE_OPTIONS.filter((module) => module.roles.includes(role)).map((module) => module.key));
  const source = modules ?? DEFAULT_MODULES_BY_ROLE[role];
  return Array.from(new Set(source.filter((module) => allowedForRole.has(module))));
}

export function hasModuleAccess(profile: UserProfile | null, module: ModulePermission): boolean {
  if (!profile) return false;
  if (profile.role === 'admin') return true;
  return normalizeModulePermissions(profile.role, profile.permisos_modulos).includes(module);
}

export function firstAllowedPath(profile: UserProfile | null): string {
  if (!profile) return '/dashboard';
  const modules = normalizeModulePermissions(profile.role, profile.permisos_modulos);
  if (modules.includes('dashboard')) return '/dashboard';
  if (modules.includes('desvios')) return '/desvios';
  if (modules.includes('gestion_desvios')) return '/gestion-desvios';
  if (modules.includes('revision_desvios')) return '/revision-desvios';
  if (modules.includes('mis_desvios')) return '/mis-desvios';
  if (modules.includes('sucursales')) return '/sucursales';
  if (modules.includes('admin')) return '/admin';
  return '/dashboard';
}

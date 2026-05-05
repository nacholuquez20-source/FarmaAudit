import type { ModulePermission, Role, UserProfile } from '../types';

const LEGACY_MODULE_ALIASES: Record<string, ModulePermission> = {
  desvios: 'gestion_desvios',
};

export const MODULE_OPTIONS: { key: ModulePermission; label: string; roles: Role[] }[] = [
  { key: 'dashboard', label: 'Dashboard', roles: ['admin', 'sucursal'] },
  { key: 'gestion_desvios', label: 'Gestion de desvios', roles: ['admin', 'auditor'] },
  { key: 'revision_desvios', label: 'Revision de desvios', roles: ['admin', 'auditor'] },
  { key: 'mis_desvios', label: 'Mis desvios', roles: ['sucursal'] },
  { key: 'sucursales', label: 'Sucursales', roles: ['admin', 'auditor', 'sucursal'] },
  { key: 'admin', label: 'Administracion', roles: ['admin'] },
];

export const DEFAULT_MODULES_BY_ROLE: Record<Role, ModulePermission[]> = {
  admin: MODULE_OPTIONS.map((module) => module.key),
  auditor: ['gestion_desvios', 'revision_desvios', 'sucursales'],
  sucursal: ['dashboard', 'mis_desvios', 'sucursales'],
};

export function normalizeModulePermissions(role: Role, modules?: ModulePermission[] | null): ModulePermission[] {
  const allowedForRole = new Set(MODULE_OPTIONS.filter((module) => module.roles.includes(role)).map((module) => module.key));
  const source = (modules ?? DEFAULT_MODULES_BY_ROLE[role]) as string[];
  const normalized: ModulePermission[] = [];
  for (const item of source) {
    const module = LEGACY_MODULE_ALIASES[item] ?? (item as ModulePermission);
    if (allowedForRole.has(module) && !normalized.includes(module)) {
      normalized.push(module);
    }
  }
  return normalized;
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
  if (modules.includes('gestion_desvios')) return '/gestion-desvios';
  if (modules.includes('revision_desvios')) return '/revision-desvios';
  if (modules.includes('mis_desvios')) return '/mis-desvios';
  if (modules.includes('sucursales')) return '/sucursales';
  if (modules.includes('admin')) return '/admin';
  return '/dashboard';
}

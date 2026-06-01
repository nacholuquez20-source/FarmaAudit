import { createContext, createElement, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';
import type { ModulePermission, Role, UserProfile } from '../types';
import { normalizeModulePermissions } from '../lib/permissions';

interface AuthState {
  user: User | null;
  profile: UserProfile | null;
  role: Role | null;
  loading: boolean;
  profileLoading: boolean;
  profileError: string | null;
}

const DEV_USER = {
  id: 'dev-user-123',
  email: 'dev@test.com',
  user_metadata: {},
  app_metadata: {},
  aud: 'authenticated',
  created_at: new Date().toISOString(),
} as unknown as User;

const DEV_PROFILE: UserProfile = {
  id: 'dev-user-123',
  role: 'admin',
  nombre: 'Dev Admin',
  telefono: null,
  id_sucursal: null,
  permisos_modulos: normalizeModulePermissions('admin'),
};

const AuthContext = createContext<AuthState | null>(null);
const PROFILE_LOAD_TIMEOUT_MS = 15000;
const AUTH_STORAGE_KEY = 'farma-audit-auth';
const MAX_PROFILE_RETRIES = 2;

function readModulePermissions(value: unknown): ModulePermission[] | null {
  return Array.isArray(value) ? (value.filter((item) => typeof item === 'string') as ModulePermission[]) : null;
}

function normalizeProfile(profile: Partial<UserProfile> | null, authUser?: User | null): UserProfile | null {
  if (!profile?.id || !profile.role) return null;
  const modulePermissions = readModulePermissions(authUser?.app_metadata?.module_permissions);
  return {
    id: profile.id,
    email: authUser?.email ?? profile.email ?? null,
    role: profile.role,
    nombre: profile.nombre ?? null,
    telefono: profile.telefono ?? null,
    id_sucursal: profile.id_sucursal ?? null,
    permisos_modulos: normalizeModulePermissions(profile.role, modulePermissions),
  };
}

async function loadProfile(userId: string, authUser?: User | null): Promise<UserProfile | null> {
  const { data, error } = await supabase
    .from('profiles')
    .select('id, role, nombre, telefono, id_sucursal')
    .eq('id', userId)
    .maybeSingle();

  if (error) throw error;
  return normalizeProfile(data, authUser);
}

async function loadProfileWithRetry(userId: string, authUser?: User | null): Promise<UserProfile | null> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= MAX_PROFILE_RETRIES; attempt++) {
    try {
      return await Promise.race([
        loadProfile(userId, authUser),
        new Promise<UserProfile | null>((resolve) => {
          window.setTimeout(() => resolve(null), PROFILE_LOAD_TIMEOUT_MS);
        }),
      ]);
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt < MAX_PROFILE_RETRIES) {
        await new Promise(resolve => window.setTimeout(resolve, 1000 * (attempt + 1)));
      }
    }
  }

  throw lastError || new Error('Failed to load profile after retries');
}

function readCachedSessionUser(): User | null {
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { user?: User; expires_at?: number };
    if (parsed.expires_at && parsed.expires_at * 1000 < Date.now()) return null;
    return parsed.user ?? null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const initializedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    const applyUser = async (sessionUser: User | null) => {
      if (cancelled) return;

      if (!sessionUser) {
        if (import.meta.env.DEV) {
          setUser(DEV_USER);
          setProfile(DEV_PROFILE);
        } else {
          setUser(null);
          setProfile(null);
        }
        setProfileLoading(false);
        setProfileError(null);
        return;
      }

      setUser(sessionUser);
      setProfileLoading(true);
      setProfileError(null);
      try {
        const loadedProfile = await loadProfileWithRetry(sessionUser.id, sessionUser);
        if (!cancelled) {
          setProfile(loadedProfile);
          if (!loadedProfile) setProfileError('No se pudo cargar el perfil del usuario.');
        }
      } catch (err) {
        console.error('[AuthProvider] Failed to load profile:', err);
        if (!cancelled) {
          setProfile(null);
          const message = err instanceof Error ? err.message : 'No se pudo cargar el perfil del usuario.';
          setProfileError(message.includes('timeout') ? 'Conexión lenta. Reintentar...' : message);
        }
      } finally {
        if (!cancelled) setProfileLoading(false);
      }
    };

    const finishInit = async (sessionUser: User | null) => {
      if (initializedRef.current || cancelled) return;
      initializedRef.current = true;
      void applyUser(sessionUser);
      if (!cancelled) setLoading(false);
    };

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (cancelled) return;

      if (event === 'INITIAL_SESSION') {
        await finishInit(session?.user ?? null);
        return;
      }

      await applyUser(session?.user ?? null);
      if (!cancelled) setLoading(false);
    });

    supabase.auth
      .getSession()
      .then(({ data, error }) => {
        if (error) throw error;
        return finishInit(data.session?.user ?? null);
      })
      .catch((err) => {
        console.error('[AuthProvider] getSession() error:', err);
        return finishInit(null);
      });

    const failSafe = window.setTimeout(() => {
      if (!initializedRef.current) {
        finishInit(readCachedSessionUser());
      }
    }, 8000);

    return () => {
      cancelled = true;
      window.clearTimeout(failSafe);
      subscription.unsubscribe();
    };
  }, []);

  return createElement(
    AuthContext.Provider,
    { value: { user, profile, role: profile?.role || null, loading, profileLoading, profileError } },
    children,
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}

export async function login(email: string, password: string) {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw error;
  return data;
}

export async function requestPasswordReset(email: string) {
  const redirectTo = `${window.location.origin}/reset-password`;
  const { data, error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo });
  if (error) throw error;
  return data;
}

export async function updatePassword(password: string) {
  const { data, error } = await supabase.auth.updateUser({ password });
  if (error) throw error;
  return data;
}

export async function logout() {
  const { error } = await supabase.auth.signOut();
  if (error) throw error;
}

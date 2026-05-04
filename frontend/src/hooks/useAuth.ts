import { createContext, createElement, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';
import type { Role, UserProfile } from '../types';

interface AuthState {
  user: User | null;
  profile: UserProfile | null;
  role: Role | null;
  loading: boolean;
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
};

const AuthContext = createContext<AuthState | null>(null);

function normalizeProfile(profile: Partial<UserProfile> | null): UserProfile | null {
  if (!profile?.id || !profile.role) return null;
  return {
    id: profile.id,
    role: profile.role,
    nombre: profile.nombre ?? null,
    telefono: profile.telefono ?? null,
    id_sucursal: profile.id_sucursal ?? null,
  };
}

async function loadProfile(userId: string): Promise<UserProfile | null> {
  console.log('[loadProfile] Starting for user:', userId);
  const { data, error } = await supabase
    .from('profiles')
    .select('id, role, nombre, telefono, id_sucursal')
    .eq('id', userId)
    .maybeSingle();

  console.log('[loadProfile] Query completed', { hasData: !!data, error });

  if (!error) return normalizeProfile(data);

  if (error.message.toLowerCase().includes('id_sucursal')) {
    console.log('[loadProfile] Retrying without id_sucursal column');
    const fallback = await supabase.from('profiles').select('id, role, nombre, telefono').eq('id', userId).maybeSingle();
    if (fallback.error) throw fallback.error;
    return normalizeProfile(fallback.data);
  }

  throw error;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const initializedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    console.log('[AuthProvider] Initializing...');

    const applyUser = async (sessionUser: User | null) => {
      if (cancelled) return;

      console.log('[AuthProvider] applyUser called', { hasUser: !!sessionUser });

      if (!sessionUser) {
        if (import.meta.env.DEV) {
          console.log('[AuthProvider] No user, using DEV_USER');
          setUser(DEV_USER);
          setProfile(DEV_PROFILE);
        } else {
          console.log('[AuthProvider] No user, setting null');
          setUser(null);
          setProfile(null);
        }
        return;
      }

      console.log('[AuthProvider] Loading profile for user:', sessionUser.id);
      setUser(sessionUser);
      try {
        const loadedProfile = await loadProfile(sessionUser.id);
        console.log('[AuthProvider] Profile loaded:', loadedProfile?.role);
        if (!cancelled) setProfile(loadedProfile);
      } catch (err) {
        console.error('[AuthProvider] Failed to load profile:', err);
        if (!cancelled) setProfile(null);
      }
    };

    const finishInit = async (sessionUser: User | null) => {
      if (initializedRef.current || cancelled) return;
      console.log('[AuthProvider] finishInit called');
      initializedRef.current = true;
      await applyUser(sessionUser);
      if (!cancelled) {
        console.log('[AuthProvider] Setting loading=false');
        setLoading(false);
      }
    };

    console.log('[AuthProvider] Registering onAuthStateChange listener');
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, session) => {
      console.log('[AuthProvider] onAuthStateChange:', event);
      if (cancelled) return;

      if (event === 'INITIAL_SESSION') {
        console.log('[AuthProvider] INITIAL_SESSION event, calling finishInit');
        await finishInit(session?.user ?? null);
        return;
      }

      await applyUser(session?.user ?? null);
      if (!cancelled) setLoading(false);
    });

    console.log('[AuthProvider] Calling getSession()');
    supabase.auth
      .getSession()
      .then(({ data, error }) => {
        console.log('[AuthProvider] getSession() resolved', { hasSession: !!data.session, error });
        if (error) throw error;
        return finishInit(data.session?.user ?? null);
      })
      .catch((err) => {
        console.error('[AuthProvider] getSession() error:', err);
        return finishInit(null);
      });

    const failSafe = window.setTimeout(() => {
      if (!initializedRef.current) {
        console.warn('[AuthProvider] Auth initialization timed out after 8s!');
        finishInit(null);
      }
    }, 8000);

    return () => {
      cancelled = true;
      window.clearTimeout(failSafe);
      subscription.unsubscribe();
    };
  }, []);

  return createElement(AuthContext.Provider, { value: { user, profile, role: profile?.role || null, loading } }, children);
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

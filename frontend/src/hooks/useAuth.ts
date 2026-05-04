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
  const { data, error } = await supabase
    .from('profiles')
    .select('id, role, nombre, telefono, id_sucursal')
    .eq('id', userId)
    .maybeSingle();

  if (!error) return normalizeProfile(data);

  if (error.message.toLowerCase().includes('id_sucursal')) {
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
        return;
      }

      setUser(sessionUser);
      try {
        const loadedProfile = await loadProfile(sessionUser.id);
        if (!cancelled) setProfile(loadedProfile);
      } catch (err) {
        console.error('Failed to load profile:', err);
        if (!cancelled) setProfile(null);
      }
    };

    const finishInit = async (sessionUser: User | null) => {
      if (initializedRef.current || cancelled) return;
      initializedRef.current = true;
      await applyUser(sessionUser);
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
        console.error('Error loading session:', err);
        return finishInit(null);
      });

    const failSafe = window.setTimeout(() => {
      if (!initializedRef.current) {
        console.warn('Auth initialization timed out.');
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

import { useEffect, useState } from 'react';
import type { User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';
import type { Role, UserProfile } from '../types';

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
  const selectWithSucursal = 'id, role, nombre, telefono, id_sucursal';
  const { data, error } = await supabase.from('profiles').select(selectWithSucursal).eq('id', userId).maybeSingle();

  if (!error) return normalizeProfile(data);

  const message = error.message.toLowerCase();
  if (message.includes('id_sucursal')) {
    const fallback = await supabase.from('profiles').select('id, role, nombre, telefono').eq('id', userId).maybeSingle();
    if (fallback.error) throw fallback.error;
    return normalizeProfile(fallback.data);
  }

  throw error;
}

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const applySession = async (sessionUser: User | null) => {
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

    const getSession = async () => {
      setLoading(true);
      try {
        const {
          data: { session },
          error,
        } = await supabase.auth.getSession();

        if (error) throw error;
        if (!cancelled) await applySession(session?.user ?? null);
      } catch (err) {
        console.error('Error loading session:', err);
        if (!cancelled && import.meta.env.DEV) {
          setUser(DEV_USER);
          setProfile(DEV_PROFILE);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    getSession();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (cancelled || event === 'INITIAL_SESSION') return;
      await applySession(session?.user ?? null);
      if (!cancelled) setLoading(false);
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, []);

  const role: Role | null = profile?.role || null;

  return {
    user,
    profile,
    role,
    loading,
  };
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

import { useEffect, useState } from 'react';
import type { User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';
import type { UserProfile, Role } from '../types';

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

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const getSession = async () => {
      setLoading(true);

      timeoutId = setTimeout(() => {
        if (!cancelled) {
          console.warn('Session loading timeout - falling back to guest/dev mode');
          if (import.meta.env.DEV) {
            setUser(DEV_USER);
            setProfile(DEV_PROFILE);
          } else {
            setUser(null);
            setProfile(null);
          }
          setLoading(false);
        }
      }, 3000);

      try {
        const {
          data: { session },
        } = await supabase.auth.getSession();

        if (cancelled) return;
        if (timeoutId) clearTimeout(timeoutId);

        if (session?.user) {
          setUser(session.user);
          try {
            const { data } = await supabase.from('profiles').select('*').eq('id', session.user.id).single();
            if (!cancelled) {
              setProfile(data);
            }
          } catch (err) {
            console.error('Failed to load profile:', err);
            if (!cancelled) {
              setProfile(null);
            }
          }
        } else {
          if (import.meta.env.DEV) {
            setUser(DEV_USER);
            setProfile(DEV_PROFILE);
          } else {
            setUser(null);
            setProfile(null);
          }
        }
      } catch (err) {
        console.error('Failed to get session:', err);
        if (cancelled) return;
        if (timeoutId) clearTimeout(timeoutId);
        if (import.meta.env.DEV) {
          setUser(DEV_USER);
          setProfile(DEV_PROFILE);
        } else {
          setUser(null);
          setProfile(null);
        }
      } finally {
        if (!cancelled && timeoutId) {
          clearTimeout(timeoutId);
        }
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    getSession();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, session) => {
      if (cancelled) return;

      try {
        if (session?.user) {
          setUser(session.user);
          try {
            const { data } = await supabase.from('profiles').select('*').eq('id', session.user.id).single();
            if (!cancelled) {
              setProfile(data);
            }
          } catch (err) {
            console.error('Failed to load profile on auth change:', err);
            if (!cancelled) {
              setProfile(null);
            }
          }
        } else {
          if (import.meta.env.DEV) {
            setUser(DEV_USER);
            setProfile(DEV_PROFILE);
          } else {
            setUser(null);
            setProfile(null);
          }
        }
      } catch (err) {
        console.error('Error in auth state change handler:', err);
        if (import.meta.env.DEV) {
          setUser(DEV_USER);
          setProfile(DEV_PROFILE);
        } else {
          setUser(null);
          setProfile(null);
        }
      }
    });

    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
      subscription?.unsubscribe();
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

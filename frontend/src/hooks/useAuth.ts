import { useEffect, useState } from 'react';
import type { User } from '@supabase/supabase-js';
import { supabase, supabaseConfig } from '../lib/supabase';
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

      // Debug: Log if credentials are available
      console.log('[useAuth] Starting getSession', {
        hasUrl: supabaseConfig.hasUrl,
        hasKey: supabaseConfig.hasKey,
        isDev: import.meta.env.DEV,
      });

      timeoutId = setTimeout(() => {
        if (!cancelled) {
          console.warn('[useAuth] Session loading timeout after 3s - falling back', {
            hasUrl: supabaseConfig.hasUrl,
            hasKey: supabaseConfig.hasKey,
          });
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
        console.log('[useAuth] Calling supabase.auth.getSession()...');
        const {
          data: { session },
        } = await supabase.auth.getSession();

        console.log('[useAuth] getSession completed', { hasSession: !!session?.user });
        if (cancelled) return;
        if (timeoutId) clearTimeout(timeoutId);

        if (session?.user) {
          console.log('[useAuth] User found:', session.user.id);
          setUser(session.user);
          try {
            console.log('[useAuth] Loading profile for user:', session.user.id);
            const { data } = await supabase.from('profiles').select('*').eq('id', session.user.id).single();
            console.log('[useAuth] Profile loaded:', data?.role);
            if (!cancelled) {
              setProfile(data);
            }
          } catch (err) {
            console.error('[useAuth] Failed to load profile:', err);
            if (!cancelled) {
              setProfile(null);
            }
          }
        } else {
          console.log('[useAuth] No session found');
          if (import.meta.env.DEV) {
            console.log('[useAuth] Using DEV user');
            setUser(DEV_USER);
            setProfile(DEV_PROFILE);
          } else {
            setUser(null);
            setProfile(null);
          }
        }
      } catch (err) {
        console.error('[useAuth] Error in getSession:', err);
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
          console.log('[useAuth] Setting loading=false');
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

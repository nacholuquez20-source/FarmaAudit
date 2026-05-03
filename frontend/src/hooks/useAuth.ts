import { useEffect, useState } from 'react';
import type { User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';
import type { UserProfile, Role } from '../types';

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const getSession = async () => {
      setLoading(true);
      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (cancelled) return;

      if (session?.user) {
        setUser(session.user);
        const { data } = await supabase.from('profiles').select('*').eq('id', session.user.id).single();
        if (!cancelled) {
          setProfile(data);
        }
      } else {
        // Development mode: fake admin user
        const fakeUser = {
          id: 'dev-user-123',
          email: 'dev@test.com',
          user_metadata: {},
          app_metadata: {},
          aud: 'authenticated',
          created_at: new Date().toISOString(),
        } as unknown as User;

        setUser(fakeUser);
        setProfile({
          id: 'dev-user-123',
          role: 'admin',
          nombre: 'Dev Admin',
          telefono: null,
          id_sucursal: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      }

      if (!cancelled) {
        setLoading(false);
      }
    };

    getSession();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, session) => {
      if (cancelled) return;

      if (session?.user) {
        setUser(session.user);
        const { data } = await supabase.from('profiles').select('*').eq('id', session.user.id).single();
        if (!cancelled) {
          setProfile(data);
        }
      } else {
        // Development mode: fake admin user
        const fakeUser = {
          id: 'dev-user-123',
          email: 'dev@test.com',
          user_metadata: {},
          app_metadata: {},
          aud: 'authenticated',
          created_at: new Date().toISOString(),
        } as unknown as User;

        setUser(fakeUser);
        setProfile({
          id: 'dev-user-123',
          role: 'admin',
          nombre: 'Dev Admin',
          telefono: null,
          id_sucursal: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      }
    });

    return () => {
      cancelled = true;
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

export async function logout() {
  const { error } = await supabase.auth.signOut();
  if (error) throw error;
}

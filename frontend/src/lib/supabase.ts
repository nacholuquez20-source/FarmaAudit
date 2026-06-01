import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseKey) {
  const message = `⚠️ Supabase not configured. URL: ${supabaseUrl ? '✓' : '✗ MISSING'}, Key: ${supabaseKey ? '✓' : '✗ MISSING'}`;
  console.error(message);
  // Still create client so errors bubble up properly
}

const secureSessionStorage = {
  getItem: (key: string) => {
    if (typeof window === 'undefined') return null;
    return sessionStorage.getItem(key);
  },
  setItem: (key: string, value: string) => {
    if (typeof window === 'undefined') return;
    sessionStorage.setItem(key, value);
  },
  removeItem: (key: string) => {
    if (typeof window === 'undefined') return;
    sessionStorage.removeItem(key);
  },
};

export const supabase = createClient(supabaseUrl || '', supabaseKey || '', {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
    storageKey: 'farma-audit-auth',
    storage: secureSessionStorage,
    lock: async (_name, _acquireTimeout, fn) => fn(),
  },
});

// Expose config status for debugging
export const supabaseConfig = {
  url: supabaseUrl,
  hasUrl: !!supabaseUrl,
  hasKey: !!supabaseKey,
};

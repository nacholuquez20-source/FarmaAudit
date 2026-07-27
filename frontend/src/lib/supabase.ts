import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseKey) {
  const message = `⚠️ Supabase not configured. URL: ${supabaseUrl ? '✓' : '✗ MISSING'}, Key: ${supabaseKey ? '✓' : '✗ MISSING'}`;
  console.error(message);
  // Still create client so errors bubble up properly
}

export const supabase = createClient(supabaseUrl || '', supabaseKey || '', {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
    storageKey: 'farma-audit-auth',
  },
});

// Expose config status for debugging
export const supabaseConfig = {
  url: supabaseUrl,
  hasUrl: !!supabaseUrl,
  hasKey: !!supabaseKey,
};

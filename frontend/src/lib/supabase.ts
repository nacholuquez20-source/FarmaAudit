import { createClient, processLock } from '@supabase/supabase-js';

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
    // navigatorLock (the default) serializes every auth call through the
    // Web Locks API with its own acquire/steal timeouts. Combined with
    // React StrictMode's double-invoked effects in dev, that added enough
    // queued lock latency to blow past the profile-load timeout on a plain
    // page reload. This is a single-tab admin panel, so a same-process
    // in-memory lock gives the same call-serialization without that cost.
    lock: processLock,
  },
});

import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseKey) {
  const message = 'Supabase credentials not configured. Please set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.';
  if (import.meta.env.DEV) {
    console.warn(message);
  } else {
    console.error(message);
  }
}

export const supabase = createClient(supabaseUrl || '', supabaseKey || '');

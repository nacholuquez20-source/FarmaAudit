import { useState, useEffect } from 'react';
import { supabase } from '../lib/supabase';
import type { ControlStockItem } from '../types';

export function useControlStock(sucursal_id?: string) {
  const [items, setItems] = useState<ControlStockItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadControlStock = async () => {
      if (!sucursal_id) {
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);
        let query = supabase.from('control_stock').select('*');

        if (sucursal_id) {
          query = query.eq('sucursal_id', sucursal_id);
        }

        const { data, error: err } = await query.order('fecha', { ascending: false });

        if (err) throw err;
        setItems(data || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load control stock');
      } finally {
        setLoading(false);
      }
    };

    loadControlStock();
  }, [sucursal_id]);

  return { items, loading, error };
}

import { useState, useEffect } from 'react';
import { supabase } from '../lib/supabase';

export interface ControlStockItem {
  id: string;
  auditoria_id: string | null;
  sucursal_id: string;
  fecha: string;
  auditor: string;
  nombre_item: string;
  stock_fisico: number;
  stock_sistema: number;
  diferencia: number;
  alerta: string;
}

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

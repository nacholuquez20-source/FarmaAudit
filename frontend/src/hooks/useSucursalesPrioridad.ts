import { useCallback, useEffect, useState } from 'react';
import { getEstadoContactoSucursales, getSucursalesDashboard } from '../lib/api';
import { supabase } from '../lib/supabase';
import type { EstadoContactoSucursal, SucursalDashboard } from '../types';

/**
 * Centraliza en un solo Promise.all lo que antes pedían por separado Hoy.tsx
 * (getSucursalesDashboard + conteo En_revision) y SucursalesDashboard.tsx
 * (getEstadoContactoSucursales) — ambos ahora conviven dentro del módulo
 * "Hoy" (buckets de prioridad + grid filtrable) y compartían exactamente los
 * mismos datos pedidos con fetches independientes, con el riesgo real de
 * mostrar snapshots distintos por carreras de red separadas.
 *
 * `cargarContacto` existe porque el estado de contacto es admin/auditor-only
 * (usuarios_whatsapp es RLS admin-only en el backend) — quien monte este
 * hook para un rol sin ese acceso debe pasar `false` para no pedirlo.
 */
export function useSucursalesPrioridad(cargarContacto: boolean) {
  const [rows, setRows] = useState<SucursalDashboard[]>([]);
  const [enRevision, setEnRevision] = useState<Map<string, number>>(new Map());
  const [contacto, setContacto] = useState<Record<string, EstadoContactoSucursal>>({});
  // Distingue "todavia no intentamos cargar el contacto" de "ya intentamos y
  // esta sucursal no aparecio o fallo la llamada" — contacto[id] es
  // undefined en ambos casos, por eso hace falta este flag aparte (mismo
  // criterio que ya usaba SucursalesDashboard.tsx).
  const [contactoLoaded, setContactoLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const recargarContacto = useCallback(() => {
    if (!cargarContacto) return;
    getEstadoContactoSucursales()
      .then((r) => setContacto(Object.fromEntries(r.map((x) => [x.id_sucursal, x]))))
      .catch(() => setContacto({}))
      .finally(() => setContactoLoaded(true));
  }, [cargarContacto]);

  useEffect(() => {
    let active = true;

    Promise.all([
      getSucursalesDashboard(),
      supabase.from('gestion').select('id_sucursal').eq('estado', 'En_revision'),
      cargarContacto ? getEstadoContactoSucursales() : Promise.resolve(null),
    ])
      .then(([dashboard, revisionRes, contactoRows]) => {
        if (!active) return;
        setRows(dashboard);

        const map = new Map<string, number>();
        for (const g of revisionRes.data ?? []) {
          const key = (g as { id_sucursal: string }).id_sucursal;
          map.set(key, (map.get(key) ?? 0) + 1);
        }
        setEnRevision(map);

        if (contactoRows) {
          setContacto(Object.fromEntries(contactoRows.map((r) => [r.id_sucursal, r])));
        }
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'No se pudo cargar el panel.');
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
        if (cargarContacto) setContactoLoaded(true);
      });

    return () => {
      active = false;
    };
  }, [cargarContacto]);

  return { rows, enRevision, contacto, contactoLoaded, loading, error, recargarContacto };
}

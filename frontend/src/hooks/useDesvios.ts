import { useMemo, useState } from 'react';
import { useGestion } from './useGestion';
import { useReportes } from './useReportes';
import { useAuth } from './useAuth';
import type { Desvio, DesvioFilters, Gestion, Severidad } from '../types';

const initialFilters: DesvioFilters = {
  sucursal: '',
  severidad: '',
  estado: '',
  fechaDesde: '',
  fechaHasta: '',
  search: '',
};

const severityPriority: Record<Severidad, number> = {
  Alta: 0,
  Media: 1,
  Baja: 2,
};

function isOverdue(gestion: Gestion): boolean {
  if (gestion.estado === 'Vencida') return true;
  if (gestion.estado === 'Cerrada' || !gestion.plazo_fecha) return false;

  const dueDate = new Date(`${gestion.plazo_fecha}T23:59:59`);
  return !Number.isNaN(dueDate.getTime()) && dueDate < new Date();
}

function getComparableDate(value?: string | null): number {
  if (!value) return Number.MAX_SAFE_INTEGER;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? Number.MAX_SAFE_INTEGER : date.getTime();
}

function matchesDateRange(gestion: Gestion, fechaDesde: string, fechaHasta: string): boolean {
  const dueDate = getComparableDate(gestion.plazo_fecha);
  if (fechaDesde && dueDate < getComparableDate(fechaDesde)) return false;
  if (fechaHasta && dueDate > getComparableDate(`${fechaHasta}T23:59:59`)) return false;
  return true;
}

function matchesSearch(gestion: Gestion, search: string): boolean {
  if (!search.trim()) return true;
  const normalizedSearch = search.trim().toLowerCase();
  const haystack = [
    gestion.sucursal,
    gestion.desvio,
    gestion.responsable,
    gestion.plan_accion,
    gestion.severidad,
    gestion.estado,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  return haystack.includes(normalizedSearch);
}

function compareDesvios(a: Gestion, b: Gestion): number {
  const overdueDiff = Number(isOverdue(b)) - Number(isOverdue(a));
  if (overdueDiff !== 0) return overdueDiff;

  const severityDiff = severityPriority[a.severidad] - severityPriority[b.severidad];
  if (severityDiff !== 0) return severityDiff;

  return getComparableDate(a.plazo_fecha) - getComparableDate(b.plazo_fecha);
}

interface SucursalResumen {
  nombre: string;
  desviosActivos: number;
  proximoVencimiento: string | null;
}

export function useDesvios() {
  const { role, profile } = useAuth();
  const scopedSucursalId = role === 'sucursal' ? profile?.id_sucursal ?? undefined : undefined;
  const { gestiones, loading: loadingGestion, error: gestionError } = useGestion({ sucursal_id: scopedSucursalId });
  const { reportes, loading: loadingReportes, error: reportesError } = useReportes({ sucursal_id: scopedSucursalId });
  const [filters, setFilters] = useState<DesvioFilters>(initialFilters);

  const allDesvios = useMemo<Desvio[]>(() => {
    const reportesById = new Map(reportes.map((reporte) => [reporte.id, reporte]));

    return gestiones.map((gestion) => ({
      ...gestion,
      area: reportesById.get(gestion.id_reporte)?.area || '-',
    }));
  }, [gestiones, reportes]);

  const sucursales = useMemo(
    () => Array.from(new Set(allDesvios.map((gestion) => gestion.sucursal).filter(Boolean))).sort(),
    [allDesvios]
  );

  const desvios = useMemo(() => {
    return allDesvios
      .filter((gestion) => {
        if (filters.sucursal && gestion.sucursal !== filters.sucursal) return false;
        if (filters.severidad && gestion.severidad !== filters.severidad) return false;
        if (filters.estado && gestion.estado !== filters.estado) return false;
        if (!matchesDateRange(gestion, filters.fechaDesde, filters.fechaHasta)) return false;
        if (!matchesSearch(gestion, filters.search)) return false;
        return true;
      })
      .sort(compareDesvios);
  }, [allDesvios, filters]);

  const sucursalesResumen = useMemo<SucursalResumen[]>(() => {
    const activos = allDesvios.filter((g) => g.estado === 'Abierta' || g.estado === 'En_proceso' || g.estado === 'Vencida');
    const byNombre = new Map<string, Desvio[]>();

    activos.forEach((desvio) => {
      if (!byNombre.has(desvio.sucursal)) {
        byNombre.set(desvio.sucursal, []);
      }
      byNombre.get(desvio.sucursal)!.push(desvio);
    });

    const resumen = Array.from(byNombre.entries()).map(([nombre, desvios]) => {
      const fechas = desvios
        .map((d) => d.plazo_fecha)
        .filter(Boolean)
        .map((f) => new Date(f).getTime())
        .filter((t) => !Number.isNaN(t));
      const proximoVencimiento = fechas.length > 0 ? new Date(Math.min(...fechas)).toISOString().split('T')[0] : null;

      return {
        nombre,
        desviosActivos: desvios.length,
        proximoVencimiento,
      };
    });

    return resumen.sort((a, b) => {
      if (!a.proximoVencimiento && !b.proximoVencimiento) return 0;
      if (!a.proximoVencimiento) return 1;
      if (!b.proximoVencimiento) return -1;
      return a.proximoVencimiento.localeCompare(b.proximoVencimiento);
    });
  }, [allDesvios]);

  const resetFilters = () => setFilters(initialFilters);

  return {
    desvios,
    allDesvios,
    loading: loadingGestion || loadingReportes,
    error: gestionError || reportesError,
    filters,
    setFilters,
    resetFilters,
    sucursales,
    sucursalesResumen,
    isOverdue,
  };
}

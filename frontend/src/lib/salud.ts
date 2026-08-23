import { Check, CircleDot, Minus, Triangle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { EstadoSalud } from '../types';

// Única fuente de verdad para el color/ícono/label de salud de una sucursal
// en todo el módulo (Dashboard, Hoy, SucursalDetail, SucursalesMap). Antes
// vivía duplicado en SucursalesGrid.tsx y SucursalDetail.tsx con formas
// distintas — y la versión de SucursalDetail no tenía el ícono, rompiendo la
// legibilidad por daltonismo en esa pantalla. El color se comunica siempre
// por COLOR + FORMA, nunca solo color.
interface SaludMeta {
  dot: string;
  border: string;
  pill: string;
  icon: LucideIcon;
  label: string;
  descripcion: string;
}

export const SALUD_META: Record<EstadoSalud, SaludMeta> = {
  critica: {
    dot: 'bg-red-500',
    border: 'border-l-red-500',
    pill: 'bg-red-50 text-red-700',
    icon: Triangle,
    label: 'Crítica',
    descripcion: 'Tiene desvíos vencidos, hace más de 30 días sin auditar, o el último puntaje fue menor a 3.',
  },
  atencion: {
    dot: 'bg-amber-500',
    border: 'border-l-amber-500',
    pill: 'bg-amber-50 text-amber-700',
    icon: CircleDot,
    label: 'Atención',
    descripcion: 'Tiene desvíos abiertos sin vencer, entre 15 y 30 días sin auditar, o el último puntaje fue menor a 4.',
  },
  ok: {
    dot: 'bg-green-500',
    border: 'border-l-green-500',
    pill: 'bg-green-50 text-green-700',
    icon: Check,
    label: 'Al día',
    descripcion: 'Sin desvíos abiertos, auditada hace menos de 15 días, con buen puntaje.',
  },
  sin_datos: {
    dot: 'bg-gray-300',
    border: 'border-l-gray-300',
    pill: 'bg-gray-100 text-gray-600',
    icon: Minus,
    label: 'Sin datos',
    descripcion: 'Todavía no tiene ninguna auditoría registrada.',
  },
};

// Mismo color, en hex — los pines de Google Maps (SucursalesMap) usan estilos
// inline en vez de clases de Tailwind (Pin/AdvancedMarker de @vis.gl).
export const SALUD_HEX: Record<EstadoSalud, string> = {
  critica: '#ef4444',
  atencion: '#f59e0b',
  ok: '#22c55e',
  sin_datos: '#9ca3af',
};

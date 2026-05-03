import type { Severidad, GestionState, Gestion } from '../types';

export function getWhatsappUrl(gestion: Gestion): string | null {
  const phone = gestion.tel_responsable.replace(/\D/g, '');
  if (!phone) return null;

  const message = [
    `Hola ${gestion.responsable || ''}`.trim(),
    `Te contactamos por un desvio registrado en ${gestion.sucursal}.`,
    `Detalle: ${gestion.desvio}`,
    `Severidad: ${gestion.severidad}`,
    `Vencimiento: ${formatDate(gestion.plazo_fecha)}`,
  ].join('\n');

  return `https://wa.me/${phone}?text=${encodeURIComponent(message)}`;
}

export function formatDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString('es-AR', { year: 'numeric', month: 'short', day: 'numeric' });
  } catch {
    return dateString;
  }
}

export function formatDateTime(dateString: string): string {
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString('es-AR', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateString;
  }
}

export function severidadColor(severidad: Severidad): string {
  const colors: Record<Severidad, string> = {
    'Alta': 'bg-red-100 text-red-800',
    'Media': 'bg-yellow-100 text-yellow-800',
    'Baja': 'bg-green-100 text-green-800',
  };
  return colors[severidad] || 'bg-gray-100 text-gray-800';
}

export function gestionStateColor(estado: GestionState): string {
  const colors: Record<GestionState, string> = {
    'Abierta': 'bg-blue-100 text-blue-800',
    'En_proceso': 'bg-purple-100 text-purple-800',
    'Resuelta': 'bg-emerald-100 text-emerald-800',
    'Cerrada': 'bg-green-100 text-green-800',
    'Vencida': 'bg-red-100 text-red-800',
  };
  return colors[estado] || 'bg-gray-100 text-gray-800';
}

export function gestionStateLabel(estado: GestionState): string {
  const labels: Record<GestionState, string> = {
    'Abierta': 'Abierta',
    'En_proceso': 'En proceso',
    'Resuelta': 'Resuelta',
    'Cerrada': 'Cerrada',
    'Vencida': 'Vencida',
  };
  return labels[estado] || estado;
}

export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ');
}

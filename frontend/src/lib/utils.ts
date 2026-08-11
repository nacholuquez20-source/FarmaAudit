import type { Severidad, GestionState, Gestion } from '../types';

// El telefono/nombre se resuelven en vivo contra usuarios_whatsapp (ver
// getResponsableActivo en api.ts) — nunca desde gestion.tel_responsable, que
// es una foto congelada al crear el desvio (ARQUITECTURA_PANEL_DESVIOS.md §4.4).
export function getWhatsappUrl(gestion: Gestion, telefono: string, nombre: string): string | null {
  const phone = telefono.replace(/\D/g, '');
  if (!phone) return null;

  const message = [
    `Hola ${nombre || ''}`.trim(),
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
    'En_revision': 'bg-emerald-100 text-emerald-800',
    'En_gestion_terceros': 'bg-gray-100 text-gray-700',
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
    'En_revision': 'Corregido · en revision',
    'En_gestion_terceros': 'Depende de terceros',
    'Resuelta': 'Resuelta',
    'Cerrada': 'Cerrada',
    'Vencida': 'Vencida',
  };
  return labels[estado] || estado;
}

export function timeSince(dateString: string): string {
  try {
    const then = new Date(dateString).getTime();
    if (Number.isNaN(then)) return '';
    const diffMs = Date.now() - then;
    const hours = Math.floor(diffMs / 3_600_000);
    if (hours < 1) return 'hace instantes';
    if (hours < 24) return `hace ${hours}h`;
    const days = Math.floor(hours / 24);
    return `hace ${days}d`;
  } catch {
    return '';
  }
}

export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ');
}

// Deja solo dígitos. Tiene que coincidir exactamente con
// SupabaseManager._normalize_phone / identity.normalize_phone del backend,
// que es contra lo que se compara el número entrante de un mensaje de
// WhatsApp — si acá se guardara con espacios, guiones o "+", el bot nunca
// lo matchearía y esa persona quedaría con acceso roto en silencio.
export function normalizePhoneDigits(tel: string): string {
  return tel.replace(/\D/g, '');
}

// Enlace directo de WhatsApp normalizando teléfonos argentinos.
// Quita el 0 de trunk, antepone 54 y descarta números demasiado cortos
// (evita links basura como wa.me/54 que no abren ningún chat).
export function whatsappLink(tel: string | null | undefined, mensaje?: string): string | null {
  if (!tel) return null;
  let d = tel.replace(/\D/g, '');
  if (!d) return null;
  if (!d.startsWith('54')) {
    if (d.startsWith('0')) d = d.slice(1);
    d = `54${d}`;
  }
  if (d.length < 10) return null;
  const base = `https://wa.me/${d}`;
  return mensaje ? `${base}?text=${encodeURIComponent(mensaje)}` : base;
}

// Las auditorías se hacen por WhatsApp: este link abre el chat con el bot.
// El texto tiene que ser EXACTAMENTE el disparador que el bot espera —
// router.py compara por igualdad contra V2_TRIGGERS, no por substring—, así que
// no se le puede agregar la sucursal. El bot la pide en el paso siguiente.
export const AUDIT_TRIGGER = 'auditoria';

export function whatsappAuditLink(): string {
  const bot = import.meta.env.VITE_WHATSAPP_PHONE || '5493816199195';
  return `https://wa.me/${bot}?text=${encodeURIComponent(AUDIT_TRIGGER)}`;
}

// Diferencia en días CALENDARIO usando la hora local del navegador
// (Argentina), no UTC — así "hace X días" coincide con la percepción real
// y con la vista SQL cuando esta usa la misma zona horaria.
export function diasDesde(fecha: string | null | undefined): number | null {
  if (!fecha) return null;
  const d = new Date(fecha);
  if (Number.isNaN(d.getTime())) return null;
  const desde = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const hoy = new Date();
  const hoyInicio = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());
  return Math.round((hoyInicio.getTime() - desde.getTime()) / 86_400_000);
}

// ¿La fecha cae en el mes calendario actual (hora local)?
export function esMesActual(fecha: string | null | undefined): boolean {
  if (!fecha) return false;
  const d = new Date(fecha);
  if (Number.isNaN(d.getTime())) return false;
  const hoy = new Date();
  return d.getFullYear() === hoy.getFullYear() && d.getMonth() === hoy.getMonth();
}

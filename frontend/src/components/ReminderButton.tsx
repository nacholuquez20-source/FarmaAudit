import type { ReactNode } from 'react';
import { useState } from 'react';
import { Clock, MessageCircle, UserPlus } from 'lucide-react';
import { Button } from './Button';
import { postRecordatorioSucursal } from '../lib/api';
import { whatsappLink } from '../lib/utils';
import type { EstadoContactoSucursal, RecordatorioResultado } from '../types';

interface ReminderButtonProps {
  idSucursal: string;
  sucursalNombre: string;
  cantidadDesvios: number;
  diasSinAccion?: number | null;
  /** undefined = todavia cargando, null = no se pudo resolver */
  estadoContacto: EstadoContactoSucursal | null | undefined;
  onSent?: () => void;
  size?: 'sm' | 'md';
  /** Icono solo, sin texto de apoyo — para grillas densas (tarjetas de sucursal). */
  compact?: boolean;
}

function proximoDisponibleLabel(iso: string): string {
  const restante = new Date(iso).getTime() - new Date().getTime();
  if (restante <= 0) return 'ya disponible';
  const horas = Math.ceil(restante / 3_600_000);
  return horas <= 1 ? 'en menos de 1 h' : `en ${horas} h`;
}

function mensajeManual(sucursal: string, cantidad: number): string {
  return (
    `Hola, soy de auditoría de FarmaAudit. Tenés ${cantidad} desvío(s) pendientes en ${sucursal}. ` +
    `Para verlos y responder, escribile "HOLA" al bot de FarmaAudit. ¡Gracias!`
  );
}

function IconLink({
  href,
  title,
  className,
  children,
}: {
  href: string;
  title: string;
  className: string;
  children: ReactNode;
}) {
  return (
    <a
      href={href}
      target={href.startsWith('http') ? '_blank' : undefined}
      rel={href.startsWith('http') ? 'noopener noreferrer' : undefined}
      onClick={(e) => e.stopPropagation()}
      title={title}
      className={`rounded-md p-1.5 transition ${className}`}
    >
      {children}
    </a>
  );
}

export function ReminderButton({
  idSucursal,
  sucursalNombre,
  cantidadDesvios,
  diasSinAccion,
  estadoContacto,
  onSent,
  size = 'md',
  compact = false,
}: ReminderButtonProps) {
  const [sending, setSending] = useState(false);
  const [resultado, setResultado] = useState<RecordatorioResultado | null>(null);

  if (estadoContacto === undefined) {
    return <span className="text-xs text-gray-400">Cargando...</span>;
  }

  if (!estadoContacto || !estadoContacto.tiene_telefono) {
    if (compact) {
      return (
        <IconLink href="/admin?tab=whatsapp" title="No hay a quién reclamarle · asignar encargado" className="text-gray-400 hover:bg-gray-100">
          <UserPlus className="h-4 w-4" />
        </IconLink>
      );
    }
    return (
      <div>
        <a
          href="/admin?tab=whatsapp"
          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100"
        >
          <UserPlus className="h-4 w-4" />
          Asignar encargado
        </a>
        <p className="mt-1 text-xs text-gray-400">No hay a quién reclamarle.</p>
      </div>
    );
  }

  const enCooldown =
    estadoContacto.proximo_disponible_at &&
    new Date(estadoContacto.proximo_disponible_at).getTime() > new Date().getTime();

  if (enCooldown) {
    const label = `Ya reclamado hoy · disponible de nuevo ${proximoDisponibleLabel(estadoContacto.proximo_disponible_at as string)}`;
    if (compact) {
      return (
        <span title={label} className="rounded-md p-1.5 text-gray-300">
          <Clock className="h-4 w-4" />
        </span>
      );
    }
    return (
      <div>
        <Button variant="secondary" size={size} disabled>
          Ya reclamado hoy
        </Button>
        <p className="mt-1 text-xs text-gray-500">
          Disponible de nuevo {proximoDisponibleLabel(estadoContacto.proximo_disponible_at as string)}.
        </p>
      </div>
    );
  }

  const handleRecordar = async () => {
    setSending(true);
    setResultado(null);
    try {
      const r = await postRecordatorioSucursal(idSucursal);
      setResultado(r.resultado);
      if (r.resultado === 'enviado') onSent?.();
    } catch {
      setResultado('fallido');
    } finally {
      setSending(false);
    }
  };

  if (estadoContacto.ventana_abierta) {
    if (compact) {
      return (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            void handleRecordar();
          }}
          disabled={sending}
          title="Recordar por WhatsApp (se envía ahora desde el bot)"
          className="rounded-md p-1.5 text-green-600 transition hover:bg-green-50 disabled:opacity-50"
        >
          <MessageCircle className="h-4 w-4" />
        </button>
      );
    }
    return (
      <div>
        <Button variant="success" size={size} onClick={() => void handleRecordar()} isLoading={sending}>
          <MessageCircle className="mr-1.5 inline h-4 w-4" />
          Recordar por WhatsApp · {cantidadDesvios}
        </Button>
        {!resultado && <p className="mt-1 text-xs text-gray-500">Se envía ahora desde el bot.</p>}
        {resultado === 'enviado' && (
          <p className="mt-1 text-xs text-green-700">
            Pedido enviado a WhatsApp. No podemos confirmar que lo haya leído — vas a saber que llegó cuando responda.
          </p>
        )}
        {resultado === 'sin_ventana' && (
          <p className="mt-1 text-xs text-amber-700">El canal se cerró justo ahora. Recargá la página e intentá de nuevo.</p>
        )}
        {resultado === 'cooldown' && <p className="mt-1 text-xs text-amber-700">Ya se reclamó hace instantes.</p>}
        {resultado === 'fallido' && <p className="mt-1 text-xs text-red-700">No se pudo enviar. Probá de nuevo en un rato.</p>}
      </div>
    );
  }

  // Ventana cerrada: la plantilla farmaaudit_novedades sigue sin aprobar en
  // Meta, así que el bot no puede iniciar la conversación. El camino
  // principal hoy es que el auditor le escriba con su propio WhatsApp.
  const link = whatsappLink(estadoContacto.encargado_telefono, mensajeManual(sucursalNombre, cantidadDesvios));

  if (compact) {
    return (
      <IconLink href={link ?? '#'} title="El bot no puede escribirle — escribile vos por WhatsApp" className="text-green-600 hover:bg-green-50">
        <MessageCircle className="h-4 w-4" />
      </IconLink>
    );
  }

  return (
    <div>
      <a
        href={link ?? '#'}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 rounded-lg bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700"
      >
        <MessageCircle className="h-4 w-4" />
        Escribirle vos por WhatsApp
      </a>
      <p className="mt-1 text-xs text-gray-500">
        El bot no puede iniciar la conversación
        {diasSinAccion != null ? `: no te escribe hace ${diasSinAccion} días.` : '.'}
      </p>
    </div>
  );
}

import { useEffect, useMemo, useState } from 'react';
import { Check, Clock, MapPin, Paperclip, Search, Send, User, X } from 'lucide-react';
import { FeedbackState } from '../components/FeedbackState';
import { EvidenciaGaleria } from '../components/EvidenciaGaleria';
import { DesvioCorrectionReviewPanel } from '../components/desvio-detail';
import {
  getGestion,
  getDesvioEventos,
  updateGestion,
  enviarMensajeInterno,
  createDesvioEvento,
  revisarGestion,
  getNotificaciones,
  getResponsableActivo,
} from '../lib/api';
import { formatDate, formatDateTime, gestionStateLabel, getWhatsappUrl, timeSince } from '../lib/utils';
import { useAuth } from '../hooks/useAuth';
import type { DesvioBandeja, DesvioEvento, Gestion, GestionState, Notificacion, Severidad } from '../types';
import { toast } from 'sonner';
import { validateResolutionForm } from '../lib/validation';

interface DesvioCard extends Gestion {
  eventos: DesvioEvento[];
}

type GroupBy = 'estado' | 'sucursal' | 'none';
type DetailTab = 'revision' | 'actividad' | 'plan' | 'evidencias' | 'detalle';
type SlaStatus = 'overdue' | 'today' | 'soon' | 'ok' | 'closed' | 'paused';

const ESTADOS: GestionState[] = ['Vencida', 'Abierta', 'En_proceso', 'En_revision', 'En_gestion_terceros', 'Resuelta', 'Cerrada'];
const SEVERIDADES: Severidad[] = ['Alta', 'Media', 'Baja'];

// Que estados entran en cada bandeja. 'decidir' es lo unico que espera una
// accion del auditor; el resto esta esperando al responsable o ya cerro.
// Sin bandeja (uso standalone de la pagina) se ven todos, como antes.
const ESTADOS_POR_BANDEJA: Record<DesvioBandeja, GestionState[]> = {
  decidir: ['En_revision'],
  esperando: ['Vencida', 'Abierta', 'En_proceso'],
  cerrado: ['En_gestion_terceros', 'Resuelta', 'Cerrada'],
};

function filterChipLabel(estado: GestionState): string {
  return estado === 'En_revision' ? 'Pendiente de revision' : gestionStateLabel(estado);
}

const tokens = {
  navy: '#1E3A6D',
  orange: '#F15A29',
  green: '#2A9D5F',
  ink: '#0F172A',
  muted: '#64748B',
  line: '#E5E7EB',
  state: {
    Vencida: { bg: '#FEE2E2', fg: '#991B1B', dot: '#DC2626' },
    Abierta: { bg: '#E0EAFF', fg: '#1E3A6D', dot: '#1E3A6D' },
    En_proceso: { bg: '#FFF1E6', fg: '#9A3A12', dot: '#F15A29' },
    En_revision: { bg: '#DCFCE7', fg: '#166534', dot: '#16A34A' },
    En_gestion_terceros: { bg: '#F1F4F9', fg: '#475467', dot: '#94A3B8' },
    Resuelta: { bg: '#E7F6EC', fg: '#1E6F3D', dot: '#2A9D5F' },
    Cerrada: { bg: '#F1F4F9', fg: '#475467', dot: '#667085' },
  } satisfies Record<GestionState, { bg: string; fg: string; dot: string }>,
  severity: {
    Alta: { bar: '#DC2626', soft: '#FEE2E2', fg: '#991B1B' },
    Media: { bar: '#D97706', soft: '#FEF3C7', fg: '#92400E' },
    Baja: { bar: '#0EA5E9', soft: '#E0F2FE', fg: '#075985' },
  } satisfies Record<Severidad, { bar: string; soft: string; fg: string }>,
  sla: {
    overdue: { bg: '#FEE2E2', fg: '#991B1B', dot: '#DC2626' },
    today: { bg: '#FFE5D6', fg: '#9A3A12', dot: '#F15A29' },
    soon: { bg: '#FEF3C7', fg: '#92400E', dot: '#D97706' },
    ok: { bg: '#F1F4F9', fg: '#344054', dot: '#94A3B8' },
    closed: { bg: '#E7F6EC', fg: '#1E6F3D', dot: '#2A9D5F' },
    paused: { bg: '#F1F4F9', fg: '#475467', dot: '#94A3B8' },
  } satisfies Record<SlaStatus, { bg: string; fg: string; dot: string }>,
};

function WhatsappIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
      <path d="M17.6 14.3c-.3-.1-1.7-.8-2-.9-.3-.1-.5-.1-.7.1-.2.3-.7.9-.9 1.1-.2.2-.3.2-.6.1-1.6-.8-2.6-1.4-3.7-3.2-.3-.5.3-.5.8-1.5.1-.2.1-.4 0-.5-.1-.1-.7-1.6-.9-2.2-.2-.6-.5-.5-.7-.5h-.6c-.2 0-.5.1-.8.4-.3.3-1 1-1 2.5s1.1 2.9 1.2 3.1c.1.2 2.1 3.2 5.1 4.5 1.9.8 2.6.9 3.5.7.6-.1 1.7-.7 2-1.4.3-.7.3-1.2.2-1.4-.1-.1-.3-.2-.6-.4zM12 2C6.5 2 2 6.5 2 12c0 1.8.5 3.5 1.3 4.9L2 22l5.3-1.4c1.4.8 2.9 1.2 4.7 1.2 5.5 0 10-4.5 10-10S17.5 2 12 2z" />
    </svg>
  );
}

function computeSla(desvio: Gestion): { status: SlaStatus; label: string; days: number } {
  if (desvio.estado === 'Resuelta' || desvio.estado === 'Cerrada') {
    return { status: 'closed', label: 'Completado', days: 0 };
  }
  if (desvio.estado === 'En_gestion_terceros') {
    return { status: 'paused', label: 'Pausado · depende de terceros', days: 0 };
  }
  if (desvio.estado === 'En_revision') {
    return { status: 'paused', label: 'Corregido, en revision', days: 0 };
  }

  const due = new Date(desvio.plazo_fecha);
  const today = new Date();
  due.setHours(0, 0, 0, 0);
  today.setHours(0, 0, 0, 0);
  const days = Math.round((due.getTime() - today.getTime()) / 86_400_000);

  if (days < 0) return { status: 'overdue', label: `Vencido hace ${Math.abs(days)}d`, days };
  if (days === 0) return { status: 'today', label: 'Vence hoy', days };
  if (days <= 2) return { status: 'soon', label: `Vence en ${days}d`, days };
  return { status: 'ok', label: `${days}d restantes`, days };
}

function normalize(value: string | null | undefined) {
  return (value || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

function EstadoBadge({ estado, size = 'md' }: { estado: GestionState; size?: 'sm' | 'md' }) {
  const color = tokens.state[estado];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md font-bold uppercase tracking-wide ${size === 'sm' ? 'px-2 py-1 text-[11px]' : 'px-3 py-1.5 text-xs'}`}
      style={{ background: color.bg, color: color.fg }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color.dot }} />
      {gestionStateLabel(estado)}
    </span>
  );
}

function CorrectionBadge({ count, onClick, size = 'md' }: { count: number; onClick: () => void; size?: 'sm' | 'md' }) {
  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className={`inline-flex items-center gap-1.5 rounded-md font-bold uppercase tracking-wide transition hover:brightness-95 ${size === 'sm' ? 'px-2 py-1 text-[11px]' : 'px-3 py-1.5 text-xs'}`}
      style={{ background: tokens.state.En_revision.bg, color: tokens.state.En_revision.fg }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: tokens.state.En_revision.dot }} />
      Corregido
      {count > 0 && (
        <span className="rounded-full bg-white/70 px-1.5 py-0.5 text-[10px] font-black">{count}</span>
      )}
    </button>
  );
}

function SeveridadBadge({ severidad }: { severidad: Severidad }) {
  const color = tokens.severity[severidad];
  return (
    <span className="inline-flex items-center gap-2 text-sm font-semibold" style={{ color: color.fg }}>
      <span className="h-7 w-1 rounded-full" style={{ background: color.bar }} />
      {severidad}
    </span>
  );
}

function SlaPill({ desvio, large = false }: { desvio: Gestion; large?: boolean }) {
  const sla = computeSla(desvio);
  const color = tokens.sla[sla.status];
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full font-semibold ${large ? 'px-4 py-2 text-sm' : 'px-3 py-1.5 text-xs'}`}
      style={{ background: color.bg, color: color.fg }}
    >
      <span className="h-2 w-2 rounded-full" style={{ background: color.dot }} />
      {sla.label}
    </span>
  );
}

function FilterChip({
  active,
  children,
  count,
  danger,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  count?: number;
  danger?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex min-h-10 items-center gap-2 rounded-lg border px-4 text-sm font-semibold transition hover:bg-slate-50"
      style={{
        borderColor: active ? tokens.navy : '#D0D5DD',
        background: active ? tokens.navy : '#fff',
        color: active ? '#fff' : danger ? '#991B1B' : '#344054',
      }}
    >
      {children}
      {count != null && (
        <span
          className="rounded-full px-2 py-0.5 text-xs font-bold"
          style={{
            background: active ? 'rgba(255,255,255,.18)' : danger ? '#FEE2E2' : '#F1F4F9',
            color: active ? '#fff' : danger ? '#991B1B' : '#475467',
          }}
        >
          {count}
        </span>
      )}
    </button>
  );
}

function SelectBox({ checked, onClick }: { checked: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className="flex h-5 w-5 items-center justify-center rounded border transition"
      style={{ borderColor: checked ? tokens.navy : '#CBD5E1', background: checked ? tokens.navy : '#fff' }}
      aria-label={checked ? 'Quitar seleccion' : 'Seleccionar'}
    >
      {checked && <Check className="h-4 w-4" />}
    </button>
  );
}

function GroupHeader({ label, count, accent, pendingReview }: { label: string; count: number; accent: string; pendingReview?: number }) {
  return (
    <div className="sticky top-[145px] z-10 flex items-center gap-3 border-y border-slate-200 bg-slate-50 px-4 py-2 text-xs font-bold uppercase tracking-wide text-slate-600 lg:top-[137px]">
      <span className="ml-9 h-2 w-2 rounded-full" style={{ background: accent }} />
      <span>{label}</span>
      <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs tracking-normal">{count}</span>
      {!!pendingReview && (
        <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-bold tracking-normal" style={{ background: tokens.state.En_revision.bg, color: tokens.state.En_revision.fg }}>
          {pendingReview} pendiente{pendingReview > 1 ? 's' : ''} de revision
        </span>
      )}
    </div>
  );
}

function Timeline({ eventos }: { eventos: DesvioEvento[] }) {
  if (eventos.length === 0) {
    return <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">Sin actividad registrada todavia.</div>;
  }

  const eventColor: Record<string, string> = {
    creacion: tokens.navy,
    contacto: tokens.orange,
    respuesta: tokens.navy,
    cierre: tokens.green,
    nota: '#64748B',
    evidencia: tokens.green,
    mensaje: '#475467',
    rechazo: '#DC2626',
  };

  return (
    <div className="relative pl-9">
      <div className="absolute left-[13px] top-1 bottom-1 w-0.5 bg-slate-200" />
      <div className="space-y-4">
        {eventos.map((evento) => {
          const color = eventColor[evento.tipo] || '#64748B';
          return (
            <div key={evento.id} className="relative">
              <div className="absolute -left-9 top-0 flex h-7 w-7 items-center justify-center rounded-full border-2 bg-white text-xs font-bold" style={{ borderColor: color, color }}>
                {evento.tipo === 'cierre' ? '✓' : evento.tipo === 'contacto' ? '↗' : '•'}
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-3">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-bold text-slate-950">{evento.actor_nombre || 'Sistema'}</span>
                  <span className="text-slate-400">·</span>
                  <span className="font-bold uppercase tracking-wide" style={{ color }}>{evento.tipo}</span>
                  <span className="ml-auto text-slate-400">{formatDateTime(evento.created_at)}</span>
                </div>
                <p className="mt-1 text-sm leading-6 text-slate-700">{evento.comentario}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Fact({ icon, label, value, sub, tone }: { icon: React.ReactNode; label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-400">
        {icon}
        {label}
      </div>
      <div className="text-sm font-bold text-slate-950">{value || '-'}</div>
      {sub && <div className="mt-0.5 text-sm" style={{ color: tone || '#64748B' }}>{sub}</div>}
    </div>
  );
}

function ResolveModal({
  desvio,
  comment,
  evidenceText,
  evidenceUrl,
  submitting,
  error,
  onCommentChange,
  onEvidenceTextChange,
  onEvidenceUrlChange,
  onCancel,
  onSubmit,
}: {
  desvio: DesvioCard;
  comment: string;
  evidenceText: string;
  evidenceUrl: string;
  submitting: boolean;
  error: string;
  onCommentChange: (value: string) => void;
  onEvidenceTextChange: (value: string) => void;
  onEvidenceUrlChange: (value: string) => void;
  onCancel: () => void;
  onSubmit: (event: React.FormEvent) => void;
}) {
  return (
    <>
      <button type="button" aria-label="Cerrar" onClick={onCancel} className="fixed inset-0 z-50 cursor-default bg-slate-950/40" />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onCancel}>
        <form
          onSubmit={onSubmit}
          onClick={(event) => event.stopPropagation()}
          className="w-full max-w-lg rounded-lg bg-white p-6 shadow-2xl"
        >
          <h3 className="text-lg font-bold text-slate-950">Marcar como resuelta</h3>
          <p className="mt-1 text-sm text-slate-500">
            {desvio.id_gestion} · {desvio.sucursal} — describi que hizo el responsable para resolver el desvio.
          </p>

          <label className="mt-4 block text-sm font-medium text-slate-700">
            Comentario de resolución *
            <textarea
              autoFocus
              value={comment}
              onChange={(event) => onCommentChange(event.target.value)}
              rows={3}
              required
              placeholder="Describi que hizo el responsable para resolver el desvio"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </label>

          <label className="mt-3 block text-sm font-medium text-slate-700">
            Evidencia (texto)
            <input
              type="text"
              value={evidenceText}
              onChange={(event) => onEvidenceTextChange(event.target.value)}
              placeholder="Numero de remito, descripcion de foto, etc. (opcional)"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </label>

          <label className="mt-3 block text-sm font-medium text-slate-700">
            URL de evidencia
            <input
              type="url"
              value={evidenceUrl}
              onChange={(event) => onEvidenceUrlChange(event.target.value)}
              placeholder="https:// (opcional)"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </label>

          {error && <p className="mt-3 text-sm font-medium text-red-600">{error}</p>}

          <div className="mt-5 flex justify-end gap-2">
            <button type="button" onClick={onCancel} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50">
              Cancelar
            </button>
            <button
              type="submit"
              disabled={submitting || !comment.trim()}
              className="rounded-lg px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
              style={{ background: submitting || !comment.trim() ? undefined : tokens.navy }}
            >
              {submitting ? 'Guardando...' : 'Marcar como resuelta'}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}

function DetailDrawer({
  desvio,
  tab,
  setTab,
  comentario,
  setComentario,
  sending,
  updatingId,
  reviewUpdating,
  onClose,
  onStateChange,
  onResolve,
  onComment,
  onWhatsapp,
  onAprobar,
  onRechazar,
  onEnGestionTerceros,
}: {
  desvio: DesvioCard;
  tab: DetailTab;
  setTab: (tab: DetailTab) => void;
  comentario: string;
  setComentario: (value: string) => void;
  sending: boolean;
  updatingId: string | null;
  reviewUpdating: boolean;
  onClose: () => void;
  onStateChange: (id: string, state: GestionState) => void;
  onResolve: (desvio: DesvioCard) => void;
  onComment: (id: string) => void;
  onWhatsapp: (desvio: Gestion) => void;
  onAprobar: (desvio: DesvioCard) => void;
  onRechazar: (desvio: DesvioCard, motivo: string) => void;
  onEnGestionTerceros: (desvio: DesvioCard, motivo: string) => void;
}) {
  const sla = computeSla(desvio);
  const visibleTabs: { key: DetailTab; label: string }[] = [
    ...(desvio.estado === 'En_revision' ? [{ key: 'revision' as const, label: 'Revision' }] : []),
    { key: 'actividad', label: `Actividad · ${desvio.eventos.length}` },
    { key: 'plan', label: 'Plan de accion' },
    { key: 'evidencias', label: 'Evidencias' },
    { key: 'detalle', label: 'Detalle' },
  ];

  return (
    <>
      <button type="button" aria-label="Cerrar detalle" onClick={onClose} className="fixed inset-0 z-40 cursor-default bg-slate-950/35" />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-white shadow-2xl sm:w-[640px]">
        <div className="border-b border-slate-200 px-6 py-5">
          <div className="mb-4 flex items-center gap-3">
            <span className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-bold" style={{ background: tokens.severity[desvio.severidad].soft, color: tokens.severity[desvio.severidad].fg }}>
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: tokens.severity[desvio.severidad].bar }} />
              {desvio.severidad}
            </span>
            <EstadoBadge estado={desvio.estado} />
            <SlaPill desvio={desvio} large />
            <button type="button" onClick={onClose} className="ml-auto rounded-md p-2 text-slate-500 hover:bg-slate-100" aria-label="Cerrar">
              <X className="h-4.5 w-4.5" />
            </button>
          </div>
          <div className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">{desvio.id_gestion} · {desvio.id_reporte || 'Sin reporte'}</div>
          <h2 className="text-2xl font-bold leading-tight text-slate-950">{desvio.desvio}</h2>
        </div>

        <div className="grid grid-cols-1 gap-4 border-b border-slate-200 px-6 py-4 sm:grid-cols-3">
          <Fact icon={<MapPin className="h-3.5 w-3.5" />} label="Sucursal" value={desvio.sucursal} sub={desvio.id_sucursal} />
          <Fact icon={<User className="h-3.5 w-3.5" />} label="Responsable" value={desvio.responsable} sub="Encargado/a" />
          <Fact icon={<Clock className="h-3.5 w-3.5" />} label="Plazo" value={formatDate(desvio.plazo_fecha)} sub={sla.label} tone={tokens.sla[sla.status].fg} />
        </div>

        <div className="flex flex-wrap gap-2 border-b border-slate-200 px-6 py-4">
          <button type="button" onClick={() => onWhatsapp(desvio)} className="inline-flex min-h-11 items-center gap-2 rounded-lg px-4 text-sm font-bold text-white" style={{ background: tokens.orange }}>
            <WhatsappIcon />
            Contactar por WhatsApp
          </button>
          {desvio.estado !== 'Resuelta' && desvio.estado !== 'Cerrada' && (
            <button type="button" disabled={updatingId === desvio.id_gestion} onClick={() => onResolve(desvio)} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-emerald-200 bg-white px-4 text-sm font-bold text-emerald-700 disabled:opacity-60">
              <Check className="h-4 w-4" />
              Marcar resuelta
            </button>
          )}
          {desvio.estado !== 'En_proceso' && desvio.estado !== 'Resuelta' && desvio.estado !== 'Cerrada' && (
            <button type="button" disabled={updatingId === desvio.id_gestion} onClick={() => onStateChange(desvio.id_gestion, 'En_proceso')} className="min-h-11 rounded-lg border border-slate-300 bg-white px-4 text-sm font-bold text-slate-700 disabled:opacity-60">
              En proceso
            </button>
          )}
          <button type="button" className="ml-auto min-h-11 rounded-lg border border-slate-300 bg-white px-4 text-sm font-bold text-slate-700">
            Reasignar
          </button>
        </div>

        <div className="flex border-b border-slate-200 px-6">
          {visibleTabs.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setTab(item.key)}
              className="mr-6 border-b-2 px-1 py-4 text-sm font-bold transition"
              style={{ borderColor: tab === item.key ? tokens.navy : 'transparent', color: tab === item.key ? tokens.navy : '#64748B' }}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto bg-slate-50 px-6 py-5">
          {tab === 'revision' && (
            <DesvioCorrectionReviewPanel
              gestion={desvio}
              eventos={desvio.eventos}
              updating={reviewUpdating}
              onAprobar={() => onAprobar(desvio)}
              onRechazar={(motivo) => onRechazar(desvio, motivo)}
              onEnGestionTerceros={(motivo) => onEnGestionTerceros(desvio, motivo)}
            />
          )}
          {tab === 'actividad' && <Timeline eventos={desvio.eventos} />}
          {tab === 'plan' && (
            <div className="rounded-lg border border-slate-200 bg-white p-5">
              <div className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">Plan de accion acordado</div>
              <p className="text-sm leading-6 text-slate-950">{desvio.plan_accion || 'Aun no se cargo un plan de accion para este desvio.'}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button type="button" className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700">Editar plan</button>
                <button type="button" className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700">Solicitar a sucursal</button>
              </div>
            </div>
          )}
          {tab === 'evidencias' && <EvidenciaGaleria idGestion={desvio.id_gestion} eventos={desvio.eventos} />}
          {tab === 'detalle' && (
            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
              {[
                ['ID gestion', desvio.id_gestion],
                ['Reporte origen', desvio.id_reporte],
                ['Sucursal', `${desvio.sucursal} (${desvio.id_sucursal})`],
                ['Responsable', `${desvio.responsable} · ${desvio.tel_responsable || 'sin telefono'}`],
                ['Severidad', desvio.severidad],
                ['Estado', gestionStateLabel(desvio.estado)],
                ['Creado', desvio.created_at ? formatDateTime(desvio.created_at) : '-'],
                ['Actualizado', desvio.updated_at ? formatDateTime(desvio.updated_at) : '-'],
              ].map(([label, value]) => (
                <div key={label} className="grid grid-cols-[140px_1fr] border-b border-slate-100 px-4 py-3 text-sm last:border-b-0">
                  <div className="font-semibold text-slate-400">{label}</div>
                  <div className="font-semibold text-slate-950">{value || '-'}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-end gap-3 border-t border-slate-200 bg-white p-4">
          <textarea
            value={comentario}
            onChange={(event) => setComentario(event.target.value)}
            rows={2}
            placeholder={`Comentar en ${desvio.id_gestion}...`}
            className="min-h-[54px] flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
          <button type="button" className="rounded-lg p-3 text-slate-500 hover:bg-slate-100" aria-label="Adjuntar evidencia">
            <Paperclip className="h-4.5 w-4.5" />
          </button>
          <button
            type="button"
            onClick={() => onComment(desvio.id_gestion)}
            disabled={sending || !comentario.trim()}
            className="inline-flex min-h-12 items-center gap-2 rounded-lg px-5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-200"
            style={{ background: comentario.trim() ? tokens.orange : undefined }}
          >
            <Send className="h-4 w-4" />
            Enviar
          </button>
        </div>
      </aside>
    </>
  );
}

export function DesviosGestionPanel({
  bandeja,
}: {
  bandeja?: DesvioBandeja;
}) {
  const { user, profile } = useAuth();
  const [desvios, setDesvios] = useState<DesvioCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [estadoFilter, setEstadoFilter] = useState<'' | GestionState>('');
  const [severidadFilter, setSeveridadFilter] = useState<'' | Severidad>('');
  const [searchText, setSearchText] = useState('');
  const [groupBy, setGroupBy] = useState<GroupBy>('estado');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [openId, setOpenId] = useState<string | null>(null);
  const [drawerTab, setDrawerTab] = useState<DetailTab>('actividad');
  const [comentario, setComentario] = useState('');
  const [sending, setSending] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [resolvingDesvio, setResolvingDesvio] = useState<DesvioCard | null>(null);
  const [resolveComment, setResolveComment] = useState('');
  const [resolveEvidenceText, setResolveEvidenceText] = useState('');
  const [resolveEvidenceUrl, setResolveEvidenceUrl] = useState('');
  const [resolveError, setResolveError] = useState('');
  const [resolving, setResolving] = useState(false);
  const [notifByGestion, setNotifByGestion] = useState<Map<string, Notificacion[]>>(new Map());
  const [reviewUpdating, setReviewUpdating] = useState(false);

  // Carga inicial. El primer statement es el await a proposito: el estado ya
  // arranca en loading, y volver a setearlo de forma sincronica dentro del
  // efecto dispara un render en cascada. `cancelled` evita escribir estado si
  // el panel se desmonto mientras la carga estaba en vuelo.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [data, notificaciones] = await Promise.all([getGestion(), getNotificaciones().catch(() => [])]);
        const enriched = await Promise.all(
          data.map(async (gestion) => ({
            ...gestion,
            eventos: await getDesvioEventos(gestion.id_gestion),
          })),
        );
        if (cancelled) return;
        setDesvios(enriched);

        const byGestion = new Map<string, Notificacion[]>();
        notificaciones
          .filter((notificacion) => notificacion.tipo === 'encargado_respondio')
          .forEach((notificacion) => {
            byGestion.set(notificacion.id_gestion, [...(byGestion.get(notificacion.id_gestion) || []), notificacion]);
          });
        setNotifByGestion(byGestion);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Error al cargar desvios');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const estadosVisibles = useMemo(
    () => (bandeja ? ESTADOS_POR_BANDEJA[bandeja] : ESTADOS),
    [bandeja],
  );

  const enBandeja = useMemo(
    () => (bandeja ? desvios.filter((desvio) => estadosVisibles.includes(desvio.estado)) : desvios),
    [desvios, bandeja, estadosVisibles],
  );

  // Al abrir otro desvio se limpia el borrador de comentario y el drawer
  // arranca en la pestaña que corresponde. Se ajusta durante el render, no en
  // un efecto, para no mostrar un frame con el comentario del desvio anterior.
  const [prevOpenId, setPrevOpenId] = useState(openId);
  if (prevOpenId !== openId) {
    setPrevOpenId(openId);
    setComentario('');
    const opened = desvios.find((desvio) => desvio.id_gestion === openId);
    setDrawerTab(opened?.estado === 'En_revision' ? 'revision' : 'actividad');
  }

  const counts = useMemo(() => {
    const result = ESTADOS.reduce((acc, estado) => ({ ...acc, [estado]: 0 }), { total: enBandeja.length } as Record<GestionState | 'total', number>);
    enBandeja.forEach((desvio) => {
      result[desvio.estado] += 1;
    });
    return result;
  }, [enBandeja]);

  const filtered = useMemo(() => {
    const search = normalize(searchText);
    return enBandeja.filter((desvio) => {
      if (estadoFilter && desvio.estado !== estadoFilter) return false;
      if (severidadFilter && desvio.severidad !== severidadFilter) return false;
      if (!search) return true;

      return [
        desvio.id_gestion,
        desvio.id_reporte,
        desvio.desvio,
        desvio.sucursal,
        desvio.responsable,
      ].some((value) => normalize(value).includes(search));
    });
  }, [enBandeja, estadoFilter, severidadFilter, searchText]);

  const sortByPendingReview = (items: DesvioCard[]) =>
    [...items].sort((a, b) => {
      const aPending = a.estado === 'En_revision';
      const bPending = b.estado === 'En_revision';
      if (aPending && bPending) {
        return new Date(a.en_revision_desde || 0).getTime() - new Date(b.en_revision_desde || 0).getTime();
      }
      if (aPending) return -1;
      if (bPending) return 1;
      return 0;
    });

  const countPendingReview = (items: DesvioCard[]) => items.filter((desvio) => desvio.estado === 'En_revision').length;

  const groups = useMemo(() => {
    if (groupBy === 'none') {
      const items = sortByPendingReview(filtered);
      return [{ key: 'all', label: '', accent: tokens.navy, items, pendingReview: countPendingReview(items) }];
    }

    if (groupBy === 'sucursal') {
      const byBranch = new Map<string, DesvioCard[]>();
      filtered.forEach((desvio) => {
        byBranch.set(desvio.sucursal, [...(byBranch.get(desvio.sucursal) || []), desvio]);
      });
      return Array.from(byBranch.entries())
        .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))
        .map(([key, items]) => ({
          key,
          label: key,
          accent: tokens.navy,
          items: sortByPendingReview(items),
          pendingReview: countPendingReview(items),
        }));
    }

    const byState = new Map<GestionState, DesvioCard[]>();
    filtered.forEach((desvio) => {
      byState.set(desvio.estado, [...(byState.get(desvio.estado) || []), desvio]);
    });
    return estadosVisibles
      .filter((estado) => byState.has(estado))
      .map((estado) => ({
        key: estado,
        label: gestionStateLabel(estado),
        accent: tokens.state[estado].dot,
        items: sortByPendingReview(byState.get(estado) || []),
        pendingReview: 0,
      }));
  }, [filtered, groupBy, estadosVisibles]);

  const selectedDesvio = openId ? desvios.find((desvio) => desvio.id_gestion === openId) || null : null;
  const visibleIds = filtered.map((desvio) => desvio.id_gestion);
  const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selected.has(id));

  const toggleSelected = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    setSelected((current) => {
      const next = new Set(current);
      if (allSelected) visibleIds.forEach((id) => next.delete(id));
      else visibleIds.forEach((id) => next.add(id));
      return next;
    });
  };

  const handleStateChange = async (desvioId: string, newEstado: GestionState) => {
    const snapshot = desvios;
    setUpdatingId(desvioId);
    setDesvios((prev) => prev.map((desvio) => (desvio.id_gestion === desvioId ? { ...desvio, estado: newEstado } : desvio)));

    try {
      await updateGestion(desvioId, newEstado, profile?.nombre || user?.email || undefined);
      toast.success(`Desvio marcado como ${gestionStateLabel(newEstado)}`);
    } catch {
      setDesvios(snapshot);
      toast.error('Error al actualizar estado');
    } finally {
      setUpdatingId(null);
    }
  };

  const applyRevisionResult = async (desvio: DesvioCard, updatedGestion: Gestion) => {
    const eventos = await getDesvioEventos(desvio.id_gestion).catch(() => desvio.eventos);
    setDesvios((prev) =>
      prev.map((item) => (item.id_gestion === desvio.id_gestion ? { ...item, ...updatedGestion, eventos } : item)),
    );
    setNotifByGestion((prev) => {
      const next = new Map(prev);
      next.delete(desvio.id_gestion);
      return next;
    });
  };

  const handleAprobar = async (desvio: DesvioCard) => {
    setReviewUpdating(true);
    try {
      const updated = await revisarGestion({ idGestion: desvio.id_gestion, accion: 'aprobar' });
      await applyRevisionResult(desvio, updated);
      toast.success('Correccion aprobada');
      setDrawerTab('actividad');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo aprobar la correccion');
    } finally {
      setReviewUpdating(false);
    }
  };

  const handleRechazar = async (desvio: DesvioCard, motivo: string) => {
    setReviewUpdating(true);
    try {
      const updated = await revisarGestion({ idGestion: desvio.id_gestion, accion: 'rechazar', motivo });
      await applyRevisionResult(desvio, updated);
      toast.success('Correccion rechazada, se notifico al responsable');
      setDrawerTab('actividad');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo rechazar la correccion');
    } finally {
      setReviewUpdating(false);
    }
  };

  const handleEnGestionTerceros = async (desvio: DesvioCard, motivo: string) => {
    setReviewUpdating(true);
    try {
      const updated = await revisarGestion({ idGestion: desvio.id_gestion, accion: 'en_gestion_terceros', motivo });
      await applyRevisionResult(desvio, updated);
      toast.success('Desvio marcado como dependiente de terceros');
      setDrawerTab('actividad');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo actualizar el desvio');
    } finally {
      setReviewUpdating(false);
    }
  };

  const openResolveModal = (desvio: DesvioCard) => {
    setResolvingDesvio(desvio);
    setResolveComment('');
    setResolveEvidenceText('');
    setResolveEvidenceUrl('');
    setResolveError('');
  };

  const closeResolveModal = () => {
    if (resolving) return;
    setResolvingDesvio(null);
  };

  const handleResolveSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!resolvingDesvio) return;

    const validated = validateResolutionForm({
      resolutionComment: resolveComment,
      evidenceText: resolveEvidenceText,
      evidenceUrl: resolveEvidenceUrl,
    });
    if ('error' in validated) {
      setResolveError(validated.error);
      return;
    }

    const desvioId = resolvingDesvio.id_gestion;
    const actorName = profile?.nombre || user?.email || undefined;
    const evidence = validated.evidenceText?.trim() || null;
    const url = validated.evidenceUrl?.trim() || null;

    setResolving(true);
    setResolveError('');
    try {
      await updateGestion(desvioId, 'Resuelta', actorName);
      const respuestaEvento = await createDesvioEvento({
        id_gestion: desvioId,
        tipo: 'respuesta',
        comentario: validated.resolutionComment,
        actor_id: user?.id || null,
        actor_nombre: actorName || null,
        metadata: { estado: 'Resuelta', evidencia_texto: evidence, evidencia_url: url },
      });
      const newEventos = [respuestaEvento];

      if (evidence || url) {
        const evidenciaEvento = await createDesvioEvento({
          id_gestion: desvioId,
          tipo: 'evidencia',
          comentario: evidence || 'Evidencia adjunta por URL.',
          actor_id: user?.id || null,
          actor_nombre: actorName || null,
          metadata: { evidencia_url: url },
        });
        newEventos.push(evidenciaEvento);
      }

      setDesvios((prev) =>
        prev.map((desvio) =>
          desvio.id_gestion === desvioId
            ? { ...desvio, estado: 'Resuelta', eventos: [...desvio.eventos, ...newEventos] }
            : desvio,
        ),
      );
      toast.success('Desvio marcado como resuelto');
      setResolvingDesvio(null);
    } catch (err) {
      setResolveError(err instanceof Error ? err.message : 'No se pudo marcar como resuelto.');
    } finally {
      setResolving(false);
    }
  };

  const handleComment = async (desvioId: string) => {
    if (!comentario.trim()) return;

    setSending(true);
    try {
      const created = await enviarMensajeInterno({
        idGestion: desvioId,
        comentario: comentario.trim(),
        origen: 'auditor',
        actorId: user?.id || '',
        actorNombre: profile?.nombre || user?.email || 'Auditor',
      });
      setDesvios((prev) =>
        prev.map((desvio) => (desvio.id_gestion === desvioId ? { ...desvio, eventos: [...desvio.eventos, created] } : desvio)),
      );
      setComentario('');
      toast.success('Comentario enviado');
    } catch {
      toast.error('Error al enviar comentario');
    } finally {
      setSending(false);
    }
  };

  const handleWhatsapp = async (desvio: Gestion) => {
    let telefono = '';
    let nombre = '';
    try {
      const responsableActivo = await getResponsableActivo(desvio.id_gestion);
      telefono = responsableActivo.responsable?.telefono ?? '';
      nombre = responsableActivo.responsable?.nombre ?? '';
    } catch {
      // getWhatsappUrl abajo maneja el telefono vacio mostrando el mismo error.
    }
    const url = getWhatsappUrl(desvio, telefono, nombre);
    if (!url) {
      toast.error('Este desvio no tiene responsable activo con telefono');
      return;
    }
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
      <div className="min-h-screen bg-slate-100">
        <section className="sticky top-0 z-20 border-b border-slate-200 bg-white px-5 py-4 lg:px-8">
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
              <label className="relative min-w-0 flex-1">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400"><Search className="h-4.5 w-4.5" /></span>
                <input
                  value={searchText}
                  onChange={(event) => setSearchText(event.target.value)}
                  placeholder="Buscar por desvio, sucursal, responsable o ID..."
                  className="h-12 w-full rounded-lg border border-slate-300 bg-white pl-12 pr-4 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                />
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <span className="mr-1 text-xs font-bold uppercase tracking-wide text-slate-500">Vista</span>
                {[
                  ['estado', 'Por estado'],
                  ['sucursal', 'Por sucursal'],
                  ['none', 'Lista'],
                ].map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setGroupBy(key as GroupBy)}
                    className="min-h-10 rounded-lg border px-4 text-sm font-bold transition"
                    style={{ borderColor: groupBy === key ? tokens.navy : '#D0D5DD', background: groupBy === key ? tokens.navy : '#fff', color: groupBy === key ? '#fff' : '#344054' }}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {/* Con un solo estado en la bandeja los chips no filtran nada. */}
              {estadosVisibles.length > 1 && (
                <>
                  <span className="mr-1 text-xs font-bold uppercase tracking-wide text-slate-500">Estado</span>
                  <FilterChip active={estadoFilter === ''} count={counts.total} onClick={() => setEstadoFilter('')}>Todos</FilterChip>
                  {estadosVisibles.map((estado) => (
                    <FilterChip key={estado} active={estadoFilter === estado} count={counts[estado]} danger={estado === 'Vencida'} onClick={() => setEstadoFilter(estado)}>
                      {filterChipLabel(estado)}
                    </FilterChip>
                  ))}
                  <span className="mx-2 hidden h-6 w-px bg-slate-200 lg:block" />
                </>
              )}
              <span className="mr-1 text-xs font-bold uppercase tracking-wide text-slate-500">Severidad</span>
              <FilterChip active={severidadFilter === ''} onClick={() => setSeveridadFilter('')}>Todas</FilterChip>
              {SEVERIDADES.map((severidad) => (
                <FilterChip key={severidad} active={severidadFilter === severidad} onClick={() => setSeveridadFilter(severidad)}>
                  {severidad}
                </FilterChip>
              ))}
            </div>
          </div>
        </section>

        {selected.size > 0 && (
          <div className="sticky top-[145px] z-20 flex flex-wrap items-center gap-3 bg-slate-900 px-5 py-3 text-sm font-bold text-white lg:top-[137px] lg:px-8">
            <span>{selected.size} seleccionados</span>
            <button type="button" className="rounded-md bg-white/10 px-3 py-2 hover:bg-white/20">Reasignar</button>
            <button type="button" className="rounded-md bg-white/10 px-3 py-2 hover:bg-white/20">Exportar</button>
            <button type="button" onClick={() => setSelected(new Set())} className="ml-auto rounded-md px-3 py-2 hover:bg-white/10">Cancelar</button>
          </div>
        )}

        {loading && <div className="px-6 py-10"><FeedbackState title="Cargando desvíos..." tone="loading" /></div>}
        {error && <div className="px-6 py-10"><FeedbackState title={error} tone="error" /></div>}
        {!loading && !error && desvios.length === 0 && (
          <div className="px-6 py-10">
            <FeedbackState title="No hay desvios en gestion." description="Cuando los auditores aprueben borradores, apareceran aqui para su seguimiento." />
          </div>
        )}

        {!loading && !error && desvios.length > 0 && (
          <div className="bg-white">
            <div className="hidden min-w-[1040px] grid-cols-[44px_150px_minmax(280px,1fr)_250px_190px_150px_76px] items-center border-b border-slate-200 bg-white px-4 py-3 text-xs font-bold uppercase tracking-wide text-slate-500 lg:grid">
              <div><SelectBox checked={allSelected} onClick={toggleAll} /></div>
              <div>Severidad</div>
              <div>Desvio</div>
              <div>Sucursal · Responsable</div>
              <div>SLA</div>
              <div>Estado</div>
              <div className="text-right">Acciones</div>
            </div>

            {filtered.length === 0 && (
              <div className="px-6 py-16 text-center">
                <div className="text-lg font-bold text-slate-900">Sin resultados</div>
                <div className="mt-1 text-sm text-slate-500">Ajusta los filtros o limpia la busqueda.</div>
              </div>
            )}

            {groups.map((group) => (
              <div key={group.key}>
                {group.label && <GroupHeader label={group.label} count={group.items.length} accent={group.accent} pendingReview={group.pendingReview} />}
                {group.items.map((desvio) => {
                  const selectedRow = selected.has(desvio.id_gestion);
                  return (
                    <article
                      key={desvio.id_gestion}
                      onClick={() => setOpenId(desvio.id_gestion)}
                      className="grid cursor-pointer grid-cols-[32px_1fr] gap-3 border-b border-slate-100 bg-white px-4 py-4 transition hover:bg-slate-50 lg:min-w-[1040px] lg:grid-cols-[44px_150px_minmax(280px,1fr)_250px_190px_150px_76px] lg:items-center lg:gap-0 lg:py-0"
                    >
                      <div className="pt-1 lg:pt-0"><SelectBox checked={selectedRow} onClick={() => toggleSelected(desvio.id_gestion)} /></div>
                      <div className="lg:hidden">
                        <div className="mb-3 flex flex-wrap items-center gap-2">
                          <SeveridadBadge severidad={desvio.severidad} />
                          {desvio.estado === 'En_revision' ? (
                            <CorrectionBadge count={(notifByGestion.get(desvio.id_gestion) || []).length} size="sm" onClick={() => setOpenId(desvio.id_gestion)} />
                          ) : (
                            <EstadoBadge estado={desvio.estado} size="sm" />
                          )}
                          <SlaPill desvio={desvio} />
                        </div>
                        <div className="font-semibold text-slate-950">{desvio.desvio}</div>
                        <div className="mt-1 text-sm text-slate-500">{desvio.id_gestion} · {desvio.sucursal} · {desvio.responsable}</div>
                      </div>

                      <div className="hidden lg:block"><SeveridadBadge severidad={desvio.severidad} /></div>
                      <div className="hidden min-w-0 py-3 pr-4 lg:block">
                        <div className="truncate font-semibold text-slate-950">{desvio.desvio}</div>
                        <div className="mt-1 flex items-center gap-2 text-xs text-slate-400">
                          <span className="font-bold text-slate-500">{desvio.id_gestion}</span>
                          <span>·</span>
                          <span>{desvio.id_reporte || 'Sin reporte'}</span>
                          {desvio.eventos.length > 0 && <span className="rounded-full bg-orange-100 px-2 py-0.5 font-bold text-orange-700">{desvio.eventos.length} eventos</span>}
                        </div>
                      </div>
                      <div className="hidden min-w-0 py-3 pr-4 lg:block">
                        <div className="truncate font-semibold text-slate-950">{desvio.sucursal}</div>
                        <div className="mt-1 truncate text-xs text-slate-400">{desvio.responsable}</div>
                      </div>
                      <div className="hidden py-3 lg:block">
                        <SlaPill desvio={desvio} />
                        <div className="mt-1 text-xs text-slate-400">Plazo {formatDate(desvio.plazo_fecha)}</div>
                      </div>
                      <div className="hidden py-3 lg:block">
                        {desvio.estado === 'En_revision' ? (
                          <div>
                            <CorrectionBadge count={(notifByGestion.get(desvio.id_gestion) || []).length} size="sm" onClick={() => setOpenId(desvio.id_gestion)} />
                            {desvio.en_revision_desde && <div className="mt-1 text-xs text-slate-400">{timeSince(desvio.en_revision_desde)}</div>}
                          </div>
                        ) : (
                          <EstadoBadge estado={desvio.estado} size="sm" />
                        )}
                      </div>
                      <div className="hidden justify-end gap-1 py-3 lg:flex" onClick={(event) => event.stopPropagation()}>
                        <button type="button" onClick={() => handleWhatsapp(desvio)} className="rounded-md p-2 text-emerald-600 hover:bg-emerald-50" aria-label="Contactar por WhatsApp">
                          <WhatsappIcon />
                        </button>
                        {desvio.estado !== 'Resuelta' && desvio.estado !== 'Cerrada' && (
                          <button type="button" disabled={updatingId === desvio.id_gestion} onClick={() => openResolveModal(desvio)} className="rounded-md p-2 text-emerald-700 hover:bg-emerald-50 disabled:opacity-50" aria-label="Marcar resuelta">
                            <Check className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            ))}
          </div>
        )}

        {selectedDesvio && (
          <DetailDrawer
            desvio={selectedDesvio}
            tab={drawerTab}
            setTab={setDrawerTab}
            comentario={comentario}
            setComentario={setComentario}
            sending={sending}
            updatingId={updatingId}
            reviewUpdating={reviewUpdating}
            onClose={() => setOpenId(null)}
            onStateChange={(id, state) => void handleStateChange(id, state)}
            onResolve={openResolveModal}
            onComment={(id) => void handleComment(id)}
            onWhatsapp={handleWhatsapp}
            onAprobar={(desvio) => void handleAprobar(desvio)}
            onRechazar={(desvio, motivo) => void handleRechazar(desvio, motivo)}
            onEnGestionTerceros={(desvio, motivo) => void handleEnGestionTerceros(desvio, motivo)}
          />
        )}

        {resolvingDesvio && (
          <ResolveModal
            desvio={resolvingDesvio}
            comment={resolveComment}
            evidenceText={resolveEvidenceText}
            evidenceUrl={resolveEvidenceUrl}
            submitting={resolving}
            error={resolveError}
            onCommentChange={setResolveComment}
            onEvidenceTextChange={setResolveEvidenceText}
            onEvidenceUrlChange={setResolveEvidenceUrl}
            onCancel={closeResolveModal}
            onSubmit={(event) => void handleResolveSubmit(event)}
          />
        )}
      </div>
  );
}


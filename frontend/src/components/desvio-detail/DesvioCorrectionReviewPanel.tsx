import { useState } from 'react';
import { Check, Clock, X } from 'lucide-react';
import { EvidenciaGaleria } from '../EvidenciaGaleria';
import { formatDateTime, timeSince } from '../../lib/utils';
import type { DesvioEvento, Gestion } from '../../types';

interface DesvioCorrectionReviewPanelProps {
  gestion: Gestion;
  eventos: DesvioEvento[];
  updating: boolean;
  onAprobar: () => void;
  onRechazar: (motivo: string) => void;
  onEnGestionTerceros: (motivo: string) => void;
}

type PendingAction = 'rechazar' | 'en_gestion_terceros' | null;

export function DesvioCorrectionReviewPanel({
  gestion,
  eventos,
  updating,
  onAprobar,
  onRechazar,
  onEnGestionTerceros,
}: DesvioCorrectionReviewPanelProps) {
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [motivo, setMotivo] = useState('');

  const correctionEvents = eventos
    .filter((evento) => evento.metadata?.origen === 'sucursal' && (evento.tipo === 'evidencia' || evento.tipo === 'mensaje'))
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  const latest = correctionEvents[0];

  const closeInlineForm = () => {
    setPendingAction(null);
    setMotivo('');
  };

  const submitInlineForm = () => {
    if (!motivo.trim()) return;
    if (pendingAction === 'rechazar') onRechazar(motivo.trim());
    if (pendingAction === 'en_gestion_terceros') onEnGestionTerceros(motivo.trim());
    closeInlineForm();
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-bold text-emerald-800">Corregido por el responsable</span>
          {gestion.en_revision_desde && (
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700">
              <Clock className="h-3.5 w-3.5" />
              {timeSince(gestion.en_revision_desde)} esperando revision
            </span>
          )}
        </div>

        {latest ? (
          <div className="mt-3 rounded-lg border border-emerald-100 bg-white p-3">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span className="font-bold text-slate-900">{latest.actor_nombre || 'Encargado'}</span>
              <span>·</span>
              <span>{formatDateTime(latest.created_at)}</span>
            </div>
            <p className="mt-1 text-sm leading-6 text-slate-800">{latest.comentario}</p>
          </div>
        ) : (
          <p className="mt-3 text-sm text-emerald-700">Sin detalle de texto, revisa la evidencia fotografica.</p>
        )}
      </div>

      <EvidenciaGaleria idGestion={gestion.id_gestion} eventos={eventos} />

      {pendingAction ? (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <label className="block text-sm font-medium text-slate-700">
            {pendingAction === 'rechazar' ? 'Motivo del rechazo *' : 'Motivo (depende de terceros) *'}
            <textarea
              autoFocus
              value={motivo}
              onChange={(event) => setMotivo(event.target.value)}
              rows={3}
              placeholder={
                pendingAction === 'rechazar'
                  ? 'Que le falta corregir al responsable...'
                  : 'Ej: falta stock de droguería, obra pendiente, licencia del personal...'
              }
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </label>
          <div className="mt-3 flex justify-end gap-2">
            <button type="button" onClick={closeInlineForm} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50">
              Cancelar
            </button>
            <button
              type="button"
              disabled={updating || !motivo.trim()}
              onClick={submitInlineForm}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {pendingAction === 'rechazar' ? 'Confirmar rechazo' : 'Marcar depende de terceros'}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={updating}
            onClick={onAprobar}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-emerald-600 px-4 text-sm font-bold text-white disabled:opacity-60"
          >
            <Check className="h-4 w-4" />
            Aprobar cierre
          </button>
          <button
            type="button"
            disabled={updating}
            onClick={() => setPendingAction('rechazar')}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-red-200 bg-white px-4 text-sm font-bold text-red-700 disabled:opacity-60"
          >
            <X className="h-4 w-4" />
            Rechazar, reabrir
          </button>
          <button
            type="button"
            disabled={updating}
            onClick={() => setPendingAction('en_gestion_terceros')}
            className="min-h-11 rounded-lg border border-slate-300 bg-white px-4 text-sm font-bold text-slate-700 disabled:opacity-60"
          >
            Depende de terceros
          </button>
        </div>
      )}
    </div>
  );
}

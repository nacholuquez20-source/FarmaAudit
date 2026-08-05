import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { AppLayout } from '../components/AppLayout';
import { ChatMensajes } from '../components/ChatMensajes';
import { EvidenciaGaleria } from '../components/EvidenciaGaleria';
import { EvidenciaUploader } from '../components/EvidenciaUploader';
import { FeedbackState } from '../components/FeedbackState';
import {
  DesvioHeaderActions,
  DesvioInfoCard,
  DesvioResponsibleCard,
  DesvioResolutionPanel,
  DesvioTimeline,
} from '../components/desvio-detail';
import { useAuth } from '../hooks/useAuth';
import { useDesvioDetail } from '../hooks/useDesvioDetail';
import type { DesvioEvento, Gestion } from '../types';
import { notificarEncargado, resolveEvidenceUrl } from '../lib/api';
import { getWhatsappUrl } from '../lib/utils';
import { ResolutionFormSchema } from '../lib/validation';

function getDueState(gestion: Gestion): { label: string; className: string } {
  if (gestion.estado === 'Cerrada') {
    return { label: 'Cerrado', className: 'text-green-700' };
  }

  const dueDate = new Date(`${gestion.plazo_fecha}T23:59:59`);
  if (!Number.isNaN(dueDate.getTime()) && dueDate < new Date()) {
    return { label: 'Vencido', className: 'text-red-700' };
  }

  return { label: 'En plazo', className: 'text-gray-700' };
}

export default function DesvioDetail() {
  const { id } = useParams<{ id: string }>();
  const { user, profile, role } = useAuth();
  const { gestion, reporte, eventos, loading, error, eventsReady, reload, addEvento, updateEstado } = useDesvioDetail(id);
  const [actionError, setActionError] = useState('');
  const [actionMessage, setActionMessage] = useState('');
  const [contacting, setContacting] = useState(false);
  const [notifying, setNotifying] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [resolutionComment, setResolutionComment] = useState('');
  const [evidenceText, setEvidenceText] = useState('');
  const [evidenceUrl, setEvidenceUrl] = useState('');
  const [resolvedReporteFotoUrl, setResolvedReporteFotoUrl] = useState('');

  const whatsappUrl = useMemo(() => (gestion ? getWhatsappUrl(gestion) : null), [gestion]);
  const hasResolution = useMemo(
    () => eventos.some((evento) => evento.tipo === 'respuesta' || evento.tipo === 'evidencia'),
    [eventos]
  );

  const actorName = profile?.nombre || user?.email || null;
  const canManageEstado = role === 'admin' || role === 'auditor';

  useEffect(() => {
    let cancelled = false;
    const source = reporte?.foto_url;
    if (!source) {
      setResolvedReporteFotoUrl('');
      return;
    }

    const loadEvidenceUrl = async () => {
      try {
        const resolved = await resolveEvidenceUrl(source);
        if (!cancelled) setResolvedReporteFotoUrl(resolved);
      } catch {
        if (!cancelled) setResolvedReporteFotoUrl('');
      }
    };

    void loadEvidenceUrl();
    return () => {
      cancelled = true;
    };
  }, [reporte?.foto_url]);

  const addTimelineEvent = async (event: Omit<Parameters<typeof addEvento>[0], 'actor_id' | 'actor_nombre'>) => {
    return addEvento({
      ...event,
      actor_id: user?.id || null,
      actor_nombre: actorName,
    });
  };

  const handleContact = async () => {
    if (!gestion || !whatsappUrl) return;

    setContacting(true);
    setActionError('');
    setActionMessage('');

    try {
      await addTimelineEvent({
        id_gestion: gestion.id_gestion,
        tipo: 'contacto',
        comentario: `Contacto enviado a ${gestion.responsable || 'responsable'} por WhatsApp.`,
        metadata: {
          canal: 'whatsapp',
          telefono: gestion.tel_responsable,
        },
      });
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'No se pudo registrar el evento de contacto.');
    } finally {
      window.open(whatsappUrl, '_blank', 'noopener,noreferrer');
      setContacting(false);
    }
  };

  const handleNotifyEncargado = async () => {
    if (!gestion) return;

    setNotifying(true);
    setActionError('');
    setActionMessage('');

    try {
      await notificarEncargado({
        idGestion: gestion.id_gestion,
        telefonoEncargado: gestion.tel_responsable,
        descripcionDesvio: gestion.desvio,
        sucursal: gestion.sucursal,
      });
      try {
        await addTimelineEvent({
          id_gestion: gestion.id_gestion,
          tipo: 'contacto',
          comentario: `Encargado notificado por WhatsApp desde el bot.`,
          metadata: {
            canal: 'whatsapp_bot',
            telefono: gestion.tel_responsable,
          },
        });
      } catch (timelineError) {
        console.warn('WhatsApp notification sent, but timeline event failed:', timelineError);
      }
      setActionMessage('Encargado notificado por WhatsApp.');
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'No se pudo notificar al encargado.');
    } finally {
      setNotifying(false);
    }
  };

  const handleMarkInProgress = async () => {
    if (!gestion) return;

    setUpdatingStatus(true);
    setActionError('');
    setActionMessage('');

    try {
      await updateEstado('En_proceso');
      await addTimelineEvent({
        id_gestion: gestion.id_gestion,
        tipo: 'nota',
        comentario: 'El desvio fue marcado como en proceso.',
        metadata: { estado: 'En_proceso' },
      });
      setActionMessage('Desvio marcado como en proceso.');
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'No se pudo actualizar el estado.');
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleResolve = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!gestion) return;

    setUpdatingStatus(true);
    setActionError('');
    setActionMessage('');

    try {
      const validatedData = ResolutionFormSchema.parse({
        resolutionComment,
        evidenceText,
        evidenceUrl,
      });

      const comment = validatedData.resolutionComment;
      const evidence = validatedData.evidenceText?.trim() || null;
      const url = validatedData.evidenceUrl?.trim() || null;

      await updateEstado('Resuelta');
      await addTimelineEvent({
        id_gestion: gestion.id_gestion,
        tipo: 'respuesta',
        comentario: comment,
        metadata: {
          estado: 'Resuelta',
          evidencia_texto: evidence,
          evidencia_url: url,
        },
      });

      if (evidence || url) {
        await addTimelineEvent({
          id_gestion: gestion.id_gestion,
          tipo: 'evidencia',
          comentario: evidence || 'Evidencia adjunta por URL.',
          metadata: {
            evidencia_url: url,
          },
        });
      }

      setResolutionComment('');
      setEvidenceText('');
      setEvidenceUrl('');
      setActionMessage('Desvio marcado como resuelto.');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'No se pudo marcar como resuelto.';
      setActionError(message);
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleEvidenceUploaded = (evento: DesvioEvento) => {
    const signedUrl =
      evento.metadata && typeof evento.metadata.foto_url_signed === 'string' ? evento.metadata.foto_url_signed : '';
    if (signedUrl) {
      // Prefill the resolution form's evidence URL so it doesn't need to be copy-pasted by hand.
      setEvidenceUrl((current) => current || signedUrl);
    }
    reload();
  };

  const handleClose = async () => {
    if (!gestion) return;

    if (!hasResolution) {
      setActionError('No se puede cerrar sin una resolucion o evidencia previa.');
      return;
    }

    setUpdatingStatus(true);
    setActionError('');
    setActionMessage('');

    try {
      await updateEstado('Cerrada', actorName || undefined);
      await addTimelineEvent({
        id_gestion: gestion.id_gestion,
        tipo: 'cierre',
        comentario: 'El desvio fue cerrado con resolucion validada.',
        metadata: { estado: 'Cerrada' },
      });
      setActionMessage('Desvio cerrado correctamente.');
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'No se pudo cerrar el desvio.');
    } finally {
      setUpdatingStatus(false);
    }
  };

  if (loading) {
    return (
      <AppLayout title="Detalle de Desvio">
        <FeedbackState title="Cargando desvio..." tone="loading" />
      </AppLayout>
    );
  }

  if (error) {
    return (
      <AppLayout title="Detalle de Desvio">
        <FeedbackState title={error} tone="error" />
      </AppLayout>
    );
  }

  if (!gestion) {
    return (
      <AppLayout title="Detalle de Desvio">
        <FeedbackState title="No se encontro el desvio." />
      </AppLayout>
    );
  }

  const dueState = getDueState(gestion);

  return (
    <AppLayout title="Detalle de Desvio">
      <DesvioHeaderActions
        role={role}
        gestion={gestion}
        whatsappUrl={whatsappUrl}
        contacting={contacting}
        notifying={notifying}
        onContact={handleContact}
        onNotify={handleNotifyEncargado}
      />

      {actionError && (
        <div className="mb-6"><FeedbackState title={actionError} tone="warning" /></div>
      )}

      {actionMessage && (
        <div className="mb-6"><FeedbackState title={actionMessage} /></div>
      )}

      {!eventsReady && !actionError && (
        <div className="mb-6">
          <FeedbackState title="La trazabilidad necesita ejecutar frontend/docs/sql/etapa-2.sql en Supabase." tone="warning" />
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <DesvioInfoCard gestion={gestion} reporte={reporte} dueState={dueState} />

        <DesvioResponsibleCard gestion={gestion} />

        {canManageEstado && (
          <DesvioResolutionPanel
            gestion={gestion}
            updatingStatus={updatingStatus}
            resolutionComment={resolutionComment}
            evidenceText={evidenceText}
            evidenceUrl={evidenceUrl}
            onCommentChange={setResolutionComment}
            onEvidenceTextChange={setEvidenceText}
            onEvidenceUrlChange={setEvidenceUrl}
            onMarkInProgress={handleMarkInProgress}
            onClose={handleClose}
            onResolve={handleResolve}
          />
        )}

        <div className="lg:col-span-2">
          <ChatMensajes idGestion={gestion.id_gestion} eventos={eventos} onSent={reload} />
        </div>

        <div>
          <EvidenciaUploader idGestion={gestion.id_gestion} onUploaded={handleEvidenceUploaded} />
        </div>

        <div className="lg:col-span-3">
          <EvidenciaGaleria idGestion={gestion.id_gestion} eventos={eventos} />
        </div>

        <DesvioTimeline eventos={eventos} />

        <section className="rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Evidencias</h2>
          {reporte?.foto_url ? (
            <a
              href={resolvedReporteFotoUrl || reporte.foto_url}
              target="_blank"
              rel="noreferrer"
              className="block rounded-lg border border-gray-200 p-4 text-sm font-medium text-blue-600 hover:bg-blue-50"
            >
              {resolvedReporteFotoUrl ? 'Abrir foto del reporte' : 'Cargando foto del reporte...'}
            </a>
          ) : (
            <FeedbackState title="No hay evidencias asociadas todavia." />
          )}
          {reporte?.descripcion && (
            <div className="mt-4 rounded-lg bg-gray-50 p-4 text-sm text-gray-700">{reporte.descripcion}</div>
          )}
        </section>
      </div>
    </AppLayout>
  );
}

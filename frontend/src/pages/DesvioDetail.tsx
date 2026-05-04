import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AppLayout } from '../components/AppLayout';
import { ChatMensajes } from '../components/ChatMensajes';
import { EvidenciaGaleria } from '../components/EvidenciaGaleria';
import { EvidenciaUploader } from '../components/EvidenciaUploader';
import { FeedbackState } from '../components/FeedbackState';
import { useAuth } from '../hooks/useAuth';
import { useDesvioDetail } from '../hooks/useDesvioDetail';
import type { Gestion } from '../types';
import { notificarEncargado } from '../lib/api';
import { formatDate, formatDateTime, gestionStateColor, gestionStateLabel, severidadColor, getWhatsappUrl } from '../lib/utils';

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
  const navigate = useNavigate();
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

  const whatsappUrl = useMemo(() => (gestion ? getWhatsappUrl(gestion) : null), [gestion]);
  const hasResolution = useMemo(
    () => eventos.some((evento) => evento.tipo === 'respuesta' || evento.tipo === 'evidencia'),
    [eventos]
  );

  const actorName = profile?.nombre || user?.email || null;
  const canManageEstado = role === 'admin' || role === 'auditor';
  const backPath = role === 'sucursal' ? '/mis-desvios' : '/desvios';

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

    const comment = resolutionComment.trim();
    if (!comment) {
      setActionError('El comentario de resolucion es obligatorio.');
      return;
    }

    setUpdatingStatus(true);
    setActionError('');
    setActionMessage('');

    try {
      await updateEstado('Resuelta');
      await addTimelineEvent({
        id_gestion: gestion.id_gestion,
        tipo: 'respuesta',
        comentario: comment,
        metadata: {
          estado: 'Resuelta',
          evidencia_texto: evidenceText.trim() || null,
          evidencia_url: evidenceUrl.trim() || null,
        },
      });

      if (evidenceText.trim() || evidenceUrl.trim()) {
        await addTimelineEvent({
          id_gestion: gestion.id_gestion,
          tipo: 'evidencia',
          comentario: evidenceText.trim() || 'Evidencia adjunta por URL.',
          metadata: {
            evidencia_url: evidenceUrl.trim() || null,
          },
        });
      }

      setResolutionComment('');
      setEvidenceText('');
      setEvidenceUrl('');
      setActionMessage('Desvio marcado como resuelto.');
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'No se pudo marcar como resuelto.');
    } finally {
      setUpdatingStatus(false);
    }
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
        <FeedbackState title="Cargando desvio..." />
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
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <button
          type="button"
          onClick={() => navigate(backPath)}
          className="self-start text-sm font-medium text-blue-600 hover:text-blue-800"
        >
          Volver a desvios
        </button>
        <div className="flex gap-2">
          {canManageEstado && (
            <>
              <Link
                to={`/sucursales/${gestion.id_sucursal}`}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
              >
                Ver sucursal
              </Link>
              <button
                type="button"
                onClick={handleNotifyEncargado}
                disabled={!gestion.tel_responsable || notifying || gestion.estado === 'Cerrada'}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-300 disabled:text-gray-600"
              >
                {notifying ? 'Notificando...' : 'Notificar encargado'}
              </button>
              <button
                type="button"
                onClick={handleContact}
                disabled={!whatsappUrl || contacting}
                className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:bg-gray-300 disabled:text-gray-600"
              >
                {contacting ? 'Contactando...' : 'Contactar responsable'}
              </button>
            </>
          )}
        </div>
      </div>

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
        <section className="rounded-lg bg-white p-6 shadow lg:col-span-2">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <span className={`rounded px-3 py-1 text-xs font-semibold ${severidadColor(gestion.severidad)}`}>
              {gestion.severidad}
            </span>
            <span className={`rounded px-3 py-1 text-xs font-semibold ${gestionStateColor(gestion.estado)}`}>
              {gestionStateLabel(gestion.estado)}
            </span>
            <span className={`text-sm font-semibold ${dueState.className}`}>{dueState.label}</span>
          </div>

          <h2 className="mb-2 text-xl font-semibold text-gray-900">{gestion.sucursal}</h2>
          <p className="mb-6 text-gray-700">{gestion.desvio}</p>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <div className="text-sm text-gray-500">Area</div>
              <div className="font-medium">{reporte?.area || '-'}</div>
            </div>
            <div>
              <div className="text-sm text-gray-500">Vencimiento</div>
              <div className="font-medium">{formatDate(gestion.plazo_fecha)}</div>
            </div>
            <div>
              <div className="text-sm text-gray-500">Reporte origen</div>
              <div className="font-medium">{gestion.id_reporte || '-'}</div>
            </div>
            <div>
              <div className="text-sm text-gray-500">Fecha reporte</div>
              <div className="font-medium">{reporte?.fecha ? formatDate(reporte.fecha) : '-'}</div>
            </div>
          </div>

          <div className="mt-6 border-t border-gray-200 pt-6">
            <h3 className="mb-2 text-sm font-semibold text-gray-900">Plan de accion</h3>
            <p className="text-gray-700">{gestion.plan_accion || 'Sin plan de accion registrado.'}</p>
          </div>
        </section>

        <aside className="rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Responsable</h2>
          <div className="space-y-4">
            <div>
              <div className="text-sm text-gray-500">Nombre</div>
              <div className="font-medium">{gestion.responsable || '-'}</div>
            </div>
            <div>
              <div className="text-sm text-gray-500">Telefono</div>
              <div className="font-medium">{gestion.tel_responsable || 'Sin telefono'}</div>
            </div>
            <div>
              <div className="text-sm text-gray-500">Cierre</div>
              <div className="font-medium">{gestion.fecha_cierre ? formatDate(gestion.fecha_cierre) : 'Pendiente'}</div>
            </div>
            <div>
              <div className="text-sm text-gray-500">Cerrado por</div>
              <div className="font-medium">{gestion.cerrado_por || '-'}</div>
            </div>
          </div>
        </aside>

        {canManageEstado && (
        <section className="rounded-lg bg-white p-6 shadow lg:col-span-3">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Resolucion y cierre</h2>
              <p className="text-sm text-gray-500">Registra respuesta, evidencia y cierre con trazabilidad.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={handleMarkInProgress}
                disabled={updatingStatus || gestion.estado === 'En_proceso' || gestion.estado === 'Cerrada'}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:bg-gray-100 disabled:text-gray-400"
              >
                Marcar en proceso
              </button>
              <button
                type="button"
                onClick={handleClose}
                disabled={updatingStatus || gestion.estado === 'Cerrada'}
                className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:bg-gray-300 disabled:text-gray-600"
              >
                Cerrar desvio
              </button>
            </div>
          </div>

          <form onSubmit={handleResolve} className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <label className="text-sm font-medium text-gray-700 lg:col-span-3">
              Comentario de resolucion
              <textarea
                value={resolutionComment}
                onChange={(event) => setResolutionComment(event.target.value)}
                rows={3}
                required
                placeholder="Describe que hizo el responsable para resolver el desvio"
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
              />
            </label>

            <label className="text-sm font-medium text-gray-700 lg:col-span-2">
              Evidencia o respuesta
              <input
                type="text"
                value={evidenceText}
                onChange={(event) => setEvidenceText(event.target.value)}
                placeholder="Texto breve, numero de remito, descripcion de foto, etc."
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
              />
            </label>

            <label className="text-sm font-medium text-gray-700">
              URL de evidencia
              <input
                type="url"
                value={evidenceUrl}
                onChange={(event) => setEvidenceUrl(event.target.value)}
                placeholder="https://..."
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
              />
            </label>

            <div className="lg:col-span-3">
              <button
                type="submit"
                disabled={updatingStatus || gestion.estado === 'Cerrada'}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-300 disabled:text-gray-600"
              >
                {updatingStatus ? 'Guardando...' : 'Marcar como resuelto'}
              </button>
            </div>
          </form>
        </section>
        )}

        <div className="lg:col-span-2">
          <ChatMensajes idGestion={gestion.id_gestion} eventos={eventos} onSent={reload} />
        </div>

        <div>
          <EvidenciaUploader idGestion={gestion.id_gestion} onUploaded={reload} />
        </div>

        <div className="lg:col-span-3">
          <EvidenciaGaleria eventos={eventos} />
        </div>

        <section className="rounded-lg bg-white p-6 shadow lg:col-span-2">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Timeline</h2>
          {eventos.length === 0 ? (
            <FeedbackState title="Sin eventos registrados." />
          ) : (
            <div className="space-y-4">
              {eventos.map((evento) => (
                <div key={evento.id} className="border-l-2 border-blue-200 pl-4">
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                    <div className="font-medium capitalize text-gray-900">{evento.tipo.replace('_', ' ')}</div>
                    <div className="text-xs text-gray-500">{formatDateTime(evento.created_at)}</div>
                  </div>
                  <p className="mt-1 text-sm text-gray-700">{evento.comentario}</p>
                  {evento.actor_nombre && <div className="mt-1 text-xs text-gray-500">Por {evento.actor_nombre}</div>}
                  {typeof evento.metadata?.evidencia_url === 'string' && evento.metadata.evidencia_url && (
                    <a
                      href={evento.metadata.evidencia_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 inline-block text-sm font-medium text-blue-600 hover:text-blue-800"
                    >
                      Abrir evidencia
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Evidencias</h2>
          {reporte?.foto_url ? (
            <a
              href={reporte.foto_url}
              target="_blank"
              rel="noreferrer"
              className="block rounded-lg border border-gray-200 p-4 text-sm font-medium text-blue-600 hover:bg-blue-50"
            >
              Abrir foto del reporte
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

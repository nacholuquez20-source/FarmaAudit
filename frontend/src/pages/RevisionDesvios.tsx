import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { useDesviosBorrador } from '../hooks/useDesviosBorrador';
import { resolveEvidenceUrl, resolveEvidenceThumbUrl } from '../lib/api';
import { formatDateTime, severidadColor } from '../lib/utils';
import type { DesvioBorrador, DesvioBorradorEvidencia } from '../types';

function EvidencePreview({ evidencia, alt }: { evidencia?: DesvioBorradorEvidencia; alt: string }) {
  const [thumbUrl, setThumbUrl] = useState('');
  const [fullUrl, setFullUrl] = useState('');

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      if (!evidencia) {
        setThumbUrl('');
        setFullUrl('');
        return;
      }

      try {
        const thumb = await resolveEvidenceThumbUrl(evidencia);
        if (!cancelled) setThumbUrl(thumb);
      } catch {
        if (!cancelled) setThumbUrl('');
      }

      try {
        const full = await resolveEvidenceUrl(evidencia.path || evidencia.url);
        if (!cancelled) setFullUrl(full);
      } catch {
        if (!cancelled) setFullUrl('');
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [evidencia]);

  if (!evidencia || (!evidencia.path && !evidencia.url)) {
    return <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded border border-gray-200 bg-gray-50 text-xs text-gray-400">Sin foto</div>;
  }

  const displayUrl = thumbUrl || fullUrl;
  if (!displayUrl) {
    return <div className="h-24 w-24 shrink-0 rounded border border-gray-200 bg-gray-100" />;
  }

  return (
    <a href={fullUrl || displayUrl} target="_blank" rel="noreferrer" className="block h-24 w-24 shrink-0">
      <img src={displayUrl} alt={alt} className="h-24 w-24 rounded border border-gray-300 object-cover" />
    </a>
  );
}

function EvidenceGallery({ evidencias, alt }: { evidencias: DesvioBorradorEvidencia[]; alt: string }) {
  const images = useMemo(() => evidencias.filter((e) => e.tipo === 'image' || e.mime_type?.startsWith('image/')), [evidencias]);

  if (images.length === 0) {
    return <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded border border-gray-200 bg-gray-50 text-xs text-gray-400">Sin foto</div>;
  }

  if (images.length === 1) {
    return <EvidencePreview evidencia={images[0]} alt={alt} />;
  }

  return (
    <div className="flex gap-2 overflow-x-auto pb-1">
      {images.map((evidencia, idx) => (
        <EvidencePreview key={idx} evidencia={evidencia} alt={`${alt} ${idx + 1}`} />
      ))}
    </div>
  );
}


export default function RevisionDesvios() {
  const navigate = useNavigate();
  const { pendientes, loading, error, busyId, aprobar, descartar, reload } = useDesviosBorrador();
  const [actionError, setActionError] = useState<string | null>(null);

  const grouped = useMemo(() => {
    const bySucursal = new Map<string, DesvioBorrador[]>();
    pendientes.forEach((borrador) => {
      const key = borrador.sucursal || 'Sin sucursal';
      bySucursal.set(key, [...(bySucursal.get(key) || []), borrador]);
    });
    return Array.from(bySucursal.entries());
  }, [pendientes]);

  const handleApprove = async (id: string) => {
    try {
      setActionError(null);
      await aprobar(id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'No se pudo aprobar el borrador.');
    }
  };

  const handleDiscard = async (id: string) => {
    try {
      setActionError(null);
      await descartar(id, 'Descartado desde revision web');
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'No se pudo descartar el borrador.');
    }
  };

  return (
    <AppLayout title="Revision de Desvios">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm text-gray-600">
            {pendientes.length} borrador{pendientes.length !== 1 ? 'es' : ''} pendiente{pendientes.length !== 1 ? 's' : ''} de WhatsApp
          </p>
          <p className="mt-1 text-sm text-gray-500">
            Aprobados pasan a Gestion y aparecen en Centro de Desvios.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void reload()}
          className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
        >
          Actualizar
        </button>
      </div>

      {loading && <FeedbackState title="Cargando borradores..." />}
      {error && <FeedbackState title={error} tone="error" />}
      {actionError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {actionError}
        </div>
      )}
      {!loading && !error && pendientes.length === 0 && (
        <FeedbackState title="No hay borradores pendientes." description="Cuando el bot detecte posibles desvios, apareceran aca para revisar." />
      )}

      {!loading && !error && grouped.length > 0 && (
        <div className="space-y-8">
          {grouped.map(([sucursal, items]) => (
            <section key={sucursal}>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900">{sucursal}</h2>
                <span className="text-sm text-gray-500">{items.length} pendiente{items.length !== 1 ? 's' : ''}</span>
              </div>

              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                {items.map((borrador) => {
                  const busy = busyId === borrador.id;

                  return (
                    <article key={borrador.id} className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                      <div className="mb-4 flex items-start gap-4">
                        <EvidenceGallery evidencias={borrador.evidencias_json || []} alt={borrador.descripcion} />
                        <div className="min-w-0 flex-1">
                          <div className="mb-2 flex flex-wrap items-center gap-2">
                            <span className="rounded bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700">
                              {borrador.bloque_nombre || borrador.bloque_id}
                            </span>
                            <span className={`rounded px-2 py-1 text-xs font-semibold ${severidadColor(borrador.severidad_sugerida)}`}>
                              {borrador.severidad_sugerida}
                            </span>
                          </div>
                          <p className="text-sm leading-6 text-gray-800">{borrador.descripcion}</p>
                        </div>
                      </div>

                      {borrador.respuesta_consolidada && borrador.respuesta_consolidada !== borrador.descripcion && (
                        <div className="mb-4 rounded bg-gray-50 p-3 text-sm text-gray-600">
                          {borrador.respuesta_consolidada}
                        </div>
                      )}

                      <div className="mb-4 grid grid-cols-1 gap-2 text-xs text-gray-500 sm:grid-cols-2">
                        <div>Auditor: {borrador.auditor_nombre || '-'}</div>
                        <div>Creado: {formatDateTime(borrador.created_at)}</div>
                        <div>Sesion: {borrador.id_sesion || '-'}</div>
                        <div>Evidencias: {borrador.evidencias_json?.length || 0}</div>
                      </div>

                      <div className="flex flex-wrap justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => void handleDiscard(borrador.id)}
                          disabled={busy}
                          className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Descartar
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleApprove(borrador.id)}
                          disabled={busy}
                          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {busy ? 'Procesando...' : 'Aprobar'}
                        </button>
                        {borrador.id_gestion && (
                          <button
                            type="button"
                            onClick={() => navigate(`/desvios/${borrador.id_gestion}`)}
                            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
                          >
                            Ver gestion
                          </button>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      )}
    </AppLayout>
  );
}

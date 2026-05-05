import { useEffect, useMemo, useState } from 'react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { useDesviosBorrador } from '../hooks/useDesviosBorrador';
import { resolveEvidenceUrl, resolveEvidenceThumbUrl } from '../lib/api';
import { formatDateTime, severidadColor } from '../lib/utils';
import type { DesvioBorrador, DesvioBorradorEvidencia, Severidad } from '../types';

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
  const {
    pendientes,
    loading,
    error,
    busyId,
    selectedIds,
    aprobar,
    descartar,
    reload,
    aprobarSeleccionados,
    descartarSeleccionados,
    toggleSelect,
    selectAll,
    clearSelection,
  } = useDesviosBorrador();

  const [searchText, setSearchText] = useState('');
  const [severidadFilter, setSeveridadFilter] = useState<'' | Severidad>('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchText.toLowerCase());
    }, 200);
    return () => clearTimeout(timer);
  }, [searchText]);

  // Filter and group
  const filtered = useMemo(() => {
    return pendientes.filter((borrador) => {
      if (severidadFilter && borrador.severidad_sugerida !== severidadFilter) {
        return false;
      }
      if (debouncedSearch) {
        const searchLower = debouncedSearch;
        const matches =
          borrador.descripcion.toLowerCase().includes(searchLower) ||
          borrador.bloque_nombre?.toLowerCase().includes(searchLower) ||
          borrador.sucursal?.toLowerCase().includes(searchLower) ||
          borrador.bloque_id?.toLowerCase().includes(searchLower);
        return matches;
      }
      return true;
    });
  }, [pendientes, severidadFilter, debouncedSearch]);

  const grouped = useMemo(() => {
    const bySucursal = new Map<string, DesvioBorrador[]>();
    filtered.forEach((borrador) => {
      const key = borrador.sucursal || 'Sin sucursal';
      bySucursal.set(key, [...(bySucursal.get(key) || []), borrador]);
    });
    return Array.from(bySucursal.entries());
  }, [filtered]);

  const handleApprove = async (id: string) => {
    try {
      await aprobar(id);
    } catch {
      // Error already handled in hook with toast
    }
  };

  const handleDiscard = async (id: string) => {
    try {
      await descartar(id, 'Descartado desde revision web');
    } catch {
      // Error already handled in hook with toast
    }
  };

  return (
    <AppLayout title="Revision de Desvios">
      <div className="mb-6 space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
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

        {/* Search and Filters */}
        <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
          <div>
            <label htmlFor="search" className="block text-xs font-medium text-gray-700">
              Buscar
            </label>
            <input
              id="search"
              type="text"
              placeholder="Descripción, bloque, sucursal..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-2">
              Severidad
            </label>
            <div className="flex flex-wrap gap-2">
              {(['', 'Alta', 'Media', 'Baja'] as const).map((sev) => (
                <button
                  key={sev || 'todos'}
                  type="button"
                  onClick={() => setSeveridadFilter(sev)}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                    severidadFilter === sev
                      ? 'bg-blue-600 text-white'
                      : 'border border-gray-300 text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  {sev || 'Todos'}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {loading && <FeedbackState title="Cargando borradores..." />}
      {error && <FeedbackState title={error} tone="error" />}
      {!loading && !error && pendientes.length === 0 && (
        <FeedbackState title="No hay borradores pendientes." description="Cuando el bot detecte posibles desvios, apareceran aca para revisar." />
      )}

      {/* Toolbar de acciones en lote */}
      {selectedIds.size > 0 && (
        <div className="mb-6 flex items-center gap-3 rounded-lg bg-blue-50 border border-blue-200 p-4">
          <span className="text-sm font-medium text-blue-900">
            {selectedIds.size} seleccionado{selectedIds.size !== 1 ? 's' : ''} de {filtered.length}
          </span>
          {selectedIds.size < filtered.length && (
            <button
              type="button"
              onClick={() => selectAll()}
              className="text-sm text-blue-600 hover:text-blue-800 underline"
            >
              Seleccionar todos
            </button>
          )}
          <button
            type="button"
            onClick={() => clearSelection()}
            className="text-sm text-blue-600 hover:text-blue-800 underline"
          >
            Limpiar
          </button>
          <div className="flex-1" />
          <button
            type="button"
            onClick={() => void descartarSeleccionados()}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
          >
            Descartar ({selectedIds.size})
          </button>
          <button
            type="button"
            onClick={() => void aprobarSeleccionados()}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Aprobar ({selectedIds.size})
          </button>
        </div>
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
                  const isSelected = selectedIds.has(borrador.id);

                  return (
                    <article
                      key={borrador.id}
                      className={`rounded-lg border bg-white p-4 shadow-sm transition ${
                        isSelected ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'
                      }`}
                    >
                      <div className="mb-4 flex items-start gap-4">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelect(borrador.id)}
                          className="mt-1 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          aria-label={`Seleccionar ${borrador.descripcion}`}
                        />
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
                            onClick={() => window.open(`/desvios/${borrador.id_gestion}`, '_blank')}
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

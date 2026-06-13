import { useEffect, useMemo, useState } from 'react';
import { Check, Search, Trash2, X } from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { useDesviosBorrador } from '../hooks/useDesviosBorrador';
import { resolveEvidenceUrl, resolveEvidenceThumbUrl } from '../lib/api';
import { formatDateTime } from '../lib/utils';
import type { DesvioBorrador, DesvioBorradorEvidencia, Severidad } from '../types';

type GroupBy = 'sucursal' | 'bloque' | 'none';

const tokens = {
  navy: '#1E3A6D',
  orange: '#F15A29',
  green: '#2A9D5F',
  severity: {
    Alta: { bar: '#DC2626', soft: '#FEE2E2', fg: '#991B1B' },
    Media: { bar: '#D97706', soft: '#FEF3C7', fg: '#92400E' },
    Baja: { bar: '#0EA5E9', soft: '#E0F2FE', fg: '#075985' },
  } satisfies Record<Severidad, { bar: string; soft: string; fg: string }>,
};


function normalize(value: string | null | undefined) {
  return (value || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

function isImageEvidence(evidencia: DesvioBorradorEvidencia) {
  return evidencia.tipo === 'image' || evidencia.mime_type?.startsWith('image/');
}

function EvidenceThumb({ evidencia, alt, size = 'sm' }: { evidencia?: DesvioBorradorEvidencia; alt: string; size?: 'sm' | 'lg' }) {
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

  const className = size === 'lg' ? 'h-44 w-full' : 'h-12 w-16';

  if (!evidencia || (!evidencia.path && !evidencia.url)) {
    return <div className={`${className} flex shrink-0 items-center justify-center rounded-md border border-slate-200 bg-slate-50 text-[11px] text-slate-400`}>Sin foto</div>;
  }

  const displayUrl = thumbUrl || fullUrl;
  if (!displayUrl) {
    return <div className={`${className} shrink-0 rounded-md border border-slate-200 bg-slate-100`} />;
  }

  return (
    <a href={fullUrl || displayUrl} target="_blank" rel="noreferrer" className={`${className} block shrink-0 overflow-hidden rounded-md border border-slate-200 bg-slate-100`}>
      <img src={displayUrl} alt={alt} className="h-full w-full object-cover" />
    </a>
  );
}

function SeverityBadge({ severidad }: { severidad: Severidad }) {
  const color = tokens.severity[severidad];
  return (
    <span className="inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-bold" style={{ background: color.soft, color: color.fg }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color.bar }} />
      {severidad}
    </span>
  );
}

function QualityPill({ borrador }: { borrador: DesvioBorrador }) {
  const hasEvidence = (borrador.evidencias_json || []).some(isImageEvidence);
  const hasText = borrador.descripcion.trim().length >= 20;
  const label = hasEvidence && hasText ? 'Completo' : hasEvidence ? 'Revisar texto' : 'Sin evidencia';
  const tone = hasEvidence && hasText
    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : hasEvidence
      ? 'bg-amber-50 text-amber-700 border-amber-200'
      : 'bg-slate-50 text-slate-500 border-slate-200';

  return <span className={`rounded-full border px-2.5 py-1 text-xs font-bold ${tone}`}>{label}</span>;
}

function GroupHeader({ label, count, accent }: { label: string; count: number; accent: string }) {
  return (
    <div className="sticky top-[145px] z-10 flex items-center gap-3 border-y border-slate-200 bg-slate-50 px-5 py-2 text-xs font-bold uppercase tracking-wide text-slate-600 lg:top-[137px]">
      <span className="ml-9 h-2 w-2 rounded-full" style={{ background: accent }} />
      <span>{label}</span>
      <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 tracking-normal">{count}</span>
    </div>
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
      style={{ borderColor: checked ? tokens.navy : '#CBD5E1', background: checked ? tokens.navy : '#fff', color: '#fff' }}
      aria-label={checked ? 'Quitar seleccion' : 'Seleccionar'}
    >
      {checked && <Check className="h-4 w-4" />}
    </button>
  );
}

function Drawer({
  borrador,
  busy,
  onClose,
  onApprove,
  onDiscard,
}: {
  borrador: DesvioBorrador;
  busy: boolean;
  onClose: () => void;
  onApprove: (id: string) => void;
  onDiscard: (id: string) => void;
}) {
  const images = (borrador.evidencias_json || []).filter(isImageEvidence);

  return (
    <>
      <button type="button" aria-label="Cerrar detalle" onClick={onClose} className="fixed inset-0 z-40 cursor-default bg-slate-950/35" />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-white shadow-2xl sm:w-[640px]">
        <div className="border-b border-slate-200 px-6 py-5">
          <div className="mb-4 flex items-center gap-3">
            <SeverityBadge severidad={borrador.severidad_sugerida} />
            <QualityPill borrador={borrador} />
            <button type="button" onClick={onClose} className="ml-auto rounded-md p-2 text-slate-500 hover:bg-slate-100" aria-label="Cerrar">
              <X className="h-4.5 w-4.5" />
            </button>
          </div>
          <div className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">
            {borrador.sucursal || 'Sin sucursal'} · {borrador.bloque_nombre || borrador.bloque_id}
          </div>
          <h2 className="text-2xl font-bold leading-tight text-slate-950">{borrador.descripcion}</h2>
        </div>

        <div className="flex flex-wrap gap-2 border-b border-slate-200 px-6 py-4">
          <button
            type="button"
            disabled={busy}
            onClick={() => onApprove(borrador.id)}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg px-4 text-sm font-bold text-white disabled:opacity-60"
            style={{ background: tokens.green }}
          >
            <Check className="h-4 w-4" />
            Aprobar y pasar a Gestion
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onDiscard(borrador.id)}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-bold text-slate-700 disabled:opacity-60"
          >
            <Trash2 className="h-4 w-4" />
            Descartar
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto bg-slate-50 px-6 py-5">
          <div className="mb-5 rounded-lg border border-slate-200 bg-white p-4">
            <div className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">Respuesta consolidada</div>
            <p className="text-sm leading-6 text-slate-800">{borrador.respuesta_consolidada || borrador.descripcion}</p>
          </div>

          <div className="mb-5">
            <div className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-400">Evidencias</div>
            {images.length > 0 ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {images.map((evidencia, index) => (
                  <EvidenceThumb key={index} evidencia={evidencia} alt={`${borrador.descripcion} ${index + 1}`} size="lg" />
                ))}
              </div>
            ) : (
              <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">No hay imagenes asociadas.</div>
            )}
          </div>

          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            {[
              ['ID borrador', borrador.id],
              ['Auditor', borrador.auditor_nombre || '-'],
              ['Sesion', borrador.id_sesion || '-'],
              ['Bloque', `${borrador.bloque_nombre || '-'} (${borrador.bloque_id || '-'})`],
              ['Confianza', borrador.confianza != null ? `${Math.round(borrador.confianza * 100)}%` : '-'],
              ['Creado', formatDateTime(borrador.created_at)],
            ].map(([label, value]) => (
              <div key={label} className="grid grid-cols-[120px_1fr] border-b border-slate-100 px-4 py-3 text-sm last:border-b-0">
                <div className="font-semibold text-slate-400">{label}</div>
                <div className="min-w-0 break-words font-semibold text-slate-950">{value}</div>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </>
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
  const [groupBy, setGroupBy] = useState<GroupBy>('sucursal');
  const [openId, setOpenId] = useState<string | null>(null);

  const counts = useMemo(() => {
    const result: Record<Severidad | 'total', number> = { total: pendientes.length, Alta: 0, Media: 0, Baja: 0 };
    pendientes.forEach((borrador) => {
      result[borrador.severidad_sugerida] += 1;
    });
    return result;
  }, [pendientes]);

  const filtered = useMemo(() => {
    const search = normalize(searchText);
    return pendientes.filter((borrador) => {
      if (severidadFilter && borrador.severidad_sugerida !== severidadFilter) return false;
      if (!search) return true;
      return [
        borrador.descripcion,
        borrador.respuesta_consolidada,
        borrador.bloque_nombre,
        borrador.bloque_id,
        borrador.sucursal,
        borrador.auditor_nombre,
      ].some((value) => normalize(value).includes(search));
    });
  }, [pendientes, severidadFilter, searchText]);

  const groups = useMemo(() => {
    if (groupBy === 'none') return [{ key: 'all', label: '', accent: tokens.navy, items: filtered }];
    const map = new Map<string, DesvioBorrador[]>();
    filtered.forEach((borrador) => {
      const key = groupBy === 'bloque'
        ? borrador.bloque_nombre || borrador.bloque_id || 'Sin bloque'
        : borrador.sucursal || 'Sin sucursal';
      map.set(key, [...(map.get(key) || []), borrador]);
    });
    return Array.from(map.entries())
      .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))
      .map(([key, items]) => ({ key, label: key, accent: tokens.navy, items }));
  }, [filtered, groupBy]);

  const visibleIds = filtered.map((borrador) => borrador.id);
  const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));
  const openBorrador = openId ? pendientes.find((borrador) => borrador.id === openId) || null : null;

  const handleApprove = async (id: string) => {
    try {
      await aprobar(id);
      if (openId === id) setOpenId(null);
    } catch {
      // Hook shows toast.
    }
  };

  const handleDiscard = async (id: string) => {
    try {
      await descartar(id, 'Descartado desde revision web');
      if (openId === id) setOpenId(null);
    } catch {
      // Hook shows toast.
    }
  };

  return (
    <AppLayout title="Revision de Desvios" contentClassName="max-w-none px-0 py-0">
      <div className="min-h-[calc(100vh-73px)] bg-slate-100">
        <section className="border-b border-slate-200 bg-white px-5 py-4 lg:px-8">
          <div className="flex items-center gap-4">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg font-black text-white" style={{ background: tokens.navy }}>RV</div>
            <div className="min-w-0 flex-1">
              <div className="text-xs font-bold uppercase tracking-widest text-slate-500">FarmaAudit · WhatsApp</div>
              <h1 className="truncate text-2xl font-bold text-slate-950">Revision de Desvios</h1>
            </div>
            <span className="hidden rounded-full bg-slate-100 px-4 py-2 text-sm font-bold text-slate-600 sm:inline-flex">
              {pendientes.length} pendientes
            </span>
            <button type="button" onClick={() => void reload()} className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50">
              Actualizar
            </button>
          </div>
        </section>

        <section className="sticky top-0 z-20 border-b border-slate-200 bg-white px-5 py-4 lg:px-8">
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
              <label className="relative min-w-0 flex-1">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400"><Search className="h-4.5 w-4.5" /></span>
                <input
                  value={searchText}
                  onChange={(event) => setSearchText(event.target.value)}
                  placeholder="Buscar por descripcion, sucursal, bloque o auditor..."
                  className="h-12 w-full rounded-lg border border-slate-300 bg-white pl-12 pr-4 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                />
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <span className="mr-1 text-xs font-bold uppercase tracking-wide text-slate-500">Vista</span>
                {[
                  ['sucursal', 'Por sucursal'],
                  ['bloque', 'Por bloque'],
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
              <span className="mr-1 text-xs font-bold uppercase tracking-wide text-slate-500">Severidad</span>
              {(['', 'Alta', 'Media', 'Baja'] as const).map((sev) => {
                const active = severidadFilter === sev;
                const count = sev ? counts[sev] : counts.total;
                return (
                  <button
                    key={sev || 'todos'}
                    type="button"
                    onClick={() => setSeveridadFilter(sev)}
                    className="inline-flex min-h-10 items-center gap-2 rounded-lg border px-4 text-sm font-bold transition hover:bg-slate-50"
                    style={{ borderColor: active ? tokens.navy : '#D0D5DD', background: active ? tokens.navy : '#fff', color: active ? '#fff' : '#344054' }}
                  >
                    {sev || 'Todas'}
                    <span className="rounded-full px-2 py-0.5 text-xs" style={{ background: active ? 'rgba(255,255,255,.18)' : '#F1F4F9' }}>{count}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </section>

        {selectedIds.size > 0 && (
          <div className="sticky top-[145px] z-20 flex flex-wrap items-center gap-3 bg-slate-900 px-5 py-3 text-sm font-bold text-white lg:top-[137px] lg:px-8">
            <span>{selectedIds.size} seleccionados</span>
            {!allSelected && <button type="button" onClick={() => selectAll()} className="rounded-md bg-white/10 px-3 py-2 hover:bg-white/20">Seleccionar todos</button>}
            <button type="button" onClick={() => clearSelection()} className="rounded-md bg-white/10 px-3 py-2 hover:bg-white/20">Limpiar</button>
            <button
              type="button"
              onClick={() => {
                if (window.confirm(`¿Descartar ${selectedIds.size} borrador${selectedIds.size === 1 ? '' : 'es'}? Esta accion no se puede deshacer.`))
                  void descartarSeleccionados();
              }}
              className="ml-auto rounded-md bg-white/10 px-3 py-2 hover:bg-red-500/80"
            >Descartar</button>
            <button type="button" onClick={() => void aprobarSeleccionados()} className="rounded-md px-3 py-2 text-white" style={{ background: tokens.green }}>Aprobar</button>
          </div>
        )}

        {loading && <div className="px-6 py-10"><FeedbackState title="Cargando borradores..." tone="loading" /></div>}
        {error && <div className="px-6 py-10"><FeedbackState title={error} tone="error" /></div>}
        {!loading && !error && pendientes.length === 0 && (
          <div className="px-6 py-10">
            <FeedbackState title="No hay borradores pendientes." description="Cuando el bot detecte posibles desvios, apareceran aca para revisar." />
          </div>
        )}

        {!loading && !error && pendientes.length > 0 && (
          <div className="bg-white">
            <div className="hidden min-w-[1080px] grid-cols-[44px_86px_minmax(340px,1fr)_230px_160px_150px_138px] items-center border-b border-slate-200 bg-white px-4 py-3 text-xs font-bold uppercase tracking-wide text-slate-500 lg:grid">
              <div><SelectBox checked={allSelected} onClick={() => (allSelected ? clearSelection() : selectAll())} /></div>
              <div>Evidencia</div>
              <div>Desvio</div>
              <div>Sucursal · Bloque</div>
              <div>Calidad</div>
              <div>Creado</div>
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
                {group.label && <GroupHeader label={group.label} count={group.items.length} accent={group.accent} />}
                {group.items.map((borrador) => {
                  const images = (borrador.evidencias_json || []).filter(isImageEvidence);
                  const selected = selectedIds.has(borrador.id);
                  const busy = busyId === borrador.id;
                  return (
                    <article
                      key={borrador.id}
                      onClick={() => setOpenId(borrador.id)}
                      className="grid cursor-pointer grid-cols-[32px_1fr] gap-3 border-b border-slate-100 bg-white px-4 py-4 transition hover:bg-slate-50 lg:min-w-[1080px] lg:grid-cols-[44px_86px_minmax(340px,1fr)_230px_160px_150px_138px] lg:items-center lg:gap-0 lg:py-0"
                    >
                      <div className="pt-1 lg:pt-0"><SelectBox checked={selected} onClick={() => toggleSelect(borrador.id)} /></div>
                      <div className="hidden py-2 lg:block">
                        <EvidenceThumb evidencia={images[0]} alt={borrador.descripcion} />
                      </div>
                      <div className="lg:hidden">
                        <div className="mb-3 flex flex-wrap items-center gap-2">
                          <SeverityBadge severidad={borrador.severidad_sugerida} />
                          <QualityPill borrador={borrador} />
                        </div>
                        <div className="font-semibold text-slate-950">{borrador.descripcion}</div>
                        <div className="mt-1 text-sm text-slate-500">{borrador.sucursal || '-'} · {borrador.bloque_nombre || borrador.bloque_id}</div>
                      </div>
                      <div className="hidden min-w-0 py-3 pr-4 lg:block">
                        <div className="mb-1 flex items-center gap-2">
                          <SeverityBadge severidad={borrador.severidad_sugerida} />
                          {images.length > 1 && <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-bold text-slate-500">+{images.length - 1} fotos</span>}
                        </div>
                        <div className="truncate font-semibold text-slate-950">{borrador.descripcion}</div>
                        {borrador.respuesta_consolidada && borrador.respuesta_consolidada !== borrador.descripcion && (
                          <div className="mt-1 truncate text-xs text-slate-400">{borrador.respuesta_consolidada}</div>
                        )}
                      </div>
                      <div className="hidden min-w-0 py-3 pr-4 lg:block">
                        <div className="truncate font-semibold text-slate-950">{borrador.sucursal || '-'}</div>
                        <div className="mt-1 truncate text-xs text-slate-400">{borrador.bloque_nombre || borrador.bloque_id || '-'}</div>
                      </div>
                      <div className="hidden py-3 lg:block"><QualityPill borrador={borrador} /></div>
                      <div className="hidden py-3 text-sm text-slate-500 lg:block">{formatDateTime(borrador.created_at)}</div>
                      <div className="hidden justify-end gap-2 py-3 lg:flex" onClick={(event) => event.stopPropagation()}>
                        <button type="button" disabled={busy} onClick={() => void handleDiscard(borrador.id)} className="rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-50">
                          Descartar
                        </button>
                        <button type="button" disabled={busy} onClick={() => void handleApprove(borrador.id)} className="rounded-md px-3 py-2 text-xs font-bold text-white disabled:opacity-50" style={{ background: tokens.green }}>
                          Aprobar
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            ))}
          </div>
        )}

        {openBorrador && (
          <Drawer
            borrador={openBorrador}
            busy={busyId === openBorrador.id}
            onClose={() => setOpenId(null)}
            onApprove={(id) => void handleApprove(id)}
            onDiscard={(id) => void handleDiscard(id)}
          />
        )}
      </div>
    </AppLayout>
  );
}

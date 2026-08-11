import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Camera, FileText } from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { ReminderButton } from '../components/ReminderButton';
import { useAuth } from '../hooks/useAuth';
import { getEstadoContactoSucursales, getFichaById, getFichaPdfUrl, getGestionesByFicha, getSignedUrl, getSucursal } from '../lib/api';
import { supabase } from '../lib/supabase';
import { BLOQUES_FICHA, formatDate, formatDateTime, gestionStateLabel, scoreColor, severidadColor } from '../lib/utils';
import type { AuditFicha, EstadoContactoSucursal, Gestion, Sucursal } from '../types';

function readString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function GestionCard({
  gestion,
  thumb,
  onClick,
  footer,
}: {
  gestion: Gestion;
  /** undefined = todavía cargando; null = no hay foto; string = url. */
  thumb: string | null | undefined;
  onClick: () => void;
  footer?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full flex-col overflow-hidden rounded-lg border border-gray-200 bg-white text-left shadow-sm transition hover:shadow-md"
    >
      <div className="flex h-32 items-center justify-center bg-gray-100">
        {thumb === undefined ? (
          <span className="text-xs text-gray-400">Cargando...</span>
        ) : thumb ? (
          <img src={thumb} alt={gestion.desvio} className="h-full w-full object-cover" />
        ) : (
          <Camera className="h-8 w-8 text-gray-300" />
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-center gap-2">
          <span className={`rounded px-2 py-0.5 text-xs font-semibold ${severidadColor(gestion.severidad)}`}>
            {gestion.severidad}
          </span>
          <span className="text-xs text-gray-500">{gestionStateLabel(gestion.estado)}</span>
        </div>
        <p className="line-clamp-3 text-sm text-gray-800">{gestion.desvio}</p>
        {footer && <p className="mt-auto text-xs text-gray-400">{footer}</p>}
      </div>
    </button>
  );
}

export default function AuditFichaDetail() {
  const { id: sucursalId, fichaId } = useParams<{ id: string; fichaId: string }>();
  const { role } = useAuth();
  const navigate = useNavigate();

  const [sucursal, setSucursal] = useState<Sucursal | null>(null);
  const [ficha, setFicha] = useState<AuditFicha | null>(null);
  const [gestiones, setGestiones] = useState<Gestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [thumbs, setThumbs] = useState<Record<string, string | null>>({});
  const [estadoContacto, setEstadoContacto] = useState<EstadoContactoSucursal | null | undefined>(undefined);

  const canAudit = role === 'admin' || role === 'auditor';

  // Al cambiar de ficha (navegando entre auditorías) hay que volver al
  // spinner, si no se ve el contenido de la anterior un instante. Se ajusta
  // durante el render (mismo patrón que SucursalDetail.tsx) y no dentro del
  // efecto, donde un setState sincrónico dispara un render en cascada.
  const fichaKey = `${sucursalId ?? ''}:${fichaId ?? ''}`;
  const [prevFichaKey, setPrevFichaKey] = useState(fichaKey);
  if (prevFichaKey !== fichaKey) {
    setPrevFichaKey(fichaKey);
    setLoading(true);
    setError('');
  }

  useEffect(() => {
    if (!sucursalId || !fichaId) return;
    let active = true;

    Promise.all([getSucursal(sucursalId), getFichaById(fichaId), getGestionesByFicha(fichaId)])
      .then(([sucursalData, fichaData, gestionesData]) => {
        if (!active) return;
        setSucursal(sucursalData);
        setFicha(fichaData);
        setGestiones(gestionesData);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'No se pudo cargar la auditoría.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [sucursalId, fichaId]);

  useEffect(() => {
    if (!sucursalId || !canAudit) return;
    let active = true;
    getEstadoContactoSucursales()
      .then((rows) => {
        if (active) setEstadoContacto(rows.find((r) => r.id_sucursal === sucursalId) ?? null);
      })
      .catch(() => {
        if (active) setEstadoContacto(null);
      });
    return () => {
      active = false;
    };
  }, [sucursalId, canAudit]);

  // Una miniatura por desvío: el evento de evidencia más reciente de cada
  // gestión. Una sola consulta con .in() en vez de N — evita N+1 al pintar
  // la grilla completa.
  useEffect(() => {
    if (gestiones.length === 0) return;
    let active = true;
    const ids = gestiones.map((g) => g.id_gestion);

    supabase
      .from('desvio_eventos')
      .select('id_gestion, metadata, created_at')
      .eq('tipo', 'evidencia')
      .in('id_gestion', ids)
      .order('created_at', { ascending: false })
      .then(async ({ data, error: err }) => {
        if (!active) return;
        if (err || !data) {
          setThumbs(Object.fromEntries(ids.map((gid) => [gid, null])));
          return;
        }
        const porGestion = new Map<string, { path: string | null; bucket: string | null; legacyUrl: string | null }>();
        for (const row of data as { id_gestion: string; metadata: Record<string, unknown> | null }[]) {
          if (porGestion.has(row.id_gestion)) continue;
          porGestion.set(row.id_gestion, {
            path: readString(row.metadata?.foto_path),
            bucket: readString(row.metadata?.bucket),
            legacyUrl: readString(row.metadata?.evidencia_url),
          });
        }

        const entries = await Promise.all(
          ids.map(async (gid) => {
            const info = porGestion.get(gid);
            if (!info) return [gid, null] as const;
            if (info.path) {
              try {
                const url = await getSignedUrl(info.path, info.bucket || undefined);
                return [gid, url] as const;
              } catch {
                return [gid, null] as const;
              }
            }
            return [gid, info.legacyUrl] as const;
          }),
        );
        if (active) setThumbs(Object.fromEntries(entries));
      });

    return () => {
      active = false;
    };
  }, [gestiones]);

  const pendientes = useMemo(
    () => gestiones.filter((g) => g.estado !== 'Resuelta' && g.estado !== 'Cerrada'),
    [gestiones],
  );
  const resueltos = useMemo(
    () => gestiones.filter((g) => g.estado === 'Resuelta' || g.estado === 'Cerrada'),
    [gestiones],
  );

  if (loading) {
    return (
      <AppLayout title="Auditoría">
        <FeedbackState title="Cargando auditoría..." tone="loading" />
      </AppLayout>
    );
  }

  if (error || !ficha || !sucursal) {
    return (
      <AppLayout title="Auditoría">
        <FeedbackState title={error || 'Auditoría no encontrada'} tone="error" />
      </AppLayout>
    );
  }

  const detalleGestion = (id: string) =>
    navigate(role === 'sucursal' ? `/mis-desvios/${id}` : `/desvios/${id}`);

  const sinVincular = ficha.desvios_count > gestiones.length;

  return (
    <AppLayout title={`Auditoría · ${sucursal.nombre}`}>
      <div className="mb-4">
        <button
          onClick={() => navigate(`/sucursales/${sucursalId}`)}
          className="text-sm font-medium text-blue-600 hover:text-blue-800"
        >
          ← Volver a {sucursal.nombre}
        </button>
      </div>

      <div className="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-lg font-semibold text-gray-900">
              Auditoría del {formatDate(ficha.fecha_auditoria || ficha.created_at)}
            </p>
            <p className="text-sm text-gray-500">
              {ficha.auditor_nombre || 'Auditor sin registrar'}
              {ficha.responsable_desvios && <span> · Responsable: {ficha.responsable_desvios}</span>}
            </p>
          </div>
          {ficha.url_pdf && (
            <button
              type="button"
              onClick={() => void getFichaPdfUrl(ficha).then((url) => url && window.open(url, '_blank', 'noopener'))}
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-100"
            >
              <FileText className="h-4 w-4" />
              Ver PDF
            </button>
          )}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {BLOQUES_FICHA.map((bloque) => {
            const v = ficha[bloque.key];
            return (
              <div key={bloque.key} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                <p className="text-xs text-gray-500">{bloque.label}</p>
                <p className={`text-lg font-bold ${scoreColor(v)}`}>{v != null ? `${v}/5` : '—'}</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Pendientes */}
      <div className="mb-8">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-gray-800">Pendientes ({pendientes.length})</h2>
          {canAudit && pendientes.length > 0 && (
            <ReminderButton
              idSucursal={sucursal.id}
              sucursalNombre={sucursal.nombre}
              cantidadDesvios={pendientes.length}
              estadoContacto={estadoContacto}
              onSent={() => {
                if (!sucursalId) return;
                getEstadoContactoSucursales()
                  .then((rows) => setEstadoContacto(rows.find((r) => r.id_sucursal === sucursalId) ?? null))
                  .catch(() => setEstadoContacto(null));
              }}
              size="sm"
            />
          )}
        </div>
        {pendientes.length === 0 ? (
          <FeedbackState title="Sin desvíos pendientes en esta auditoría" tone="success" />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {pendientes.map((g) => (
              <GestionCard key={g.id_gestion} gestion={g} thumb={thumbs[g.id_gestion]} onClick={() => detalleGestion(g.id_gestion)} />
            ))}
          </div>
        )}
      </div>

      {/* Resueltos */}
      <div className="mb-8">
        <h2 className="mb-3 text-sm font-semibold text-gray-800">Resueltos ({resueltos.length})</h2>
        {resueltos.length === 0 ? (
          <p className="text-sm text-gray-400">Todavía no se resolvió ningún desvío de esta auditoría.</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {resueltos.map((g) => (
              <GestionCard
                key={g.id_gestion}
                gestion={g}
                thumb={thumbs[g.id_gestion]}
                onClick={() => detalleGestion(g.id_gestion)}
                footer={g.fecha_cierre ? `Cerrado ${formatDateTime(g.fecha_cierre)}${g.cerrado_por ? ` · ${g.cerrado_por}` : ''}` : undefined}
              />
            ))}
          </div>
        )}
      </div>

      {sinVincular && (
        <p className="text-xs text-gray-400">
          Esta auditoría detectó {ficha.desvios_count} desvíos en total, pero {ficha.desvios_count - gestiones.length}{' '}
          son anteriores al vínculo entre auditorías y desvíos — no se pueden listar acá.
        </p>
      )}
    </AppLayout>
  );
}

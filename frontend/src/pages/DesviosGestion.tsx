import { useEffect, useMemo, useState } from 'react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { getGestion, getDesvioEventos, updateGestion, enviarMensajeInterno } from '../lib/api';
import { formatDateTime, severidadColor } from '../lib/utils';
import type { Gestion, DesvioEvento, GestionState } from '../types';
import { toast } from 'sonner';

const ESTADO_LABELS: Record<GestionState, string> = {
  'Abierta': 'Abierta',
  'En_proceso': 'En Proceso',
  'Resuelta': 'Resuelta',
  'Cerrada': 'Cerrada',
  'Vencida': 'Vencida',
};

const ESTADO_COLORS: Record<GestionState, string> = {
  'Abierta': 'bg-blue-50 border-blue-200 text-blue-900',
  'En_proceso': 'bg-amber-50 border-amber-200 text-amber-900',
  'Resuelta': 'bg-green-50 border-green-200 text-green-900',
  'Cerrada': 'bg-gray-50 border-gray-200 text-gray-900',
  'Vencida': 'bg-red-50 border-red-200 text-red-900',
};

interface DesvioCard extends Gestion {
  eventos: DesvioEvento[];
  ultimeRespuesta?: DesvioEvento;
}

function TimelineIndicator({ estado }: { estado: GestionState }) {
  const steps: GestionState[] = ['Abierta', 'En_proceso', 'Resuelta', 'Cerrada'];
  const currentIndex = steps.indexOf(estado);

  return (
    <div className="flex items-center gap-2">
      {steps.map((step, idx) => {
        const isActive = idx <= currentIndex;
        const isCurrent = idx === currentIndex;
        const colors = {
          'Abierta': 'bg-blue-200',
          'En_proceso': 'bg-amber-200',
          'Resuelta': 'bg-green-200',
          'Cerrada': 'bg-gray-300',
          'Vencida': 'bg-red-300',
        };

        return (
          <div key={step} className="flex items-center">
            <div
              className={`h-3 w-3 rounded-full transition ${
                isCurrent ? 'ring-2 ring-offset-2 ring-current' : ''
              } ${isActive ? colors[step] : 'bg-gray-200'}`}
            />
            {idx < steps.length - 1 && (
              <div className={`h-0.5 w-8 ${isActive ? 'bg-gray-300' : 'bg-gray-200'}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function DesvioCardComponent({ desvio, onRefresh }: { desvio: DesvioCard; onRefresh: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [comentario, setComentario] = useState('');
  const [sending, setSending] = useState(false);
  const [updating, setUpdating] = useState(false);

  const handleComment = async () => {
    if (!comentario.trim()) return;

    setSending(true);
    try {
      await enviarMensajeInterno({
        idGestion: desvio.id_gestion,
        comentario,
        origen: 'auditor',
        actorId: '',
        actorNombre: '',
      });
      toast.success('Comentario enviado');
      setComentario('');
      void onRefresh();
    } catch (err) {
      toast.error('Error al enviar comentario');
    } finally {
      setSending(false);
    }
  };

  const handleStateChange = async (newEstado: GestionState) => {
    setUpdating(true);
    try {
      await updateGestion(desvio.id_gestion, newEstado);
      toast.success(`Desvio marcado como ${ESTADO_LABELS[newEstado]}`);
      void onRefresh();
    } catch (err) {
      toast.error('Error al actualizar estado');
    } finally {
      setUpdating(false);
    }
  };

  const diasEnProceso = desvio.created_at
    ? Math.floor((Date.now() - new Date(desvio.created_at).getTime()) / (1000 * 60 * 60 * 24))
    : 0;

  const esVencida = desvio.estado === 'Vencida';

  return (
    <article
      className={`rounded-lg border-2 p-6 transition ${
        esVencida
          ? 'border-red-300 bg-red-50'
          : ESTADO_COLORS[desvio.estado].replace('border-', 'border-2 ')
      }`}
    >
      {/* Header */}
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="mb-2 flex items-center gap-2">
            <span className={`inline-block rounded-full px-3 py-1 text-xs font-bold ${severidadColor(desvio.severidad)}`}>
              {desvio.severidad}
            </span>
            <span className="text-sm font-mono text-gray-600">{desvio.id_gestion}</span>
          </div>
          <p className="mb-1 text-lg font-bold text-gray-900">{desvio.desvio}</p>
          <p className="text-sm text-gray-600">
            {desvio.sucursal} • Responsable: {desvio.responsable}
          </p>
        </div>
      </div>

      {/* Timeline */}
      <div className="mb-4 rounded bg-white px-3 py-2">
        <TimelineIndicator estado={desvio.estado} />
      </div>

      {/* Estado y plazo */}
      <div className="mb-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <span className="text-xs font-semibold text-gray-600">ESTADO</span>
          <p className="font-bold text-gray-900">{ESTADO_LABELS[desvio.estado]}</p>
          <p className="text-xs text-gray-500">Hace {diasEnProceso} días</p>
        </div>
        <div>
          <span className="text-xs font-semibold text-gray-600">PLAZO</span>
          <p className={`font-bold ${esVencida ? 'text-red-600' : 'text-gray-900'}`}>
            {new Date(desvio.plazo_fecha).toLocaleDateString()}
          </p>
          {esVencida && <p className="text-xs font-semibold text-red-600">VENCIDA</p>}
        </div>
      </div>

      {desvio.plan_accion && (
        <div className="mb-4 rounded border-l-4 border-blue-400 bg-blue-50 p-3">
          <p className="text-xs font-semibold text-blue-900">Plan de acción:</p>
          <p className="text-sm text-blue-800">{desvio.plan_accion}</p>
        </div>
      )}

      {/* Expandable section */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full rounded border border-gray-300 bg-white px-3 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50"
      >
        {expanded ? '▼' : '▶'} {desvio.eventos?.length || 0} eventos
      </button>

      {expanded && (
        <div className="mt-4 space-y-4 rounded bg-white p-4">
          {/* Eventos */}
          <div className="max-h-64 space-y-3 overflow-y-auto border-b pb-4">
            {(desvio.eventos || []).map((evento) => (
              <div key={evento.id} className="border-l-2 border-gray-300 pl-3">
                <p className="text-xs font-semibold text-gray-600">
                  {evento.tipo.toUpperCase()} • {evento.actor_nombre || 'Sistema'}
                </p>
                <p className="text-sm text-gray-700">{evento.comentario}</p>
                <p className="text-xs text-gray-500">{formatDateTime(evento.created_at)}</p>
              </div>
            ))}
          </div>

          {/* Nuevo comentario */}
          <div className="space-y-2">
            <textarea
              value={comentario}
              onChange={(e) => setComentario(e.target.value)}
              placeholder="Agregar comentario..."
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              rows={2}
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleComment}
                disabled={sending || !comentario.trim()}
                className="rounded bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {sending ? 'Enviando...' : 'Comentar'}
              </button>
            </div>
          </div>

          {/* Acciones de estado */}
          {desvio.estado !== 'Cerrada' && desvio.estado !== 'Resuelta' && (
            <div className="border-t pt-4">
              <p className="mb-2 text-xs font-semibold text-gray-600">CAMBIAR ESTADO</p>
              <div className="flex flex-wrap gap-2">
                {(['En_proceso', 'Resuelta', 'Cerrada'] as const).map((estado) => (
                  <button
                    key={estado}
                    type="button"
                    onClick={() => handleStateChange(estado)}
                    disabled={updating}
                    className="rounded border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {ESTADO_LABELS[estado]}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export default function DesviosGestion() {
  const [desvios, setDesvios] = useState<DesvioCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [estadoFilter, setEstadoFilter] = useState<'' | GestionState>('');
  const [searchText, setSearchText] = useState('');
  const [severidadFilter, setSeveridadFilter] = useState<'' | 'Alta' | 'Media' | 'Baja'>('');

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getGestion();

      // Enrich with eventos
      const enriched = await Promise.all(
        data.map(async (gestion) => {
          const eventos = await getDesvioEventos(gestion.id_gestion);
          return { ...gestion, eventos } as DesvioCard;
        }),
      );

      setDesvios(enriched);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar desvios');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const filtered = useMemo(() => {
    return desvios.filter((d) => {
      if (estadoFilter && d.estado !== estadoFilter) return false;
      if (severidadFilter && d.severidad !== severidadFilter) return false;
      if (searchText) {
        const search = searchText.toLowerCase();
        return (
          d.desvio.toLowerCase().includes(search) ||
          d.sucursal.toLowerCase().includes(search) ||
          d.responsable.toLowerCase().includes(search)
        );
      }
      return true;
    });
  }, [desvios, estadoFilter, severidadFilter, searchText]);

  const grouped = useMemo(() => {
    const byEstado = new Map<GestionState, DesvioCard[]>();
    filtered.forEach((d) => {
      const key = d.estado;
      byEstado.set(key, [...(byEstado.get(key) || []), d]);
    });
    return Array.from(byEstado.entries()).sort((a, b) => {
      const order: GestionState[] = ['Vencida', 'Abierta', 'En_proceso', 'Resuelta', 'Cerrada'];
      return order.indexOf(a[0]) - order.indexOf(b[0]);
    });
  }, [filtered]);

  return (
    <AppLayout title="Gestión de Desvios">
      <div className="mb-8">
        {/* Intro */}
        <div className="mb-6">
          <p className="text-lg font-light text-gray-600">
            {desvios.length} desvios en gestión
          </p>
        </div>

        {/* Filtros */}
        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <div className="space-y-4">
            {/* Búsqueda */}
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-2">BUSCAR</label>
              <input
                type="text"
                placeholder="Desvio, sucursal, responsable..."
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            {/* Estados */}
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-2">ESTADO</label>
              <div className="flex flex-wrap gap-2">
                {(['', 'Abierta', 'En_proceso', 'Resuelta', 'Cerrada'] as const).map((e) => (
                  <button
                    key={e || 'todos'}
                    type="button"
                    onClick={() => setEstadoFilter(e)}
                    className={`rounded px-3 py-1.5 text-xs font-semibold transition ${
                      estadoFilter === e
                        ? 'bg-gray-900 text-white'
                        : 'border border-gray-300 text-gray-700 hover:bg-gray-100'
                    }`}
                  >
                    {e ? ESTADO_LABELS[e] : 'Todos'}
                  </button>
                ))}
              </div>
            </div>

            {/* Severidad */}
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-2">SEVERIDAD</label>
              <div className="flex flex-wrap gap-2">
                {(['', 'Alta', 'Media', 'Baja'] as const).map((s) => (
                  <button
                    key={s || 'todos'}
                    type="button"
                    onClick={() => setSeveridadFilter(s)}
                    className={`rounded px-3 py-1.5 text-xs font-semibold transition ${
                      severidadFilter === s
                        ? 'bg-gray-900 text-white'
                        : 'border border-gray-300 text-gray-700 hover:bg-gray-100'
                    }`}
                  >
                    {s || 'Todas'}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {loading && <FeedbackState title="Cargando desvios..." />}
      {error && <FeedbackState title={error} tone="error" />}
      {!loading && !error && desvios.length === 0 && (
        <FeedbackState title="No hay desvios en gestión." description="Cuando los auditores aprueben borradores, aparecerán aqui para su seguimiento." />
      )}

      {/* Grid de desvios */}
      {!loading && !error && grouped.length > 0 && (
        <div className="space-y-8">
          {grouped.map(([estado, items]) => (
            <section key={estado}>
              <h2 className="mb-4 text-lg font-bold text-gray-900">{ESTADO_LABELS[estado]}</h2>
              <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
                {items.map((desvio) => (
                  <DesvioCardComponent key={desvio.id_gestion} desvio={desvio} onRefresh={load} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </AppLayout>
  );
}

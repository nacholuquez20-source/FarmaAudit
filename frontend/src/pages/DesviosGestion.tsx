import { useEffect, useMemo, useState } from 'react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { getGestion, getDesvioEventos, updateGestion, enviarMensajeInterno } from '../lib/api';
import { formatDate, formatDateTime, severidadColor, gestionStateColor, gestionStateLabel } from '../lib/utils';
import type { Gestion, DesvioEvento, GestionState } from '../types';
import { toast } from 'sonner';

interface DesvioCard extends Gestion {
  eventos: DesvioEvento[];
}

const ESTADO_OPTIONS: GestionState[] = ['Abierta', 'En_proceso', 'Resuelta', 'Cerrada'];

export default function DesviosGestion() {
  const [desvios, setDesvios] = useState<DesvioCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [estadoFilter, setEstadoFilter] = useState<'' | GestionState>('');
  const [severidadFilter, setSeveridadFilter] = useState<'' | 'Alta' | 'Media' | 'Baja'>('');
  const [searchText, setSearchText] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [comentario, setComentario] = useState('');
  const [sending, setSending] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getGestion();

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

  const handleStateChange = async (desvioId: string, newEstado: GestionState) => {
    const snapshot = desvios;
    setUpdatingId(desvioId);

    setDesvios((prev) =>
      prev.map((d) => (d.id_gestion === desvioId ? { ...d, estado: newEstado } : d))
    );

    try {
      await updateGestion(desvioId, newEstado);
      toast.success(`Desvio marcado como ${gestionStateLabel(newEstado)}`);
    } catch (err) {
      setDesvios(snapshot);
      toast.error('Error al actualizar estado');
    } finally {
      setUpdatingId(null);
    }
  };

  const handleComment = async (desvioId: string) => {
    if (!comentario.trim()) return;

    setSending(true);
    try {
      await enviarMensajeInterno({
        idGestion: desvioId,
        comentario,
        origen: 'auditor',
        actorId: '',
        actorNombre: '',
      });
      toast.success('Comentario enviado');
      setComentario('');
      void load();
    } catch (err) {
      toast.error('Error al enviar comentario');
    } finally {
      setSending(false);
    }
  };

  return (
    <AppLayout title="Gestión de Desvios">
      <div className="mb-8">
        <div className="mb-6">
          <p className="text-lg font-light text-gray-600">
            {desvios.length} desvios en gestión
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-5 sticky top-0 z-10">
          <div className="space-y-4">
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

            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-2">ESTADO</label>
              <div className="flex flex-wrap gap-2">
                {(['', 'Vencida', 'Abierta', 'En_proceso', 'Resuelta', 'Cerrada'] as const).map((e) => (
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
                    {e ? gestionStateLabel(e) : 'Todos'}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-2">SEVERIDAD</label>
              <div className="flex flex-wrap gap-2">
                {(['', 'Alta', 'Media', 'Baja'] as const).map((s) => (
                  <button
                    key={s || 'todas'}
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

      {!loading && !error && grouped.length > 0 && (
        <div className="space-y-6">
          {grouped.map(([estado, items]) => (
            <div key={estado}>
              <h2 className="mb-3 text-lg font-bold text-gray-900">{gestionStateLabel(estado)}</h2>
              <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50">
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700">Sev.</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700">Descripción</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700">Sucursal</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700">Responsable</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700">Estado</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700">Plazo</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700">Días</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700">Eventos</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((desvio) => {
                      const isExpanded = expandedId === desvio.id_gestion;
                      const diasEnProceso = desvio.created_at
                        ? Math.floor((Date.now() - new Date(desvio.created_at).getTime()) / (1000 * 60 * 60 * 24))
                        : 0;
                      const esVencida = desvio.estado === 'Vencida';

                      return (
                        <tbody key={desvio.id_gestion}>
                          <tr
                            onClick={() => setExpandedId(isExpanded ? null : desvio.id_gestion)}
                            className="border-b border-gray-100 hover:bg-gray-50 cursor-pointer"
                          >
                            <td className="px-4 py-3 text-sm">
                              <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${severidadColor(desvio.severidad)}`}>
                                {desvio.severidad.charAt(0).toUpperCase()}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-sm">
                              <div className="font-medium text-gray-900 line-clamp-2">{desvio.desvio}</div>
                              <div className="text-xs text-gray-500">{desvio.id_gestion}</div>
                            </td>
                            <td className="px-4 py-3 text-sm text-gray-600">{desvio.sucursal}</td>
                            <td className="px-4 py-3 text-sm text-gray-600">{desvio.responsable}</td>
                            <td className="px-4 py-3 text-sm">
                              <select
                                value={desvio.estado}
                                onChange={(e) => void handleStateChange(desvio.id_gestion, e.target.value as GestionState)}
                                disabled={updatingId === desvio.id_gestion}
                                onClick={(e) => e.stopPropagation()}
                                className={`rounded px-2 py-1 text-xs font-semibold border-0 cursor-pointer disabled:opacity-60 ${gestionStateColor(desvio.estado)}`}
                              >
                                {ESTADO_OPTIONS.map((op) => (
                                  <option key={op} value={op}>
                                    {gestionStateLabel(op)}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td className={`px-4 py-3 text-sm ${esVencida ? 'text-red-600 font-semibold' : 'text-gray-600'}`}>
                              {formatDate(desvio.plazo_fecha)}
                              {esVencida && <span className="ml-1 text-xs">⚠</span>}
                            </td>
                            <td className="px-4 py-3 text-sm text-gray-600">{diasEnProceso}</td>
                            <td className="px-4 py-3 text-sm text-gray-600">{desvio.eventos.length}</td>
                            <td className="px-4 py-3 text-sm">
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setExpandedId(isExpanded ? null : desvio.id_gestion);
                                }}
                                className="rounded-md bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100"
                              >
                                {isExpanded ? 'Cerrar' : 'Ver'}
                              </button>
                            </td>
                          </tr>

                          {isExpanded && (
                            <tr className="bg-gray-50 border-b border-gray-100">
                              <td colSpan={9} className="px-4 py-4">
                                <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                                  <div>
                                    <h4 className="mb-3 font-semibold text-gray-900 text-sm">Timeline</h4>
                                    <div className="max-h-48 space-y-3 overflow-y-auto border rounded border-gray-200 bg-white p-3">
                                      {desvio.eventos.length === 0 ? (
                                        <p className="text-xs text-gray-500 text-center py-4">Sin eventos</p>
                                      ) : (
                                        desvio.eventos.map((evento) => (
                                          <div key={evento.id} className="border-l-2 border-gray-300 pl-3 text-sm">
                                            <p className="text-xs font-semibold text-gray-600">
                                              {evento.tipo.toUpperCase()} • {evento.actor_nombre || 'Sistema'}
                                            </p>
                                            <p className="text-sm text-gray-700 mt-0.5">{evento.comentario}</p>
                                            <p className="text-xs text-gray-500 mt-1">{formatDateTime(evento.created_at)}</p>
                                          </div>
                                        ))
                                      )}
                                    </div>
                                  </div>

                                  <div className="space-y-3">
                                    <div>
                                      <label className="block text-sm font-semibold text-gray-900 mb-2">Agregar comentario</label>
                                      <textarea
                                        value={comentario}
                                        onChange={(e) => setComentario(e.target.value)}
                                        placeholder="..."
                                        className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                                        rows={3}
                                      />
                                      <button
                                        type="button"
                                        onClick={() => void handleComment(desvio.id_gestion)}
                                        disabled={sending || !comentario.trim()}
                                        className="mt-2 rounded bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                                      >
                                        {sending ? 'Enviando...' : 'Enviar'}
                                      </button>
                                    </div>

                                    {desvio.estado !== 'Cerrada' && desvio.estado !== 'Resuelta' && (
                                      <div>
                                        <p className="text-xs font-semibold text-gray-700 mb-2">Cambiar estado</p>
                                        <div className="flex flex-wrap gap-2">
                                          {(['En_proceso', 'Resuelta', 'Cerrada'] as const).map((s) => (
                                            <button
                                              key={s}
                                              type="button"
                                              onClick={() => void handleStateChange(desvio.id_gestion, s)}
                                              disabled={updatingId === desvio.id_gestion}
                                              className="rounded border border-gray-300 bg-white px-2.5 py-1 text-xs font-semibold text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
                                            >
                                              {gestionStateLabel(s)}
                                            </button>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {desvio.plan_accion && (
                                      <div className="rounded border-l-4 border-blue-400 bg-blue-50 p-3">
                                        <p className="text-xs font-semibold text-blue-900">Plan de acción:</p>
                                        <p className="text-sm text-blue-800 mt-1">{desvio.plan_accion}</p>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </tbody>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </AppLayout>
  );
}

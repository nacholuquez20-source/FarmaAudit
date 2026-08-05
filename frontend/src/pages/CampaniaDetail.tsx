import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Check, Package, RotateCcw, TrendingUp } from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { Button } from '../components/Button';
import { Input } from '../components/Input';
import { Select } from '../components/Select';
import { useAuth } from '../hooks/useAuth';
import {
  getCampaniaById,
  getCampaniaTareas,
  updateCampaniaTarea,
  createCampaniaEvento,
  getSolicitudesInsumoPorTareas,
  resolverSolicitudInsumo,
  createCampaniaResultado,
  getCampaniaResultados,
} from '../lib/api';
import { formatDate, formatDateTime } from '../lib/utils';
import type { Campania, CampaniaTarea, CampaniaTareaEstado, CampaniaResultado, SolicitudInsumo } from '../types';

const TAREA_ESTADO_STYLES: Record<CampaniaTareaEstado, string> = {
  Pendiente: 'bg-gray-100 text-gray-600',
  Completada: 'bg-amber-100 text-amber-800',
  Bloqueada_por_insumo: 'bg-red-100 text-red-700',
  Verificada: 'bg-emerald-100 text-emerald-800',
};

const TAREA_ESTADO_LABELS: Record<CampaniaTareaEstado, string> = {
  Pendiente: 'Pendiente',
  Completada: 'Completada · a verificar',
  Bloqueada_por_insumo: 'Falta insumo',
  Verificada: 'Verificada',
};

export default function CampaniaDetail() {
  const { id } = useParams<{ id: string }>();
  const { user, profile } = useAuth();
  const [campania, setCampania] = useState<Campania | null>(null);
  const [tareas, setTareas] = useState<CampaniaTarea[]>([]);
  const [solicitudes, setSolicitudes] = useState<SolicitudInsumo[]>([]);
  const [resultados, setResultados] = useState<CampaniaResultado[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingTareaId, setUpdatingTareaId] = useState<string | null>(null);
  const [resolvingInsumoId, setResolvingInsumoId] = useState<string | null>(null);

  const [ventaSucursal, setVentaSucursal] = useState('');
  const [ventaCampania, setVentaCampania] = useState('');
  const [ventaBase, setVentaBase] = useState('');
  const [ventaUnidad, setVentaUnidad] = useState<'unidades' | 'pesos'>('unidades');
  const [savingResultado, setSavingResultado] = useState(false);

  const load = async () => {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const [campaniaData, tareasData, resultadosData] = await Promise.all([
        getCampaniaById(id),
        getCampaniaTareas(id),
        getCampaniaResultados(id),
      ]);
      setCampania(campaniaData);
      setTareas(tareasData);
      setResultados(resultadosData);
      const solicitudesData = await getSolicitudesInsumoPorTareas(tareasData.map((t) => t.id));
      setSolicitudes(solicitudesData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar la campania');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const bySucursal = useMemo(() => {
    const map = new Map<string, { nombre: string; tareas: CampaniaTarea[] }>();
    tareas.forEach((tarea) => {
      const key = tarea.id_sucursal;
      if (!map.has(key)) map.set(key, { nombre: tarea.sucursales?.nombre || key, tareas: [] });
      map.get(key)!.tareas.push(tarea);
    });
    return Array.from(map.entries()).map(([id_sucursal, value]) => ({ id_sucursal, ...value }));
  }, [tareas]);

  const acciones = useMemo(() => {
    const map = new Map<string, string>();
    tareas.forEach((tarea) => {
      if (tarea.campania_acciones) map.set(tarea.accion_id, tarea.campania_acciones.descripcion || tarea.campania_acciones.tipo);
    });
    return Array.from(map.entries());
  }, [tareas]);

  const pctCompletado = tareas.length
    ? Math.round((tareas.filter((t) => t.estado === 'Completada' || t.estado === 'Verificada').length / tareas.length) * 100)
    : 0;

  const solicitudesAbiertas = solicitudes.filter((s) => s.estado !== 'Recibido' && s.estado !== 'Rechazado');
  const actorNombre = profile?.nombre || user?.email || 'Auditor';

  const handleVerificar = async (tarea: CampaniaTarea) => {
    setUpdatingTareaId(tarea.id);
    try {
      const updated = await updateCampaniaTarea(tarea.id, { estado: 'Verificada' });
      setTareas((prev) => prev.map((t) => (t.id === tarea.id ? { ...t, ...updated } : t)));
      await createCampaniaEvento({ tarea_id: tarea.id, tipo: 'verificacion', comentario: 'Tarea verificada.', actor_id: user?.id, actor_nombre: actorNombre });
      toast.success('Tarea verificada');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo verificar la tarea');
    } finally {
      setUpdatingTareaId(null);
    }
  };

  const handleReabrir = async (tarea: CampaniaTarea) => {
    setUpdatingTareaId(tarea.id);
    try {
      const updated = await updateCampaniaTarea(tarea.id, { estado: 'Pendiente' });
      setTareas((prev) => prev.map((t) => (t.id === tarea.id ? { ...t, ...updated } : t)));
      await createCampaniaEvento({ tarea_id: tarea.id, tipo: 'rechazo', comentario: 'Tarea reabierta por el auditor.', actor_id: user?.id, actor_nombre: actorNombre });
      toast.success('Tarea reabierta');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo reabrir la tarea');
    } finally {
      setUpdatingTareaId(null);
    }
  };

  const handleResolverInsumo = async (insumo: SolicitudInsumo, nuevoEstado: SolicitudInsumo['estado']) => {
    setResolvingInsumoId(insumo.id);
    try {
      const updated = await resolverSolicitudInsumo(insumo, nuevoEstado, user?.id);
      setSolicitudes((prev) => prev.map((s) => (s.id === insumo.id ? updated : s)));
      if (nuevoEstado === 'Recibido') {
        setTareas((prev) => prev.map((t) => (t.id === insumo.tarea_id ? { ...t, estado: 'Pendiente' } : t)));
      }
      toast.success('Solicitud de insumo actualizada');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo actualizar la solicitud');
    } finally {
      setResolvingInsumoId(null);
    }
  };

  const handleSaveResultado = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!id || !ventaSucursal) return;
    setSavingResultado(true);
    try {
      const created = await createCampaniaResultado({
        campania_id: id,
        id_sucursal: ventaSucursal,
        venta_periodo_campania: ventaCampania ? Number(ventaCampania) : null,
        venta_periodo_base: ventaBase ? Number(ventaBase) : null,
        unidad: ventaUnidad,
        cargado_por: user?.id || null,
      });
      setResultados((prev) => [created, ...prev]);
      setVentaCampania('');
      setVentaBase('');
      toast.success('Venta real cargada');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo guardar la venta');
    } finally {
      setSavingResultado(false);
    }
  };

  if (loading) {
    return (
      <AppLayout title="Campania">
        <FeedbackState title="Cargando campania..." tone="loading" />
      </AppLayout>
    );
  }
  if (error || !campania) {
    return (
      <AppLayout title="Campania">
        <FeedbackState title={error || 'No se encontro la campania.'} tone="error" />
      </AppLayout>
    );
  }

  return (
    <AppLayout title={campania.nombre}>
      <div className="mb-6 rounded-lg bg-white p-5 shadow">
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded bg-primary-orange/10 px-2.5 py-1 text-xs font-semibold text-primary-orange">
            {campania.marcas?.nombre || 'Sin marca'}
          </span>
          <span className="rounded bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-800">{campania.estado}</span>
          {campania.acuerdo_hasta && (
            <span className="text-xs text-gray-500">Acuerdo vigente hasta {formatDate(campania.acuerdo_hasta)}</span>
          )}
          <span className="ml-auto text-sm font-semibold text-gray-500">{pctCompletado}% completado (compliance)</span>
        </div>
        {campania.contraprestacion && (
          <p className="mt-3 text-sm text-gray-600">Contraprestacion: {campania.contraprestacion}</p>
        )}
      </div>

      {solicitudesAbiertas.length > 0 && (
        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-bold text-amber-900">
            <Package className="h-4 w-4" />
            Solicitudes de insumo pendientes ({solicitudesAbiertas.length})
          </h2>
          <div className="space-y-3">
            {solicitudesAbiertas.map((insumo) => {
              const tarea = tareas.find((t) => t.id === insumo.tarea_id);
              const esLabo = insumo.proveedor === 'laboratorio_apm';
              return (
                <div key={insumo.id} className="rounded-lg bg-white p-3 shadow-sm">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
                    <span className="font-bold text-gray-900">{tarea?.sucursales?.nombre || insumo.tarea_id}</span>
                    <span>·</span>
                    <span className={`rounded px-2 py-0.5 font-semibold ${esLabo ? 'bg-purple-100 text-purple-800' : 'bg-blue-100 text-blue-800'}`}>
                      {esLabo ? 'Proveedor: laboratorio / APM' : 'Proveedor: cadena'}
                    </span>
                    <span className="rounded bg-gray-100 px-2 py-0.5 font-semibold text-gray-700">{insumo.estado}</span>
                  </div>
                  <p className="mt-1 text-sm text-gray-800">{insumo.tipo_insumo}: {insumo.detalle} {insumo.cantidad ? `(${insumo.cantidad})` : ''}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {esLabo ? (
                      <Button size="sm" variant="outline" disabled={resolvingInsumoId === insumo.id} onClick={() => void handleResolverInsumo(insumo, 'Recibido')}>
                        Marcar material recibido
                      </Button>
                    ) : (
                      <>
                        {insumo.estado === 'Solicitado' && (
                          <Button size="sm" variant="outline" disabled={resolvingInsumoId === insumo.id} onClick={() => void handleResolverInsumo(insumo, 'Aprobado')}>
                            Aprobar
                          </Button>
                        )}
                        {insumo.estado === 'Aprobado' && (
                          <Button size="sm" variant="outline" disabled={resolvingInsumoId === insumo.id} onClick={() => void handleResolverInsumo(insumo, 'Enviado')}>
                            Marcar enviado
                          </Button>
                        )}
                        {(insumo.estado === 'Aprobado' || insumo.estado === 'Enviado') && (
                          <Button size="sm" variant="outline" disabled={resolvingInsumoId === insumo.id} onClick={() => void handleResolverInsumo(insumo, 'Recibido')}>
                            Marcar recibido
                          </Button>
                        )}
                        {insumo.estado === 'Solicitado' && (
                          <Button size="sm" variant="danger" disabled={resolvingInsumoId === insumo.id} onClick={() => void handleResolverInsumo(insumo, 'Rechazado')}>
                            Rechazar
                          </Button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="mb-6 overflow-x-auto rounded-lg bg-white shadow">
        <table className="w-full min-w-[640px]">
          <thead className="border-b bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-bold uppercase text-gray-500">Sucursal</th>
              {acciones.map(([accionId, label]) => (
                <th key={accionId} className="px-4 py-3 text-left text-xs font-bold uppercase text-gray-500">{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {bySucursal.length === 0 ? (
              <tr>
                <td colSpan={acciones.length + 1} className="px-4 py-8 text-center text-sm text-gray-500">
                  Todavia no hay tareas generadas.
                </td>
              </tr>
            ) : (
              bySucursal.map((grupo) => (
                <tr key={grupo.id_sucursal} className="border-b last:border-b-0">
                  <td className="px-4 py-3 align-top font-semibold text-gray-900">{grupo.nombre}</td>
                  {acciones.map(([accionId]) => {
                    const tarea = grupo.tareas.find((t) => t.accion_id === accionId);
                    if (!tarea) return <td key={accionId} className="px-4 py-3 text-gray-300">-</td>;
                    return (
                      <td key={accionId} className="px-4 py-3 align-top">
                        <span className={`inline-flex rounded px-2 py-1 text-xs font-semibold ${TAREA_ESTADO_STYLES[tarea.estado]}`}>
                          {TAREA_ESTADO_LABELS[tarea.estado]}
                        </span>
                        {tarea.estado === 'Completada' && (
                          <div className="mt-1 flex gap-1">
                            <button
                              type="button"
                              disabled={updatingTareaId === tarea.id}
                              onClick={() => void handleVerificar(tarea)}
                              className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-1 text-[11px] font-bold text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
                            >
                              <Check className="h-3 w-3" /> Verificar
                            </button>
                            <button
                              type="button"
                              disabled={updatingTareaId === tarea.id}
                              onClick={() => void handleReabrir(tarea)}
                              className="inline-flex items-center gap-1 rounded bg-red-50 px-2 py-1 text-[11px] font-bold text-red-700 hover:bg-red-100 disabled:opacity-50"
                            >
                              <RotateCcw className="h-3 w-3" /> Reabrir
                            </button>
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="rounded-lg bg-white p-5 shadow">
        <h2 className="mb-1 flex items-center gap-2 text-sm font-bold text-gray-900">
          <TrendingUp className="h-4 w-4" />
          Venta real (sell-out)
        </h2>
        <p className="mb-4 text-xs text-gray-500">
          El % de tareas completadas mide cumplimiento, no si la campania vendio. Carga manual: venta del periodo de
          campania vs. periodo base.
        </p>
        <form onSubmit={(e) => void handleSaveResultado(e)} className="grid grid-cols-1 gap-3 sm:grid-cols-4">
          <Select
            options={bySucursal.map((g) => ({ value: g.id_sucursal, label: g.nombre }))}
            placeholder="Sucursal"
            value={ventaSucursal}
            onChange={(e) => setVentaSucursal(e.target.value)}
          />
          <Input type="number" placeholder="Venta periodo campania" value={ventaCampania} onChange={(e) => setVentaCampania(e.target.value)} />
          <Input type="number" placeholder="Venta periodo base" value={ventaBase} onChange={(e) => setVentaBase(e.target.value)} />
          <div className="flex gap-2">
            <Select
              options={[{ value: 'unidades', label: 'Unidades' }, { value: 'pesos', label: 'Pesos' }]}
              value={ventaUnidad}
              onChange={(e) => setVentaUnidad(e.target.value as 'unidades' | 'pesos')}
            />
            <Button type="submit" disabled={!ventaSucursal || savingResultado} isLoading={savingResultado}>Guardar</Button>
          </div>
        </form>

        {resultados.length > 0 && (
          <table className="mt-4 w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-gray-400">
                <th className="py-1">Sucursal</th>
                <th className="py-1">Campania</th>
                <th className="py-1">Base</th>
                <th className="py-1">Unidad</th>
                <th className="py-1">Cargado</th>
              </tr>
            </thead>
            <tbody>
              {resultados.map((resultado) => (
                <tr key={resultado.id} className="border-t border-gray-100">
                  <td className="py-1.5">{bySucursal.find((g) => g.id_sucursal === resultado.id_sucursal)?.nombre || resultado.id_sucursal}</td>
                  <td className="py-1.5">{resultado.venta_periodo_campania ?? '-'}</td>
                  <td className="py-1.5">{resultado.venta_periodo_base ?? '-'}</td>
                  <td className="py-1.5">{resultado.unidad}</td>
                  <td className="py-1.5 text-gray-400">{formatDateTime(resultado.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </AppLayout>
  );
}

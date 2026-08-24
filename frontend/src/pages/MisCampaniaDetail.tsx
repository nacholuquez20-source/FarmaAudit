import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Check, Package } from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { Button } from '../components/Button';
import { Input } from '../components/Input';
import { Select } from '../components/Select';
import { useAuth } from '../hooks/useAuth';
import {
  getMisCampaniaTareas,
  updateCampaniaTarea,
  createCampaniaEvento,
  createSolicitudInsumo,
  getSignedUrl,
} from '../lib/api';
import type { CampaniaTarea, SolicitudInsumoProveedor, SolicitudInsumoTipo } from '../types';

const TIPO_INSUMO_OPTIONS: { value: SolicitudInsumoTipo; label: string }[] = [
  { value: 'carteleria', label: 'Carteleria' },
  { value: 'material_pop', label: 'Material POP' },
  { value: 'stock', label: 'Stock / producto' },
  { value: 'otro', label: 'Otro' },
];

/** Foto de "asi debe quedar" cargada por el auditor en el wizard, si la accion tiene una. */
function ReferenciaImage({ path }: { path: string }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getSignedUrl(path)
      .then((signed) => {
        if (!cancelled) setUrl(signed);
      })
      .catch(() => {
        /* Sin referencia visible si falla la firma; no bloquea el resto de la tarjeta. */
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  if (!url) return null;
  return (
    <div className="mt-3 rounded-lg border border-gray-200 p-2">
      <p className="mb-1.5 text-xs font-semibold text-gray-500">Así debería quedar</p>
      <img src={url} alt="Referencia" className="max-h-40 rounded-md object-cover" />
    </div>
  );
}

export default function MisCampaniaDetail() {
  const { id: campaniaId } = useParams<{ id: string }>();
  const { user, profile } = useAuth();
  const sucursalId = profile?.id_sucursal ?? null;

  const [tareas, setTareas] = useState<CampaniaTarea[]>([]);
  // Arranca en false si el perfil todavia no trajo sucursal: sin sucursal no
  // hay nada que cargar, y dejarlo en true colgaria el spinner para siempre.
  const [loading, setLoading] = useState(Boolean(profile?.id_sucursal));
  const [error, setError] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [insumoTareaId, setInsumoTareaId] = useState<string | null>(null);
  const [insumoTipo, setInsumoTipo] = useState<SolicitudInsumoTipo>('material_pop');
  const [insumoDetalle, setInsumoDetalle] = useState('');
  const [insumoCantidad, setInsumoCantidad] = useState('');
  const [insumoProveedor, setInsumoProveedor] = useState<SolicitudInsumoProveedor>('laboratorio_apm');
  const [submittingInsumo, setSubmittingInsumo] = useState(false);

  // Al cambiar de campania sin desmontar la pagina hay que volver al spinner,
  // si no se ven las tareas de la anterior mientras carga la nueva. Se ajusta
  // durante el render (patron de React para estado derivado) y no en el efecto,
  // donde un setState sincronico dispara un render en cascada.
  const claveCarga = `${campaniaId}|${sucursalId ?? ''}`;
  const [prevClave, setPrevClave] = useState(claveCarga);
  if (prevClave !== claveCarga) {
    setPrevClave(claveCarga);
    setLoading(Boolean(sucursalId));
    setError(null);
  }

  // El primer statement es el await a proposito (ver comentario de arriba).
  useEffect(() => {
    if (!sucursalId) return;
    let cancelled = false;
    void (async () => {
      try {
        const data = await getMisCampaniaTareas(sucursalId);
        if (!cancelled) setTareas(data.filter((tarea) => tarea.campania_id === campaniaId));
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Error al cargar la campania');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [campaniaId, sucursalId]);

  const actorNombre = profile?.nombre || user?.email || 'Encargado';

  const handleMarcarHecho = async (tarea: CampaniaTarea) => {
    setUpdatingId(tarea.id);
    try {
      const updated = await updateCampaniaTarea(tarea.id, { estado: 'Completada', vista_at: tarea.vista_at || new Date().toISOString() });
      setTareas((prev) => prev.map((t) => (t.id === tarea.id ? { ...t, ...updated } : t)));
      await createCampaniaEvento({ tarea_id: tarea.id, tipo: 'completada', comentario: 'Marcado como hecho desde la web.', actor_id: user?.id, actor_nombre: actorNombre });
      toast.success('Tarea marcada como hecha');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo actualizar la tarea');
    } finally {
      setUpdatingId(null);
    }
  };

  const openInsumoForm = (tarea: CampaniaTarea) => {
    setInsumoTareaId(tarea.id);
    setInsumoTipo('material_pop');
    setInsumoDetalle('');
    setInsumoCantidad('');
    setInsumoProveedor('laboratorio_apm');
  };

  const handleSubmitInsumo = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!insumoTareaId) return;
    setSubmittingInsumo(true);
    try {
      await createSolicitudInsumo({
        tarea_id: insumoTareaId,
        tipo_insumo: insumoTipo,
        detalle: insumoDetalle.trim() || undefined,
        cantidad: insumoCantidad.trim() || undefined,
        proveedor: insumoProveedor,
      });
      const updated = await updateCampaniaTarea(insumoTareaId, { estado: 'Bloqueada_por_insumo' });
      setTareas((prev) => prev.map((t) => (t.id === insumoTareaId ? { ...t, ...updated } : t)));
      await createCampaniaEvento({ tarea_id: insumoTareaId, tipo: 'bloqueo_insumo', comentario: `Falta insumo: ${insumoDetalle || insumoTipo}`, actor_id: user?.id, actor_nombre: actorNombre });
      toast.success('Solicitud de insumo enviada');
      setInsumoTareaId(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo enviar la solicitud');
    } finally {
      setSubmittingInsumo(false);
    }
  };

  if (!sucursalId) {
    return (
      <AppLayout title="Campania">
        <FeedbackState title="Tu usuario no tiene una sucursal asignada." tone="warning" />
      </AppLayout>
    );
  }

  if (loading) {
    return (
      <AppLayout title="Campania">
        <FeedbackState title="Cargando..." tone="loading" />
      </AppLayout>
    );
  }

  if (error) {
    return (
      <AppLayout title="Campania">
        <FeedbackState title={error} tone="error" />
      </AppLayout>
    );
  }

  const campaniaNombre = tareas[0]?.campanias?.nombre || 'Campania';
  const marcaNombre = tareas[0]?.campanias?.marcas?.nombre || '';

  return (
    <AppLayout title={campaniaNombre}>
      {marcaNombre && <p className="mb-4 text-sm text-gray-500">Marca: {marcaNombre}</p>}

      {tareas.length === 0 ? (
        <FeedbackState title="No hay tareas para tu sucursal en esta campania." />
      ) : (
        <div className="space-y-3">
          {tareas.map((tarea) => {
            const label = tarea.campania_acciones?.descripcion || tarea.campania_acciones?.tipo || 'Tarea';
            const verificablePorFoto = tarea.campania_acciones?.verificable_por_foto ?? true;
            const done = tarea.estado === 'Completada' || tarea.estado === 'Verificada';
            return (
              <div key={tarea.id} className="rounded-lg bg-white p-4 shadow">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="font-semibold text-gray-900">{label}</div>
                    {!verificablePorFoto && <div className="text-xs text-gray-400">Accion administrativa, sin foto</div>}
                  </div>
                  <span
                    className={`shrink-0 rounded px-2.5 py-1 text-xs font-semibold ${
                      done ? 'bg-emerald-100 text-emerald-800' : tarea.estado === 'Bloqueada_por_insumo' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {tarea.estado === 'Pendiente' ? 'Pendiente' : tarea.estado === 'Bloqueada_por_insumo' ? 'Falta insumo' : tarea.estado === 'Completada' ? 'Hecho, a verificar' : 'Verificada'}
                  </span>
                </div>

                {tarea.campania_acciones?.imagen_referencia_path && (
                  <ReferenciaImage path={tarea.campania_acciones.imagen_referencia_path} />
                )}

                {tarea.estado === 'Pendiente' && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button size="sm" disabled={updatingId === tarea.id} onClick={() => void handleMarcarHecho(tarea)}>
                      <span className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5" /> Marcar hecho</span>
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => openInsumoForm(tarea)}>
                      <span className="inline-flex items-center gap-1.5"><Package className="h-3.5 w-3.5" /> Falta insumo</span>
                    </Button>
                  </div>
                )}

                {insumoTareaId === tarea.id && (
                  <form onSubmit={(e) => void handleSubmitInsumo(e)} className="mt-3 space-y-2 rounded-lg border border-gray-200 p-3">
                    <Select
                      label="Que falta"
                      options={TIPO_INSUMO_OPTIONS}
                      value={insumoTipo}
                      onChange={(e) => setInsumoTipo(e.target.value as SolicitudInsumoTipo)}
                    />
                    <Input
                      label="Detalle"
                      value={insumoDetalle}
                      onChange={(e) => setInsumoDetalle(e.target.value)}
                      placeholder="Ej: Cartel de precio talle grande"
                    />
                    <Input
                      label="Cantidad (opcional)"
                      value={insumoCantidad}
                      onChange={(e) => setInsumoCantidad(e.target.value)}
                    />
                    <Select
                      label="Quien lo provee"
                      options={[
                        { value: 'laboratorio_apm', label: 'Laboratorio / APM (material de marca)' },
                        { value: 'cadena', label: 'Cadena (mueble, cartel propio)' },
                      ]}
                      value={insumoProveedor}
                      onChange={(e) => setInsumoProveedor(e.target.value as SolicitudInsumoProveedor)}
                      helperText="Si dudas, elegi Laboratorio/APM: es lo mas comun para material de campana."
                    />
                    <div className="flex justify-end gap-2 pt-1">
                      <Button type="button" variant="outline" size="sm" onClick={() => setInsumoTareaId(null)}>Cancelar</Button>
                      <Button type="submit" size="sm" disabled={submittingInsumo} isLoading={submittingInsumo}>Enviar solicitud</Button>
                    </div>
                  </form>
                )}
              </div>
            );
          })}
        </div>
      )}
    </AppLayout>
  );
}

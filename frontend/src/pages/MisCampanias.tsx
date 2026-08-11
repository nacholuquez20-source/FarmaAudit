import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Megaphone } from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { useAuth } from '../hooks/useAuth';
import { getMisCampaniaTareas } from '../lib/api';
import type { CampaniaTarea } from '../types';

export default function MisCampanias() {
  const { profile } = useAuth();
  const sucursalId = profile?.id_sucursal ?? null;
  const [tareas, setTareas] = useState<CampaniaTarea[]>([]);
  // Arranca en false si el perfil todavia no trajo sucursal: sin sucursal no
  // hay nada que cargar, y dejarlo en true colgaria el spinner para siempre.
  const [loading, setLoading] = useState(Boolean(profile?.id_sucursal));
  const [error, setError] = useState<string | null>(null);

  // Al cambiar de sucursal hay que volver al spinner. Se ajusta durante el
  // render (patron de React para estado derivado) y no en el efecto, donde un
  // setState sincronico dispara un render en cascada.
  const [prevSucursalId, setPrevSucursalId] = useState(sucursalId);
  if (prevSucursalId !== sucursalId) {
    setPrevSucursalId(sucursalId);
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
        if (!cancelled) setTareas(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Error al cargar campanias');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sucursalId]);

  const campanias = useMemo(() => {
    const map = new Map<string, { nombre: string; marca: string; total: number; pendientes: number }>();
    tareas.forEach((tarea) => {
      const campaniaInfo = tarea.campanias;
      const key = tarea.campania_id;
      if (!map.has(key)) {
        map.set(key, { nombre: campaniaInfo?.nombre || 'Campania', marca: campaniaInfo?.marcas?.nombre || '', total: 0, pendientes: 0 });
      }
      const entry = map.get(key)!;
      entry.total += 1;
      if (tarea.estado === 'Pendiente' || tarea.estado === 'Bloqueada_por_insumo') entry.pendientes += 1;
    });
    return Array.from(map.entries()).map(([id, value]) => ({ id, ...value }));
  }, [tareas]);

  if (!sucursalId) {
    return (
      <AppLayout title="Mis Campanias">
        <FeedbackState
          title="Tu usuario no tiene una sucursal asignada."
          description="Pedile a un admin que te asigne una sucursal en Admin > Usuarios del panel."
          tone="warning"
        />
      </AppLayout>
    );
  }

  return (
    <AppLayout title="Mis Campanias">
      <div className="mb-6">
        <p className="text-sm text-gray-600">{campanias.reduce((acc, c) => acc + c.pendientes, 0)} tareas de campana pendientes.</p>
      </div>

      {loading && <FeedbackState title="Cargando campanias..." tone="loading" />}
      {error && <FeedbackState title={error} tone="error" />}
      {!loading && !error && campanias.length === 0 && (
        <FeedbackState title="No hay campanias activas para tu sucursal." />
      )}

      {!loading && !error && campanias.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {campanias.map((campania) => (
            <Link
              key={campania.id}
              to={`/mis-campanias/${campania.id}`}
              className="rounded-lg bg-white p-5 shadow transition hover:-translate-y-0.5 hover:shadow-md"
            >
              <span className="mb-3 inline-flex items-center gap-1.5 rounded bg-primary-orange/10 px-2.5 py-1 text-xs font-semibold text-primary-orange">
                <Megaphone className="h-3.5 w-3.5" />
                {campania.marca}
              </span>
              <h2 className="mb-2 text-lg font-semibold text-gray-900">{campania.nombre}</h2>
              <p className="text-sm text-gray-600">
                {campania.pendientes === 0 ? 'Todo completado' : `${campania.pendientes} de ${campania.total} tareas pendientes`}
              </p>
            </Link>
          ))}
        </div>
      )}
    </AppLayout>
  );
}

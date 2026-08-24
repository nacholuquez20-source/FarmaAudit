import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Megaphone, Plus } from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { getCampanias } from '../lib/api';
import { formatDate } from '../lib/utils';
import type { Campania, CampaniaEstado } from '../types';

const ESTADO_STYLES: Record<CampaniaEstado, string> = {
  Borrador: 'bg-gray-100 text-gray-700',
  Activa: 'bg-emerald-100 text-emerald-800',
  En_seguimiento: 'bg-blue-100 text-blue-800',
  Finalizada: 'bg-gray-200 text-gray-600',
  Cancelada: 'bg-red-100 text-red-700',
};

const ESTADO_LABELS: Record<CampaniaEstado, string> = {
  Borrador: 'Borrador',
  Activa: 'Activa',
  En_seguimiento: 'En seguimiento',
  Finalizada: 'Finalizada',
  Cancelada: 'Cancelada',
};

export default function Campanias() {
  const [campanias, setCampanias] = useState<Campania[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        setCampanias(await getCampanias());
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error al cargar campanias');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  return (
    <AppLayout title="Campanias">
      <div className="mb-6 flex items-center justify-between">
        <p className="text-sm text-gray-600">
          Campanias de marca por sucursal: exhibicion, material POP, burbuja de precio, descuento en caja.
        </p>
        <Link
          to="/campanias/nueva"
          className="inline-flex items-center gap-2 rounded-lg bg-primary-navy px-4 py-2 text-sm font-semibold text-white hover:bg-primary-navy/90"
        >
          <Plus className="h-4 w-4" />
          Nueva campania
        </Link>
      </div>

      {loading && <FeedbackState title="Cargando campanias..." tone="loading" />}
      {error && <FeedbackState title={error} tone="error" />}

      {!loading && !error && campanias.length === 0 && (
        <FeedbackState
          title="Todavia no hay campanias cargadas."
          description="Crea la primera desde 'Nueva campania'. Necesitas al menos una marca activa en Admin > Marcas."
        />
      )}

      {!loading && !error && campanias.length > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {campanias.map((campania) => (
            <Link
              key={campania.id}
              to={`/campanias/${campania.id}`}
              className="rounded-lg bg-white p-5 shadow transition hover:-translate-y-0.5 hover:shadow-md"
            >
              <div className="mb-3 flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 rounded bg-primary-orange/10 px-2.5 py-1 text-xs font-semibold text-primary-orange">
                  <Megaphone className="h-3.5 w-3.5" />
                  {campania.tipo === 'tour_interno' ? 'Tour de Farmacias' : campania.marcas?.nombre || 'Sin marca'}
                </span>
                <span className={`rounded px-2.5 py-1 text-xs font-semibold ${ESTADO_STYLES[campania.estado]}`}>
                  {ESTADO_LABELS[campania.estado]}
                </span>
              </div>
              <h2 className="mb-2 text-lg font-semibold text-gray-900">{campania.nombre}</h2>
              <div className="grid grid-cols-2 gap-3 text-sm text-gray-600">
                <div>
                  <div className="text-xs uppercase text-gray-400">Inicio</div>
                  <div className="font-medium text-gray-800">{campania.fecha_inicio ? formatDate(campania.fecha_inicio) : '-'}</div>
                </div>
                <div>
                  <div className="text-xs uppercase text-gray-400">Acuerdo hasta</div>
                  <div className="font-medium text-gray-800">{campania.acuerdo_hasta ? formatDate(campania.acuerdo_hasta) : '-'}</div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </AppLayout>
  );
}

import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { APIProvider, AdvancedMarker, InfoWindow, Map as GoogleMap, Pin, useMap } from '@vis.gl/react-google-maps';
import { AlertTriangle, MapPin } from 'lucide-react';
import { FeedbackState } from './FeedbackState';
import { getSucursalesDashboard } from '../lib/api';
import { SALUD_HEX, SALUD_META } from '../lib/salud';
import type { SucursalDashboard } from '../types';

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined;
// Map ID de prueba de Google, habilita AdvancedMarker sin crear uno propio.
// Para produccion, crear un Map ID en Google Cloud Console > Map Management
// y configurarlo en VITE_GOOGLE_MAP_ID.
const GOOGLE_MAP_ID = (import.meta.env.VITE_GOOGLE_MAP_ID as string | undefined) || 'DEMO_MAP_ID';

const DEFAULT_CENTER = { lat: -34.6037, lng: -58.3816 };
const DEFAULT_ZOOM = 11;

const SALUD_COLOR = SALUD_HEX;

// Ajusta el encuadre a los pines visibles cada vez que cambia el set (carga
// inicial o filtro de zona) — no hay un centro/zoom fijo porque no sabemos
// de antemano donde va a pinear el admin cada sucursal.
function FitToMarkers({ points }: { points: google.maps.LatLngLiteral[] }) {
  const map = useMap();
  useEffect(() => {
    if (!map || points.length === 0) return;
    if (points.length === 1) {
      map.setCenter(points[0]);
      map.setZoom(15);
      return;
    }
    const bounds = new google.maps.LatLngBounds();
    points.forEach((point) => bounds.extend(point));
    map.fitBounds(bounds, 32);
  }, [map, points]);
  return null;
}

function SucursalPin({ sucursal }: { sucursal: SucursalDashboard }) {
  const [open, setOpen] = useState(false);
  return (
    <AdvancedMarker
      position={{ lat: sucursal.lat as number, lng: sucursal.lng as number }}
      onClick={() => setOpen(true)}
    >
      <Pin
        background={SALUD_COLOR[sucursal.estado_salud]}
        borderColor="white"
        glyphColor="white"
      />
      {open && (
        <InfoWindow onCloseClick={() => setOpen(false)}>
          <div className="min-w-[200px]">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="font-semibold text-gray-900">{sucursal.nombre}</span>
              <span
                className="rounded-full px-2 py-0.5 text-xs font-semibold text-white"
                style={{ backgroundColor: SALUD_COLOR[sucursal.estado_salud] }}
              >
                {SALUD_META[sucursal.estado_salud].label}
              </span>
            </div>
            <p className="mb-2 text-xs text-gray-500">{sucursal.zona || 'Sin zona'}</p>
            <div className="mb-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-gray-700">
              <span>Puntaje: <strong>{sucursal.ultimo_score != null ? sucursal.ultimo_score.toFixed(1) : '—'}</strong></span>
              <span>Abiertos: <strong>{sucursal.desvios_abiertos}</strong></span>
              <span>Vencidos: <strong className="text-red-700">{sucursal.desvios_vencidos}</strong></span>
            </div>
            <Link to={`/sucursales/${sucursal.id}`} className="text-xs font-medium text-blue-600 hover:text-blue-800">
              Ver ficha →
            </Link>
          </div>
        </InfoWindow>
      )}
    </AdvancedMarker>
  );
}

export function SucursalesMap() {
  const [data, setData] = useState<SucursalDashboard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zonasActivas, setZonasActivas] = useState<Set<string> | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSucursalesDashboard()
      .then((rows) => {
        if (cancelled) return;
        setData(rows);
        setZonasActivas(new Set(rows.map((r) => r.zona || 'Sin zona')));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'No se pudieron cargar las sucursales');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const zonas = useMemo(() => {
    if (!data) return [];
    const counts = new Map<string, number>();
    for (const s of data) {
      const zona = s.zona || 'Sin zona';
      counts.set(zona, (counts.get(zona) || 0) + 1);
    }
    return Array.from(counts.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [data]);

  const ubicadas = useMemo(
    () => (data || []).filter((s) => s.lat != null && s.lng != null),
    [data],
  );
  const sinUbicar = (data || []).length - ubicadas.length;

  const visibles = useMemo(
    () => ubicadas.filter((s) => !zonasActivas || zonasActivas.has(s.zona || 'Sin zona')),
    [ubicadas, zonasActivas],
  );

  const puntos = useMemo<google.maps.LatLngLiteral[]>(
    () => visibles.map((s) => ({ lat: s.lat as number, lng: s.lng as number })),
    [visibles],
  );

  const toggleZona = (zona: string) => {
    setZonasActivas((current) => {
      const next = new Set(current);
      if (next.has(zona)) next.delete(zona);
      else next.add(zona);
      return next;
    });
  };

  if (error) return <FeedbackState title={error} tone="error" />;
  if (!data) return <FeedbackState title="Cargando mapa..." tone="loading" />;
  if (!GOOGLE_MAPS_API_KEY) {
    return (
      <FeedbackState
        title="Falta configurar Google Maps"
        description="Definí VITE_GOOGLE_MAPS_API_KEY en el .env del frontend para mostrar el mapa."
        tone="error"
      />
    );
  }

  return (
    <div className="rounded-lg bg-white p-6 shadow">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Mapa de sucursales</h2>
        {sinUbicar > 0 && (
          <Link
            to="/admin?tab=sucursales"
            className="flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800 hover:bg-amber-100"
          >
            <AlertTriangle className="h-3.5 w-3.5" />
            Sin ubicar ({sinUbicar})
          </Link>
        )}
      </div>

      {zonas.length > 1 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {zonas.map(([zona, count]) => {
            const active = zonasActivas?.has(zona) ?? true;
            return (
              <button
                key={zona}
                type="button"
                onClick={() => toggleZona(zona)}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                  active
                    ? 'border-primary-navy bg-primary-navy text-white'
                    : 'border-gray-300 bg-white text-gray-500 hover:bg-gray-50'
                }`}
              >
                {zona} ({count})
              </button>
            );
          })}
        </div>
      )}

      {ubicadas.length === 0 ? (
        <FeedbackState
          title="Todavía no hay sucursales ubicadas en el mapa."
          description="Pineá cada sucursal desde Administración → Sucursales → Ubicar."
          tone="info"
        />
      ) : (
        <div className="h-[520px] w-full overflow-hidden rounded-lg border border-gray-200">
          <APIProvider apiKey={GOOGLE_MAPS_API_KEY}>
            <GoogleMap
              mapId={GOOGLE_MAP_ID}
              defaultCenter={DEFAULT_CENTER}
              defaultZoom={DEFAULT_ZOOM}
              gestureHandling="greedy"
              disableDefaultUI={false}
              streetViewControl={false}
              mapTypeControl={false}
            >
              <FitToMarkers points={puntos} />
              {visibles.map((s) => (
                <SucursalPin key={s.id} sucursal={s} />
              ))}
            </GoogleMap>
          </APIProvider>
        </div>
      )}

      <p className="mt-3 flex items-center gap-1.5 text-xs text-gray-400">
        <MapPin className="h-3 w-3" />
        {ubicadas.length} de {data.length} sucursales ubicadas en el mapa.
      </p>
    </div>
  );
}

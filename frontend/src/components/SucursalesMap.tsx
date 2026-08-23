import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { AlertTriangle, MapPin } from 'lucide-react';
import { FeedbackState } from './FeedbackState';
import { getSucursalesDashboard } from '../lib/api';
import type { EstadoSalud, SucursalDashboard } from '../types';

const DEFAULT_CENTER: [number, number] = [-34.6037, -58.3816];
const DEFAULT_ZOOM = 11;

// Misma paleta que SucursalesGrid.tsx (SALUD_META) — el color de salud se
// comunica igual en todo el panel, del grid semaforo al mapa.
const SALUD_COLOR: Record<EstadoSalud, string> = {
  critica: '#ef4444',
  atencion: '#f59e0b',
  ok: '#22c55e',
  sin_datos: '#9ca3af',
};

const SALUD_LABEL: Record<EstadoSalud, string> = {
  critica: 'Crítica',
  atencion: 'Atención',
  ok: 'Al día',
  sin_datos: 'Sin datos',
};

function makeIcon(color: string): L.DivIcon {
  return L.divIcon({
    className: '',
    html: `<div style="width:18px;height:18px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.5);"></div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    popupAnchor: [0, -9],
  });
}

const ICONS: Record<EstadoSalud, L.DivIcon> = {
  critica: makeIcon(SALUD_COLOR.critica),
  atencion: makeIcon(SALUD_COLOR.atencion),
  ok: makeIcon(SALUD_COLOR.ok),
  sin_datos: makeIcon(SALUD_COLOR.sin_datos),
};

// Ajusta el encuadre a los pines visibles cada vez que cambia el set (carga
// inicial o filtro de zona) — no hay un centro/zoom fijo porque no sabemos
// de antemano donde va a pinear el admin cada sucursal.
function FitToMarkers({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 15);
      return;
    }
    map.fitBounds(L.latLngBounds(points), { padding: [32, 32] });
  }, [map, points]);
  return null;
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

  const puntos = useMemo<[number, number][]>(
    () => visibles.map((s) => [s.lat as number, s.lng as number]),
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
          <MapContainer center={DEFAULT_CENTER} zoom={DEFAULT_ZOOM} style={{ height: '100%', width: '100%' }}>
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <FitToMarkers points={puntos} />
            {visibles.map((s) => (
              <Marker key={s.id} position={[s.lat as number, s.lng as number]} icon={ICONS[s.estado_salud]}>
                <Popup>
                  <div className="min-w-[200px]">
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="font-semibold text-gray-900">{s.nombre}</span>
                      <span
                        className="rounded-full px-2 py-0.5 text-xs font-semibold text-white"
                        style={{ backgroundColor: SALUD_COLOR[s.estado_salud] }}
                      >
                        {SALUD_LABEL[s.estado_salud]}
                      </span>
                    </div>
                    <p className="mb-2 text-xs text-gray-500">{s.zona || 'Sin zona'}</p>
                    <div className="mb-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-gray-700">
                      <span>Puntaje: <strong>{s.ultimo_score != null ? s.ultimo_score.toFixed(1) : '—'}</strong></span>
                      <span>Abiertos: <strong>{s.desvios_abiertos}</strong></span>
                      <span>Vencidos: <strong className="text-red-700">{s.desvios_vencidos}</strong></span>
                    </div>
                    <Link to={`/sucursales/${s.id}`} className="text-xs font-medium text-blue-600 hover:text-blue-800">
                      Ver ficha →
                    </Link>
                  </div>
                </Popup>
              </Marker>
            ))}
          </MapContainer>
        </div>
      )}

      <p className="mt-3 flex items-center gap-1.5 text-xs text-gray-400">
        <MapPin className="h-3 w-3" />
        {ubicadas.length} de {data.length} sucursales ubicadas en el mapa.
      </p>
    </div>
  );
}

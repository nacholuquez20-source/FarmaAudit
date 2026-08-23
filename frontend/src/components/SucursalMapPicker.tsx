import { useState } from 'react';
import { MapContainer, Marker, TileLayer, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Button } from './Button';
import { updateSucursal } from '../lib/api';
import type { Sucursal } from '../types';

// Fallback si la sucursal nunca fue pineada: CABA, centro geografico
// razonable para arrancar a ubicar sucursales de una cadena argentina.
const DEFAULT_CENTER: [number, number] = [-34.6037, -58.3816];
const DEFAULT_ZOOM = 12;
const PINNED_ZOOM = 16;

const pinIcon = L.divIcon({
  className: '',
  html: '<div style="width:24px;height:24px;border-radius:50% 50% 50% 0;background:#1e3a6d;border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,0.4);transform:rotate(-45deg);"></div>',
  iconSize: [24, 24],
  iconAnchor: [12, 24],
});

function ClickToPlace({ onPlace }: { onPlace: (lat: number, lng: number) => void }) {
  useMapEvents({
    click(event) {
      onPlace(event.latlng.lat, event.latlng.lng);
    },
  });
  return null;
}

interface SucursalMapPickerProps {
  sucursal: Sucursal;
  onClose: () => void;
  onSaved: (updated: Sucursal) => void;
}

// Picker de ubicacion para una sucursal: el admin hace click (o arrastra el
// pin) para fijar el punto y guarda. Deliberadamente manual — direcciones
// argentinas en texto libre no geocodifican de forma confiable, y esto es
// una tarea de una sola vez por sucursal (~25 en total).
export function SucursalMapPicker({ sucursal, onClose, onSaved }: SucursalMapPickerProps) {
  const hasPin = sucursal.lat != null && sucursal.lng != null;
  const [position, setPosition] = useState<[number, number] | null>(
    hasPin ? [sucursal.lat as number, sucursal.lng as number] : null,
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!position) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateSucursal(sucursal.id, { lat: position[0], lng: position[1] });
      onSaved(updated);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar la ubicacion');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <button type="button" aria-label="Cerrar" onClick={onClose} className="fixed inset-0 z-50 cursor-default bg-slate-950/40" />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
        <div
          role="dialog"
          aria-modal="true"
          onClick={(event) => event.stopPropagation()}
          className="flex w-full max-w-2xl flex-col gap-4 rounded-lg bg-white p-6 shadow-2xl"
        >
          <div>
            <h3 className="text-lg font-bold text-slate-950">Ubicar {sucursal.nombre}</h3>
            <p className="mt-1 text-sm text-slate-600">
              Hace click en el mapa para fijar el pin, o arrastralo para ajustar. {sucursal.direccion || 'Sin direccion cargada.'}
            </p>
          </div>

          <div className="h-96 w-full overflow-hidden rounded-lg border border-gray-300">
            <MapContainer
              center={position ?? DEFAULT_CENTER}
              zoom={position ? PINNED_ZOOM : DEFAULT_ZOOM}
              style={{ height: '100%', width: '100%' }}
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              <ClickToPlace onPlace={(lat, lng) => setPosition([lat, lng])} />
              {position && (
                <Marker
                  position={position}
                  icon={pinIcon}
                  draggable
                  eventHandlers={{
                    dragend: (event) => {
                      const marker = event.target as L.Marker;
                      const latLng = marker.getLatLng();
                      setPosition([latLng.lat, latLng.lng]);
                    },
                  }}
                />
              )}
            </MapContainer>
          </div>

          {error && <p className="text-sm text-red-700">{error}</p>}

          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">
              {position ? `${position[0].toFixed(5)}, ${position[1].toFixed(5)}` : 'Sin ubicar todavia'}
            </span>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
                Cancelar
              </Button>
              <Button type="button" variant="primary" onClick={handleSave} isLoading={saving} disabled={!position}>
                Guardar ubicacion
              </Button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

import { useState } from 'react';
import { APIProvider, AdvancedMarker, Map as GoogleMap, Pin } from '@vis.gl/react-google-maps';
import { Button } from './Button';
import { updateSucursal } from '../lib/api';
import type { Sucursal } from '../types';

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined;
const GOOGLE_MAP_ID = (import.meta.env.VITE_GOOGLE_MAP_ID as string | undefined) || 'DEMO_MAP_ID';

// Fallback si la sucursal nunca fue pineada: CABA, centro geografico
// razonable para arrancar a ubicar sucursales de una cadena argentina.
const DEFAULT_CENTER = { lat: -34.6037, lng: -58.3816 };
const DEFAULT_ZOOM = 12;
const PINNED_ZOOM = 16;

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
  const [position, setPosition] = useState<google.maps.LatLngLiteral | null>(
    hasPin ? { lat: sucursal.lat as number, lng: sucursal.lng as number } : null,
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!position) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateSucursal(sucursal.id, { lat: position.lat, lng: position.lng });
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
            {GOOGLE_MAPS_API_KEY ? (
              <APIProvider apiKey={GOOGLE_MAPS_API_KEY}>
                <GoogleMap
                  mapId={GOOGLE_MAP_ID}
                  defaultCenter={position ?? DEFAULT_CENTER}
                  defaultZoom={position ? PINNED_ZOOM : DEFAULT_ZOOM}
                  gestureHandling="greedy"
                  streetViewControl={false}
                  mapTypeControl={false}
                  onClick={(event) => {
                    const latLng = event.detail.latLng;
                    if (latLng) setPosition({ lat: latLng.lat, lng: latLng.lng });
                  }}
                >
                  {position && (
                    <AdvancedMarker
                      position={position}
                      draggable
                      onDragEnd={(event) => {
                        const latLng = event.latLng;
                        if (latLng) setPosition({ lat: latLng.lat(), lng: latLng.lng() });
                      }}
                    >
                      <Pin background="#1e3a6d" borderColor="white" glyphColor="white" />
                    </AdvancedMarker>
                  )}
                </GoogleMap>
              </APIProvider>
            ) : (
              <div className="flex h-full items-center justify-center bg-gray-50 px-6 text-center text-sm text-gray-500">
                Falta configurar VITE_GOOGLE_MAPS_API_KEY para mostrar el mapa.
              </div>
            )}
          </div>

          {error && <p className="text-sm text-red-700">{error}</p>}

          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">
              {position ? `${position.lat.toFixed(5)}, ${position.lng.toFixed(5)}` : 'Sin ubicar todavia'}
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

import { useState } from 'react';
import { Sparkles } from 'lucide-react';
import { getExplicacionSucursal } from '../lib/api';
import type { ExplicacionSucursal } from '../types';

const PRIORIDAD_DOT: Record<string, string> = {
  alta: 'bg-red-500',
  media: 'bg-amber-500',
  baja: 'bg-gray-300',
};

// Asistente contextual, no chat libre: un solo botón que dispara un único
// call a Claude con los datos que ya están en pantalla (ver
// sucursal_assistant.py) y muestra una explicación en lenguaje simple + hasta
// 3 acciones. Sin historial, sin poder ejecutar nada — WhatsApp sigue siendo
// el canal para actuar. Opt-in (no se dispara solo al entrar a la ficha):
// el call tarda ~10s y tiene costo, no tiene sentido pagarlo si el usuario
// solo pasó de largo por la sucursal.
export function AsistenteSucursal({ idSucursal }: { idSucursal: string }) {
  const [estado, setEstado] = useState<'idle' | 'loading' | 'error'>('idle');
  const [data, setData] = useState<ExplicacionSucursal | null>(null);

  const consultar = async () => {
    setEstado('loading');
    try {
      const res = await getExplicacionSucursal(idSucursal);
      setData(res);
      setEstado('idle');
    } catch {
      setEstado('error');
    }
  };

  if (estado === 'loading') {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-blue-100 bg-blue-50 px-3 py-3 text-sm text-blue-700">
        <Sparkles className="h-4 w-4 animate-pulse" />
        Consultando al asistente...
      </div>
    );
  }

  if (estado === 'error') {
    return (
      <div className="flex items-center justify-between gap-3 rounded-lg border border-red-100 bg-red-50 px-3 py-3 text-sm text-red-700">
        No se pudo generar la explicación.
        <button type="button" onClick={consultar} className="font-semibold underline">
          Reintentar
        </button>
      </div>
    );
  }

  if (data) {
    return (
      <div className="rounded-lg border border-blue-100 bg-blue-50/60 p-3 text-sm">
        <p className="flex items-center gap-1.5 font-semibold text-blue-900">
          <Sparkles className="h-3.5 w-3.5" />
          {data.resumen}
        </p>
        <p className="mt-1.5 text-blue-800">{data.por_que}</p>
        {data.acciones.length > 0 && (
          <ul className="mt-2.5 space-y-1.5">
            {data.acciones.map((a, i) => (
              <li key={i} className="flex items-start gap-2 text-blue-900">
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${PRIORIDAD_DOT[a.prioridad] || 'bg-gray-300'}`} />
                {a.texto}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={consultar}
      className="flex items-center gap-1.5 text-xs font-medium text-blue-600 underline decoration-dotted hover:text-blue-800"
    >
      <Sparkles className="h-3.5 w-3.5" />
      Preguntarle al asistente
    </button>
  );
}

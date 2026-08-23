import { useState } from 'react';
import { HelpCircle } from 'lucide-react';
import { SALUD_META } from '../lib/salud';
import type { EstadoSalud } from '../types';

const ORDEN: EstadoSalud[] = ['critica', 'atencion', 'ok', 'sin_datos'];

// No hay ningún glosario en la app hoy: nada explica qué significa "Crítica"
// vs "Atención", ni de qué datos sale. Un solo componente, reusado en
// Dashboard/Hoy/SucursalDetail, en vez de que cada pantalla invente su
// propia explicación (o ninguna).
export function SaludLegend() {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        className="inline-flex items-center gap-1 text-xs font-medium text-gray-400 transition hover:text-gray-600"
      >
        <HelpCircle className="h-3.5 w-3.5" />
        ¿Qué significa esto?
      </button>

      {open && (
        <div className="absolute left-0 top-full z-20 mt-2 w-72 rounded-lg border border-gray-200 bg-white p-3 text-left shadow-lg">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Estado de salud</p>
          <ul className="space-y-2.5">
            {ORDEN.map((estado) => {
              const meta = SALUD_META[estado];
              return (
                <li key={estado} className="flex items-start gap-2">
                  <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-white ${meta.dot}`}>
                    <meta.icon className="h-2.5 w-2.5" />
                  </span>
                  <div>
                    <p className="text-xs font-semibold text-gray-800">{meta.label}</p>
                    <p className="text-xs text-gray-500">{meta.descripcion}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

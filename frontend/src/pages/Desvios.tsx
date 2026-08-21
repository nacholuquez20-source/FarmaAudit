import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AppLayout } from '../components/AppLayout';
import { RevisionDesviosPanel } from './RevisionDesvios';
import { DesviosGestionPanel } from './DesviosGestion';
import { getDesviosBandejaCounts } from '../lib/api';
import { useMountedTabs } from '../hooks/useMountedTabs';
import type { DesvioBandeja } from '../types';

// Bandejas por turno: la pregunta que ordena el panel es de quien es la
// pelota, no en que estado esta el desvio. Ver ARQUITECTURA_PANEL_DESVIOS.md
// seccion 5.
const BANDEJAS: { key: DesvioBandeja; label: string; hint: string }[] = [
  { key: 'decidir', label: 'Requiere tu decision', hint: 'Borradores por aprobar y correcciones por revisar' },
  { key: 'esperando', label: 'Esperando al responsable', hint: 'Abiertos, en proceso y vencidos' },
  { key: 'cerrado', label: 'Resueltos / no corresponde', hint: 'Resueltos, cerrados y en gestion de terceros' },
];

function isBandeja(value: string | null): value is DesvioBandeja {
  return BANDEJAS.some((bandeja) => bandeja.key === value);
}

export default function Desvios() {
  const [params, setParams] = useSearchParams();
  const raw = params.get('v');

  // Los enlaces viejos (?v=revision / ?v=gestion) siguen entrando a algo
  // sensato en vez de romperse.
  const legacy: Record<string, DesvioBandeja> = { revision: 'decidir', gestion: 'esperando' };
  const activeTab: DesvioBandeja = isBandeja(raw) ? raw : (legacy[raw ?? ''] ?? 'decidir');

  const [counts, setCounts] = useState<Record<DesvioBandeja, number> | null>(null);

  useEffect(() => {
    // Un fallo de contadores no debe tapar el panel: se muestran sin numero.
    getDesviosBandejaCounts()
      .then(setCounts)
      .catch(() => setCounts(null));
  }, []);

  const { isMounted, markVisited } = useMountedTabs(activeTab);

  const setTab = (tab: DesvioBandeja) => {
    markVisited(tab);
    setParams({ v: tab }, { replace: true });
  };

  return (
    <AppLayout title="Desvios" contentClassName="max-w-none px-0 py-0">
      <div className="border-b border-slate-200 bg-white px-5 lg:px-8">
        <div className="flex gap-0 overflow-x-auto">
          {BANDEJAS.map((bandeja) => {
            const active = activeTab === bandeja.key;
            const count = counts?.[bandeja.key];
            return (
              <button
                key={bandeja.key}
                type="button"
                onClick={() => setTab(bandeja.key)}
                title={bandeja.hint}
                className={`flex shrink-0 items-center gap-2 border-b-2 px-5 py-4 text-sm font-semibold transition ${
                  active
                    ? 'border-primary-navy text-primary-navy'
                    : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
              >
                {bandeja.label}
                {count !== undefined && (
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                      bandeja.key === 'decidir' && count > 0
                        ? 'bg-primary-orange text-white'
                        : active
                          ? 'bg-primary-navy/10 text-primary-navy'
                          : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ display: activeTab === 'decidir' ? 'block' : 'none' }}>
        {isMounted('decidir') && (
          <>
            {/* Los dos grupos van separados porque la accion no es la misma:
                aprobar un borrador CREA una gestion, aprobar una correccion la
                CIERRA. */}
            <SectionHeading
              title="Hallazgos propuestos por la IA"
              description="Aprobar convierte el hallazgo en un desvio con responsable y plazo."
            />
            <RevisionDesviosPanel />
            <SectionHeading
              title="Correcciones enviadas por responsables"
              description="El responsable ya respondio por WhatsApp; aprobar cierra el desvio."
            />
            <DesviosGestionPanel bandeja="decidir" />
          </>
        )}
      </div>
      <div style={{ display: activeTab === 'esperando' ? 'block' : 'none' }}>
        {isMounted('esperando') && <DesviosGestionPanel bandeja="esperando" />}
      </div>
      <div style={{ display: activeTab === 'cerrado' ? 'block' : 'none' }}>
        {isMounted('cerrado') && <DesviosGestionPanel bandeja="cerrado" />}
      </div>
    </AppLayout>
  );
}

function SectionHeading({ title, description }: { title: string; description: string }) {
  return (
    <div className="border-b border-slate-200 bg-slate-50 px-5 py-3 lg:px-8">
      <h2 className="text-sm font-bold uppercase tracking-wide text-slate-700">{title}</h2>
      <p className="text-xs text-slate-500">{description}</p>
    </div>
  );
}

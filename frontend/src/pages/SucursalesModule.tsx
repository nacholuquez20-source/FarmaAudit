import { useSearchParams } from 'react-router-dom';
import { useMountedTabs } from '../hooks/useMountedTabs';
import { AppLayout } from '../components/AppLayout';
import { DashboardPanel } from './Dashboard';
import { AuditFichesGalleryPanel } from './AuditFichesGallery';

type SucursalesTabKey = 'analitica' | 'fichas';

const TABS: { key: SucursalesTabKey; label: string }[] = [
  { key: 'analitica', label: 'Analítica' },
  { key: 'fichas', label: 'Fichas de perfumería' },
];

function isSucursalesTabKey(value: string | null): value is SucursalesTabKey {
  return TABS.some((tab) => tab.key === value);
}

// Módulo "Sucursales" (consulta/historial) — fusiona la analítica de calidad
// (antes /dashboard para admin/auditor) y la galería de fichas de perfumería
// (antes /auditorias). El grid filtrable "qué visitar hoy" vive en el módulo
// "Hoy", no acá (ver ARQUITECTURA de la consolidación de navegación).
export default function SucursalesModule() {
  const [params, setParams] = useSearchParams();
  const tabParam = params.get('tab');
  const activeTab: SucursalesTabKey = isSucursalesTabKey(tabParam) ? tabParam : 'analitica';

  const { isMounted, markVisited } = useMountedTabs(activeTab);

  const setTab = (tab: SucursalesTabKey) => {
    markVisited(tab);
    setParams({ tab }, { replace: true });
  };

  return (
    <AppLayout title="Sucursales">
      <div className="mb-6 inline-flex flex-wrap rounded-lg border border-gray-200 bg-white p-1 shadow-sm">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setTab(tab.key)}
            className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
              activeTab === tab.key ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div style={{ display: activeTab === 'analitica' ? 'block' : 'none' }}>
        {isMounted('analitica') && <DashboardPanel />}
      </div>
      <div style={{ display: activeTab === 'fichas' ? 'block' : 'none' }}>
        {isMounted('fichas') && <AuditFichesGalleryPanel />}
      </div>
    </AppLayout>
  );
}

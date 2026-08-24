import { useSearchParams } from 'react-router-dom';
import { useMountedTabs } from '../hooks/useMountedTabs';
import { AppLayout } from '../components/AppLayout';
import {
  MarcasTab,
  SistemaTab,
  SucursalesTab,
  UsuariosPanelTab,
  UsuariosWhatsappTab,
} from '../components/admin';
import type { AdminTabKey } from '../types';

const TABS: { key: AdminTabKey; label: string }[] = [
  { key: 'sucursales', label: 'Sucursales' },
  { key: 'whatsapp', label: 'Usuarios WhatsApp' },
  { key: 'usuarios', label: 'Usuarios del panel' },
  { key: 'marcas', label: 'Marcas (campañas)' },
  { key: 'sistema', label: 'Sistema' },
];

function isAdminTabKey(value: string | null): value is AdminTabKey {
  return TABS.some((tab) => tab.key === value);
}

export default function Admin() {
  const [params, setParams] = useSearchParams();
  const tabParam = params.get('tab');
  const activeTab: AdminTabKey = isAdminTabKey(tabParam) ? tabParam : 'sucursales';

  const { isMounted, markVisited } = useMountedTabs(activeTab);

  const setTab = (tab: AdminTabKey) => {
    markVisited(tab);
    setParams({ tab }, { replace: true });
  };

  return (
    <AppLayout title="Gestión">
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

      <div style={{ display: activeTab === 'sucursales' ? 'block' : 'none' }}>
        {isMounted('sucursales') && <SucursalesTab />}
      </div>
      <div style={{ display: activeTab === 'whatsapp' ? 'block' : 'none' }}>
        {isMounted('whatsapp') && <UsuariosWhatsappTab />}
      </div>
      <div style={{ display: activeTab === 'usuarios' ? 'block' : 'none' }}>
        {isMounted('usuarios') && <UsuariosPanelTab />}
      </div>
      <div style={{ display: activeTab === 'marcas' ? 'block' : 'none' }}>
        {isMounted('marcas') && <MarcasTab />}
      </div>
      <div style={{ display: activeTab === 'sistema' ? 'block' : 'none' }}>
        {isMounted('sistema') && <SistemaTab />}
      </div>
    </AppLayout>
  );
}

import { useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AppLayout } from '../components/AppLayout';
import { MarcasTab, SucursalesTab, UsuariosPanelTab, UsuariosWhatsappTab } from '../components/admin';
import type { AdminTabKey } from '../types';

const TABS: { key: AdminTabKey; label: string }[] = [
  { key: 'sucursales', label: 'Sucursales' },
  { key: 'whatsapp', label: 'Usuarios WhatsApp' },
  { key: 'usuarios', label: 'Usuarios del panel' },
  { key: 'marcas', label: 'Marcas (campañas)' },
];

function isAdminTabKey(value: string | null): value is AdminTabKey {
  return TABS.some((tab) => tab.key === value);
}

export default function Admin() {
  const [params, setParams] = useSearchParams();
  const tabParam = params.get('tab');
  const activeTab: AdminTabKey = isAdminTabKey(tabParam) ? tabParam : 'sucursales';

  const mounted = useRef<Record<AdminTabKey, boolean>>({
    sucursales: false,
    whatsapp: false,
    usuarios: false,
    marcas: false,
  });
  mounted.current[activeTab] = true;

  const setTab = (tab: AdminTabKey) => setParams({ tab }, { replace: true });

  return (
    <AppLayout title="Administración">
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
        {mounted.current.sucursales && <SucursalesTab />}
      </div>
      <div style={{ display: activeTab === 'whatsapp' ? 'block' : 'none' }}>
        {mounted.current.whatsapp && <UsuariosWhatsappTab />}
      </div>
      <div style={{ display: activeTab === 'usuarios' ? 'block' : 'none' }}>
        {mounted.current.usuarios && <UsuariosPanelTab />}
      </div>
      <div style={{ display: activeTab === 'marcas' ? 'block' : 'none' }}>
        {mounted.current.marcas && <MarcasTab />}
      </div>
    </AppLayout>
  );
}

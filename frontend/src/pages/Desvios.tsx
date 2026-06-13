import { useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AppLayout } from '../components/AppLayout';
import { RevisionDesviosPanel } from './RevisionDesvios';
import { DesviosGestionPanel } from './DesviosGestion';

type Tab = 'revision' | 'gestion';

export default function Desvios() {
  const [params, setParams] = useSearchParams();
  const activeTab: Tab = params.get('v') === 'gestion' ? 'gestion' : 'revision';

  const revisionMounted = useRef(false);
  const gestionMounted = useRef(false);
  if (activeTab === 'revision') revisionMounted.current = true;
  if (activeTab === 'gestion') gestionMounted.current = true;

  const setTab = (tab: Tab) => setParams({ v: tab }, { replace: true });

  return (
    <AppLayout title="Desvios" contentClassName="max-w-none px-0 py-0">
      <div className="border-b border-slate-200 bg-white px-5 lg:px-8">
        <div className="flex gap-0">
          <button
            type="button"
            onClick={() => setTab('revision')}
            className={`border-b-2 px-5 py-4 text-sm font-semibold transition ${
              activeTab === 'revision'
                ? 'border-primary-navy text-primary-navy'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            Por revisar
          </button>
          <button
            type="button"
            onClick={() => setTab('gestion')}
            className={`border-b-2 px-5 py-4 text-sm font-semibold transition ${
              activeTab === 'gestion'
                ? 'border-primary-navy text-primary-navy'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            En seguimiento
          </button>
        </div>
      </div>

      <div style={{ display: activeTab === 'revision' ? 'block' : 'none' }}>
        {revisionMounted.current && <RevisionDesviosPanel embedded />}
      </div>
      <div style={{ display: activeTab === 'gestion' ? 'block' : 'none' }}>
        {gestionMounted.current && <DesviosGestionPanel embedded />}
      </div>
    </AppLayout>
  );
}

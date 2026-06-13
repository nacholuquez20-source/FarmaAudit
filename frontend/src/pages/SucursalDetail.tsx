import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ClipboardCheck } from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { useControlStock } from '../hooks/useControlStock';
import { useGestion } from '../hooks/useGestion';
import { useReportes } from '../hooks/useReportes';
import { getSucursal } from '../lib/api';
import { supabase } from '../lib/supabase';
import { formatDate, gestionStateLabel, severidadColor } from '../lib/utils';
import type { Sucursal, SucursalDetailTab } from '../types';

interface AuditFiche {
  id: string;
  created_at: string;
  sucursal_id: string;
  auditor_nombre: string;
  score_limpieza: number | null;
  score_stock: number | null;
  score_ofertas: number | null;
  score_burbujas: number | null;
  total_desvios: number;
}

function scoreColor(score: number | null) {
  if (score === null) return 'text-slate-400';
  if (score >= 4) return 'text-green-600 font-semibold';
  if (score >= 3) return 'text-yellow-600 font-semibold';
  return 'text-red-600 font-semibold';
}

export default function SucursalDetail() {
  const { id } = useParams<{ id: string }>();
  const [sucursal, setSucursal] = useState<Sucursal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<SucursalDetailTab>('reportes');
  const [fichas, setFichas] = useState<AuditFiche[]>([]);
  const [fichasLoading, setFichasLoading] = useState(false);
  const navigate = useNavigate();

  const { reportes } = useReportes(id ? { sucursal_id: id } : undefined);
  const { gestiones } = useGestion(id ? { sucursal_id: id } : undefined);
  const { items: stockItems } = useControlStock(id);

  React.useEffect(() => {
    const loadSucursal = async () => {
      try {
        setLoading(true);
        if (id) {
          const data = await getSucursal(id);
          setSucursal(data);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load sucursal');
      } finally {
        setLoading(false);
      }
    };

    loadSucursal();
  }, [id]);

  React.useEffect(() => {
    if (activeTab !== 'auditorias' || !id) return;
    setFichasLoading(true);
    supabase
      .from('audit_fiches')
      .select('*')
      .eq('sucursal_id', id)
      .order('created_at', { ascending: false })
      .then(({ data, error: err }) => {
        if (!err && data) setFichas(data as AuditFiche[]);
        setFichasLoading(false);
      });
  }, [activeTab, id]);

  if (loading) {
    return (
      <AppLayout title="Sucursal">
        <FeedbackState title="Cargando sucursal..." tone="loading" />
      </AppLayout>
    );
  }

  if (!sucursal) {
    return (
      <AppLayout title="Sucursal">
        <FeedbackState title="Sucursal no encontrada" />
      </AppLayout>
    );
  }

  const tabs: { key: SucursalDetailTab; label: string }[] = [
    { key: 'reportes', label: `Hallazgos (${reportes.length})` },
    { key: 'gestiones', label: `Gestiones (${gestiones.length})` },
    { key: 'stock', label: `Stock (${stockItems.length})` },
    { key: 'auditorias', label: 'Auditorías' },
  ];

  return (
    <AppLayout title={sucursal.nombre}>
      <div className="mb-6 flex justify-between items-center">
        <button
          onClick={() => navigate('/sucursales')}
          className="text-blue-600 hover:text-blue-800 font-medium"
        >
          Volver a Sucursales
        </button>
        <button
          onClick={() => navigate(`/sucursales/${sucursal.id}/auditoria`)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-navy text-white rounded-lg hover:bg-primary-navy/90 font-medium"
        >
          <ClipboardCheck className="h-4 w-4" />
          Auditar Perfumería
        </button>
      </div>

      {error && <div className="mb-4"><FeedbackState title={error} tone="error" /></div>}

      <div className="grid grid-cols-2 gap-4 mb-8">
        <div className="bg-white rounded-lg p-6 shadow">
          <div className="text-sm text-gray-600">Direccion</div>
          <div className="font-medium">{sucursal.direccion}</div>
        </div>
        <div className="bg-white rounded-lg p-6 shadow">
          <div className="text-sm text-gray-600">Zona</div>
          <div className="font-medium">{sucursal.zona}</div>
        </div>
        <div className="bg-white rounded-lg p-6 shadow">
          <div className="text-sm text-gray-600">Responsable</div>
          <div className="font-medium">{sucursal.responsable}</div>
        </div>
        <div className="bg-white rounded-lg p-6 shadow">
          <div className="text-sm text-gray-600">Telefono</div>
          <div className="font-medium">{sucursal.tel_responsable}</div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow">
        <div className="border-b border-gray-200">
          <div className="flex gap-0">
            {tabs.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`px-6 py-4 font-medium border-b-2 transition ${
                  activeTab === key
                    ? 'border-primary-navy text-primary-navy'
                    : 'border-transparent text-gray-600 hover:text-gray-900'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          {activeTab === 'reportes' && (
            <table className="w-full">
              <thead className="bg-gray-100 border-b">
                <tr>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Fecha</th>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Auditor</th>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Area</th>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Descripcion</th>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Severidad</th>
                </tr>
              </thead>
              <tbody>
                {reportes.map((reporte) => (
                  <tr key={reporte.id} className="border-b hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm">{formatDate(reporte.fecha)}</td>
                    <td className="px-6 py-4 text-sm">{reporte.auditor}</td>
                    <td className="px-6 py-4 text-sm">{reporte.area}</td>
                    <td className="px-6 py-4 text-sm">{reporte.descripcion}</td>
                    <td className="px-6 py-4 text-sm">
                      <span className={`px-3 py-1 rounded text-xs font-semibold ${severidadColor(reporte.severidad)}`}>
                        {reporte.severidad}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {activeTab === 'gestiones' && (
            <table className="w-full">
              <thead className="bg-gray-100 border-b">
                <tr>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Desvio</th>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Severidad</th>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Responsable</th>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Plazo</th>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Estado</th>
                </tr>
              </thead>
              <tbody>
                {gestiones.map((gestion) => (
                  <tr key={gestion.id_gestion} className="border-b hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm">{gestion.desvio}</td>
                    <td className="px-6 py-4 text-sm">
                      <span className={`px-3 py-1 rounded text-xs font-semibold ${severidadColor(gestion.severidad)}`}>
                        {gestion.severidad}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm">{gestion.responsable}</td>
                    <td className="px-6 py-4 text-sm">{formatDate(gestion.plazo_fecha)}</td>
                    <td className="px-6 py-4 text-sm">{gestionStateLabel(gestion.estado)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {activeTab === 'stock' && (
            <table className="w-full">
              <thead className="bg-gray-100 border-b">
                <tr>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Fecha</th>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Item</th>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Stock Fisico</th>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Stock Sistema</th>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Diferencia</th>
                  <th className="text-left px-6 py-3 font-semibold text-sm">Alerta</th>
                </tr>
              </thead>
              <tbody>
                {stockItems.map((item) => (
                  <tr key={item.id} className="border-b hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm">{formatDate(item.fecha)}</td>
                    <td className="px-6 py-4 text-sm">{item.nombre_item}</td>
                    <td className="px-6 py-4 text-sm font-medium">{item.stock_fisico}</td>
                    <td className="px-6 py-4 text-sm font-medium">{item.stock_sistema}</td>
                    <td className="px-6 py-4 text-sm">
                      <span className={item.diferencia !== 0 ? 'text-red-600 font-semibold' : ''}>
                        {item.diferencia}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      {item.alerta !== 'NO' && <span className="bg-red-100 text-red-800 px-2 py-1 rounded text-xs">{item.alerta}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {activeTab === 'auditorias' && (
            fichasLoading ? (
              <div className="p-8"><FeedbackState title="Cargando auditorias..." tone="loading" /></div>
            ) : fichas.length === 0 ? (
              <div className="p-8"><FeedbackState title="Sin auditorias registradas" description="Las auditorias de perfumeria realizadas por WhatsApp apareceran aqui." /></div>
            ) : (
              <table className="w-full">
                <thead className="bg-gray-100 border-b">
                  <tr>
                    <th className="text-left px-6 py-3 font-semibold text-sm">Fecha</th>
                    <th className="text-left px-6 py-3 font-semibold text-sm">Auditor</th>
                    <th className="text-left px-6 py-3 font-semibold text-sm">Limpieza</th>
                    <th className="text-left px-6 py-3 font-semibold text-sm">Stock</th>
                    <th className="text-left px-6 py-3 font-semibold text-sm">Ofertas</th>
                    <th className="text-left px-6 py-3 font-semibold text-sm">Displays</th>
                    <th className="text-left px-6 py-3 font-semibold text-sm">Desvios</th>
                  </tr>
                </thead>
                <tbody>
                  {fichas.map((ficha) => (
                    <tr key={ficha.id} className="border-b hover:bg-gray-50">
                      <td className="px-6 py-4 text-sm">{formatDate(ficha.created_at)}</td>
                      <td className="px-6 py-4 text-sm">{ficha.auditor_nombre}</td>
                      <td className={`px-6 py-4 text-sm ${scoreColor(ficha.score_limpieza)}`}>{ficha.score_limpieza ?? '—'}/5</td>
                      <td className={`px-6 py-4 text-sm ${scoreColor(ficha.score_stock)}`}>{ficha.score_stock ?? '—'}/5</td>
                      <td className={`px-6 py-4 text-sm ${scoreColor(ficha.score_ofertas)}`}>{ficha.score_ofertas ?? '—'}/5</td>
                      <td className={`px-6 py-4 text-sm ${scoreColor(ficha.score_burbujas)}`}>{ficha.score_burbujas ?? '—'}/5</td>
                      <td className="px-6 py-4 text-sm font-semibold">{ficha.total_desvios}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}
        </div>

        {((activeTab === 'reportes' && reportes.length === 0) ||
          (activeTab === 'gestiones' && gestiones.length === 0) ||
          (activeTab === 'stock' && stockItems.length === 0)) && (
          <div className="p-4">
            <FeedbackState title="No se encontraron datos" />
          </div>
        )}
      </div>
    </AppLayout>
  );
}

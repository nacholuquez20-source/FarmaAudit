import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell, ClipboardList, FileText } from 'lucide-react';
import { FeedbackState } from './FeedbackState';
import { getResumenIntegralSucursal } from '../lib/api';
import { formatDate } from '../lib/utils';
import type { ResumenIntegralSucursal } from '../types';

const BLOQUE_LABELS: Record<string, string> = {
  LIMPIEZA: 'Limpieza',
  STOCK: 'Stock',
  OFERTAS: 'Ofertas',
  BURBUJAS: 'Burbujas',
  SIN_BLOQUE: 'Sin categorizar',
};

const RESULTADO_LABELS: Record<string, string> = {
  enviado: 'Enviado',
  fallido: 'Fallido',
  sin_ventana: 'Sin ventana de WhatsApp',
  sin_encargado: 'Sin encargado',
  cooldown: 'En espera (cooldown)',
};

// Junta datos que el backend ya calculaba para el bot y el PDF del dueño,
// pero que hasta ahora no tenían ningún lugar en el panel web: campañas
// pendientes, historial de recordatorios, desglose por bloque, e informes de
// respuesta ya generados. Todo de solo lectura — ver docs del rediseño
// integral del módulo Sucursales.
export function SucursalResumenIntegral({ idSucursal }: { idSucursal: string }) {
  const [data, setData] = useState<ResumenIntegralSucursal | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    getResumenIntegralSucursal(idSucursal)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'No se pudo cargar el resumen.');
      });
    return () => {
      cancelled = true;
    };
  }, [idSucursal]);

  if (error) return <FeedbackState title={error} tone="error" />;
  if (!data) return <FeedbackState title="Cargando resumen..." tone="loading" />;

  const bloques = Object.entries(data.categorias);
  const nada =
    data.campanias_pendientes.length === 0 &&
    data.recordatorios.length === 0 &&
    data.informes_respuesta.length === 0 &&
    bloques.length === 0;

  if (nada) {
    return (
      <FeedbackState
        title="Sin novedades adicionales."
        description="No hay campañas pendientes, recordatorios ni informes de respuesta registrados para esta sucursal todavía."
        tone="info"
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {bloques.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm lg:col-span-2">
          <h3 className="mb-3 text-sm font-semibold text-gray-800">Desvíos abiertos por bloque</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-gray-500">
                  <th className="py-2 pr-3">Bloque</th>
                  <th className="px-3 py-2 text-right">Alta</th>
                  <th className="px-3 py-2 text-right">Media</th>
                  <th className="px-3 py-2 text-right">Baja</th>
                </tr>
              </thead>
              <tbody>
                {bloques.map(([bloque, sev]) => (
                  <tr key={bloque} className="border-b border-gray-100">
                    <td className="py-2 pr-3 font-medium text-gray-800">{BLOQUE_LABELS[bloque] || bloque}</td>
                    <td className="px-3 py-2 text-right text-red-700">{sev.Alta || 0}</td>
                    <td className="px-3 py-2 text-right text-amber-700">{sev.Media || 0}</td>
                    <td className="px-3 py-2 text-right text-gray-600">{sev.Baja || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-800">
          <ClipboardList className="h-4 w-4 text-gray-400" />
          Campañas pendientes ({data.campanias_pendientes.length})
        </h3>
        {data.campanias_pendientes.length === 0 ? (
          <p className="text-xs text-gray-400">Sin tareas de campaña pendientes en esta sucursal.</p>
        ) : (
          <ul className="space-y-2">
            {data.campanias_pendientes.map((t) => (
              <li key={t.id} className="rounded border border-gray-100 bg-gray-50 p-2 text-xs">
                <p className="font-medium text-gray-800">{t.campanias?.nombre || 'Campaña'}</p>
                {t.campania_acciones?.descripcion && (
                  <p className="mt-0.5 text-gray-500">{t.campania_acciones.descripcion}</p>
                )}
                <span className="mt-1 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
                  {t.estado}
                </span>
              </li>
            ))}
          </ul>
        )}
        <Link to="/mis-campanias" className="mt-3 inline-block text-xs font-medium text-blue-600 hover:text-blue-800">
          Ver campañas →
        </Link>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-800">
          <Bell className="h-4 w-4 text-gray-400" />
          Historial de recordatorios ({data.recordatorios.length})
        </h3>
        {data.recordatorios.length === 0 ? (
          <p className="text-xs text-gray-400">Todavía no se le mandó ningún recordatorio a esta sucursal.</p>
        ) : (
          <ul className="space-y-1.5">
            {data.recordatorios.map((r, i) => (
              <li key={i} className="flex items-center justify-between text-xs">
                <span className="text-gray-600">{formatDate(r.enviado_at)}</span>
                <span
                  className={`rounded px-1.5 py-0.5 font-semibold ${
                    r.resultado === 'enviado' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
                  }`}
                >
                  {RESULTADO_LABELS[r.resultado] || r.resultado}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {data.informes_respuesta.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm lg:col-span-2">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-800">
            <FileText className="h-4 w-4 text-gray-400" />
            Informes de respuesta generados ({data.informes_respuesta.length})
          </h3>
          <ul className="flex flex-wrap gap-2">
            {data.informes_respuesta.map((inf) => (
              <li key={inf.path}>
                <a
                  href={inf.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                >
                  <FileText className="h-3.5 w-3.5" />
                  {inf.created_at ? formatDate(inf.created_at) : 'Informe'}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

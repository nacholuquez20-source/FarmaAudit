import React, { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  Calendar,
  Camera,
  CheckCircle2,
  ClipboardCheck,
  ExternalLink,
  FileText,
  MessageCircle,
  SprayCan,
  Star,
} from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { useControlStock } from '../hooks/useControlStock';
import { useGestion } from '../hooks/useGestion';
import { useReportes } from '../hooks/useReportes';
import { getSucursal } from '../lib/api';
import { supabase } from '../lib/supabase';
import { diasDesde, esMesActual, formatDate, gestionStateLabel, severidadColor, whatsappLink } from '../lib/utils';
import type { EstadoSalud, Sucursal, SucursalDetailTab } from '../types';

interface AuditFiche {
  id: string;
  created_at: string;
  fecha_auditoria: string | null;
  sucursal_id: string;
  auditor_nombre: string;
  score_limpieza: number | null;
  score_stock: number | null;
  score_ofertas: number | null;
  score_burbujas: number | null;
  total_desvios: number;
  total_fotos: number;
  puntuacion_promedio: number | null;
  url_pdf: string | null;
}

const BLOQUES: { key: keyof AuditFiche; label: string }[] = [
  { key: 'score_limpieza', label: 'Limpieza' },
  { key: 'score_stock', label: 'Stock' },
  { key: 'score_ofertas', label: 'Ofertas' },
  { key: 'score_burbujas', label: 'Displays' },
];

const SALUD_META: Record<EstadoSalud, { dot: string; pill: string; label: string }> = {
  critica: { dot: 'bg-red-500', pill: 'bg-red-50 text-red-700', label: 'Crítica' },
  atencion: { dot: 'bg-amber-500', pill: 'bg-amber-50 text-amber-700', label: 'Atención' },
  ok: { dot: 'bg-green-500', pill: 'bg-green-50 text-green-700', label: 'Al día' },
  sin_datos: { dot: 'bg-gray-300', pill: 'bg-gray-100 text-gray-600', label: 'Sin datos' },
};

function scoreColor(score: number | null) {
  if (score === null) return 'text-slate-400';
  if (score >= 4) return 'text-green-600 font-semibold';
  if (score >= 3) return 'text-yellow-600 font-semibold';
  return 'text-red-600 font-semibold';
}

// Mismo criterio que la vista sucursales_dashboard (4 estados). "sin_datos"
// (nunca auditada y sin desvíos pendientes) se distingue de una crítica real.
function calcSalud(vencidos: number, dias: number | null, score: number | null, abiertos: number): EstadoSalud {
  if (vencidos > 0) return 'critica';
  if (dias !== null && dias > 30) return 'critica';
  if (score !== null && score < 3) return 'critica';
  if (abiertos > 0) return 'atencion';
  if (dias !== null && dias >= 15 && dias <= 30) return 'atencion';
  if (score !== null && score < 4) return 'atencion';
  if (dias === null) return 'sin_datos';
  return 'ok';
}

function diasLabel(dias: number | null): string {
  if (dias === null) return 'Sin auditar';
  if (dias === 0) return 'Hoy';
  if (dias === 1) return 'Hace 1 día';
  return `Hace ${dias} días`;
}

export default function SucursalDetail() {
  const { id } = useParams<{ id: string }>();
  const [sucursal, setSucursal] = useState<Sucursal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<SucursalDetailTab>('resumen');
  const [fichas, setFichas] = useState<AuditFiche[]>([]);
  const [fichasLoading, setFichasLoading] = useState(true);
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

  // Las fichas alimentan tanto el Resumen (última auditoría, evolución) como
  // la pestaña Auditorías, así que se cargan una vez al entrar.
  // Se ordena por fecha_auditoria (igual que la vista sucursales_dashboard)
  // para que la "última auditoría" del header coincida con el listado.
  React.useEffect(() => {
    if (!id) return;
    let active = true;
    setFichasLoading(true);
    supabase
      .from('audit_fiches')
      .select('*')
      .eq('sucursal_id', id)
      .order('fecha_auditoria', { ascending: false, nullsFirst: false })
      .order('created_at', { ascending: false })
      .then(({ data, error: err }) => {
        if (!active) return;
        if (!err && data) setFichas(data as AuditFiche[]);
        setFichasLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id]);

  // Métricas derivadas para el Resumen (mismo criterio que la vista SQL).
  const resumen = useMemo(() => {
    const isOpen = (estado: string) => estado !== 'Resuelta' && estado !== 'Cerrada';
    const now = new Date();
    const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const isOverdue = (g: (typeof gestiones)[number]) =>
      isOpen(g.estado) &&
      (g.estado === 'Vencida' || (!!g.plazo_fecha && g.plazo_fecha.slice(0, 10) < todayStr));

    const abiertos = gestiones.filter((g) => isOpen(g.estado)).length;
    const vencidos = gestiones.filter(isOverdue).length;
    const enRevision = gestiones.filter((g) => g.estado === 'En_revision').length;

    const ultima = fichas[0] ?? null;
    const ultimaFechaStr = ultima ? ultima.fecha_auditoria || ultima.created_at : null;
    const dias = diasDesde(ultimaFechaStr);
    const score = ultima?.puntuacion_promedio ?? null;
    const salud = calcSalud(vencidos, dias, score, abiertos);

    const auditadaEsteMes = esMesActual(ultimaFechaStr);

    // Evolución: hasta 5 fichas en orden cronológico (vieja → nueva).
    const evolucion = fichas.slice(0, 5).reverse();

    return { abiertos, vencidos, enRevision, ultima, dias, score, salud, auditadaEsteMes, evolucion };
  }, [gestiones, fichas]);

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
    { key: 'resumen', label: 'Resumen' },
    { key: 'reportes', label: `Hallazgos (${reportes.length})` },
    { key: 'gestiones', label: `Gestiones (${gestiones.length})` },
    { key: 'stock', label: `Stock (${stockItems.length})` },
    { key: 'auditorias', label: 'Auditorías' },
  ];

  const salud = SALUD_META[resumen.salud];
  const wa = whatsappLink(sucursal.tel_responsable);

  return (
    <AppLayout title={sucursal.nombre}>
      <div className="mb-4">
        <button
          onClick={() => navigate('/sucursales')}
          className="text-sm font-medium text-blue-600 hover:text-blue-800"
        >
          ← Volver a Sucursales
        </button>
      </div>

      {error && <div className="mb-4"><FeedbackState title={error} tone="error" /></div>}

      {/* Header de salud */}
      <div className="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className={`h-3 w-3 rounded-full ${salud.dot}`} />
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${salud.pill}`}>
                {salud.label}
              </span>
              <span className="text-sm text-gray-500">{sucursal.zona || 'Sin zona'}</span>
              {sucursal.tiene_perfumeria && (
                <span className="inline-flex items-center gap-1 rounded-full bg-primary-orange/10 px-2 py-0.5 text-xs font-medium text-primary-orange">
                  <SprayCan className="h-3 w-3" />
                  Perfumería
                </span>
              )}
            </div>
            <p className="mt-2 text-sm text-gray-600">
              👤 {sucursal.responsable || 'Sin encargado'}
              {sucursal.direccion && <span className="text-gray-400"> · {sucursal.direccion}</span>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {wa && (
              <a
                href={wa}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-green-200 px-3 py-2 text-sm font-medium text-green-700 transition hover:bg-green-50"
              >
                <MessageCircle className="h-4 w-4" />
                WhatsApp
              </a>
            )}
            <button
              onClick={() => navigate(`/sucursales/${sucursal.id}/auditoria`)}
              className="inline-flex items-center gap-2 rounded-lg bg-primary-navy px-4 py-2 text-sm font-medium text-white transition hover:bg-primary-navy/90"
            >
              <ClipboardCheck className="h-4 w-4" />
              Iniciar auditoría
            </button>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow">
        <div className="border-b border-gray-200">
          <div className="flex gap-0 overflow-x-auto">
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
          {activeTab === 'resumen' && (
            <div className="space-y-6 p-6">
              {/* Métricas rápidas */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                  <p className="text-xs text-gray-500">Desvíos abiertos</p>
                  <p className={`text-2xl font-bold ${resumen.abiertos > 0 ? 'text-gray-800' : 'text-green-600'}`}>
                    {resumen.abiertos}
                  </p>
                </div>
                <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                  <p className="text-xs text-gray-500">Vencidos</p>
                  <p className={`text-2xl font-bold ${resumen.vencidos > 0 ? 'text-red-600' : 'text-green-600'}`}>
                    {resumen.vencidos}
                  </p>
                </div>
                <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                  <p className="text-xs text-gray-500">Última auditoría</p>
                  <p className="flex items-center gap-1.5 pt-1 text-sm font-semibold text-gray-700">
                    <Calendar className="h-4 w-4 text-gray-400" />
                    {diasLabel(resumen.dias)}
                  </p>
                </div>
                <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                  <p className="text-xs text-gray-500">Score</p>
                  <p className={`flex items-center gap-1.5 pt-0.5 text-xl font-bold ${scoreColor(resumen.score)}`}>
                    <Star className="h-4 w-4" />
                    {resumen.score != null ? `${Number(resumen.score).toFixed(1)}/5` : '—'}
                  </p>
                </div>
              </div>

              {/* Acciones sugeridas */}
              <div>
                <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
                  ⚡ Acciones sugeridas
                </p>
                <div className="space-y-2">
                  {(() => {
                    const acciones: { tone: string; text: string; onClick?: () => void; href?: string }[] = [];
                    if (resumen.vencidos > 0) {
                      // La acción EJECUTA: si hay teléfono, abre WhatsApp con el
                      // reclamo ya redactado; si no, cae a la pestaña Gestiones.
                      const reclamo = whatsappLink(
                        sucursal.tel_responsable,
                        `Hola${sucursal.responsable ? ' ' + sucursal.responsable : ''}, te escribo de la auditoría de ${sucursal.nombre}. ` +
                          `Tenés ${resumen.vencidos} desvío${resumen.vencidos === 1 ? '' : 's'} vencido${resumen.vencidos === 1 ? '' : 's'} sin resolver. ` +
                          `¿Los podemos regularizar? Gracias.`,
                      );
                      acciones.push({
                        tone: 'text-red-700 bg-red-50 border-red-100',
                        text: reclamo
                          ? `${resumen.vencidos} desvío${resumen.vencidos === 1 ? '' : 's'} vencido${resumen.vencidos === 1 ? '' : 's'} — reclamar por WhatsApp`
                          : `${resumen.vencidos} desvío${resumen.vencidos === 1 ? '' : 's'} vencido${resumen.vencidos === 1 ? '' : 's'} — ver gestiones`,
                        href: reclamo || undefined,
                        onClick: reclamo ? undefined : () => setActiveTab('gestiones'),
                      });
                    }
                    if (resumen.enRevision > 0)
                      acciones.push({
                        tone: 'text-amber-700 bg-amber-50 border-amber-100',
                        text: `${resumen.enRevision} desvío${resumen.enRevision === 1 ? '' : 's'} esperando tu revisión`,
                        onClick: () => navigate('/desvios?v=revision'),
                      });
                    if (resumen.dias === null || resumen.dias > 30)
                      acciones.push({
                        tone: 'text-gray-700 bg-gray-50 border-gray-200',
                        text:
                          resumen.dias === null
                            ? 'Sin auditorías registradas — programar la primera'
                            : `Última auditoría hace ${resumen.dias} días — programar`,
                        onClick: () => navigate(`/sucursales/${sucursal.id}/auditoria`),
                      });
                    if (sucursal.tiene_perfumeria && resumen.dias !== null && !resumen.auditadaEsteMes)
                      acciones.push({
                        tone: 'text-primary-orange bg-primary-orange/5 border-primary-orange/20',
                        text: 'Perfumería sin auditar este mes',
                        onClick: () => navigate(`/sucursales/${sucursal.id}/auditoria`),
                      });

                    if (acciones.length === 0)
                      return (
                        <div className="flex items-center gap-2 rounded-lg border border-green-100 bg-green-50 px-3 py-3 text-sm text-green-700">
                          <CheckCircle2 className="h-4 w-4" />
                          Todo al día. No hay acciones pendientes en esta sucursal.
                        </div>
                      );

                    const claseAccion = (tone: string) =>
                      `flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-3 text-left text-sm font-medium transition hover:brightness-95 ${tone}`;
                    return acciones.map((a, i) =>
                      a.href ? (
                        <a
                          key={i}
                          href={a.href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={claseAccion(a.tone)}
                        >
                          <span className="flex items-center gap-2">
                            <MessageCircle className="h-4 w-4 shrink-0" />
                            {a.text}
                          </span>
                          <ArrowRight className="h-4 w-4 shrink-0 opacity-60" />
                        </a>
                      ) : (
                        <button
                          key={i}
                          type="button"
                          onClick={a.onClick}
                          className={claseAccion(a.tone)}
                        >
                          <span className="flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4 shrink-0" />
                            {a.text}
                          </span>
                          <ArrowRight className="h-4 w-4 shrink-0 opacity-60" />
                        </button>
                      ),
                    );
                  })()}
                </div>
              </div>

              {/* Evolución de scores */}
              {resumen.evolucion.length > 0 && (
                <div>
                  <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
                    📊 Evolución (últimas {resumen.evolucion.length} auditorías)
                  </p>
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                    {BLOQUES.map((bloque) => (
                      <div key={bloque.key as string} className="rounded-lg border border-gray-100 p-3">
                        <p className="mb-2 text-xs font-medium text-gray-600">{bloque.label}</p>
                        <div className="flex h-12 items-end gap-1">
                          {resumen.evolucion.map((f) => {
                            const v = f[bloque.key] as number | null;
                            const h = v != null ? Math.max(8, (v / 5) * 100) : 4;
                            const color =
                              v == null ? 'bg-gray-200' : v >= 4 ? 'bg-green-500' : v >= 3 ? 'bg-amber-400' : 'bg-red-500';
                            return (
                              <div
                                key={f.id}
                                className={`flex-1 rounded-t ${color}`}
                                style={{ height: `${h}%` }}
                                title={v != null ? `${v}/5` : 'Sin dato'}
                              />
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Acceso a la última ficha */}
              {resumen.ultima?.url_pdf && (
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => window.open(resumen.ultima!.url_pdf as string, '_blank', 'noopener')}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-100"
                  >
                    <FileText className="h-4 w-4" />
                    Última ficha PDF
                  </button>
                </div>
              )}
            </div>
          )}

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
              <div>
                <div className="flex justify-end px-4 py-2 border-b border-gray-100">
                  <button
                    type="button"
                    onClick={() => navigate(`/auditorias?sucursal_id=${id}`)}
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-primary-navy hover:text-primary-navy/80"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Ver todas en galería
                  </button>
                </div>
                <table className="w-full">
                  <thead className="bg-gray-100 border-b">
                    <tr>
                      <th className="text-left px-6 py-3 font-semibold text-sm">Fecha</th>
                      <th className="text-left px-6 py-3 font-semibold text-sm">Auditor</th>
                      <th className="text-left px-6 py-3 font-semibold text-sm">Limpieza</th>
                      <th className="text-left px-6 py-3 font-semibold text-sm">Stock</th>
                      <th className="text-left px-6 py-3 font-semibold text-sm">Ofertas</th>
                      <th className="text-left px-6 py-3 font-semibold text-sm">Displays</th>
                      <th className="text-center px-6 py-3 font-semibold text-sm">Desvios</th>
                      <th className="text-center px-6 py-3 font-semibold text-sm">Fotos</th>
                      <th className="text-center px-6 py-3 font-semibold text-sm">PDF</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fichas.map((ficha) => (
                      <tr key={ficha.id} className="border-b hover:bg-gray-50">
                        <td className="px-6 py-4 text-sm">{formatDate(ficha.fecha_auditoria || ficha.created_at)}</td>
                        <td className="px-6 py-4 text-sm">{ficha.auditor_nombre || '—'}</td>
                        <td className={`px-6 py-4 text-sm ${scoreColor(ficha.score_limpieza)}`}>{ficha.score_limpieza != null ? `${ficha.score_limpieza}/5` : '—'}</td>
                        <td className={`px-6 py-4 text-sm ${scoreColor(ficha.score_stock)}`}>{ficha.score_stock != null ? `${ficha.score_stock}/5` : '—'}</td>
                        <td className={`px-6 py-4 text-sm ${scoreColor(ficha.score_ofertas)}`}>{ficha.score_ofertas != null ? `${ficha.score_ofertas}/5` : '—'}</td>
                        <td className={`px-6 py-4 text-sm ${scoreColor(ficha.score_burbujas)}`}>{ficha.score_burbujas != null ? `${ficha.score_burbujas}/5` : '—'}</td>
                        <td className="px-6 py-4 text-sm text-center font-semibold">
                          <span className={ficha.total_desvios > 0 ? 'text-red-600' : 'text-green-600'}>
                            {ficha.total_desvios}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm text-center">
                          <span className="inline-flex items-center gap-1 text-gray-500">
                            <Camera className="h-3.5 w-3.5" />
                            {ficha.total_fotos}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-center">
                          {ficha.url_pdf ? (
                            <button
                              type="button"
                              onClick={() => window.open(ficha.url_pdf as string, '_blank', 'noopener')}
                              className="text-blue-600 hover:text-blue-800"
                              title="Ver PDF"
                            >
                              <FileText className="h-4 w-4" />
                            </button>
                          ) : (
                            <span className="text-gray-300">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
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

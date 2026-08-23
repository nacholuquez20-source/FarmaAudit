import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  ExternalLink,
  FileText,
  MessageCircle,
  SprayCan,
  Star,
} from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { AsistenteSucursal } from '../components/AsistenteSucursal';
import { Breadcrumbs } from '../components/Breadcrumbs';
import { FeedbackState } from '../components/FeedbackState';
import { ReminderButton } from '../components/ReminderButton';
import { SaludLegend } from '../components/SaludLegend';
import { SucursalResumenIntegral } from '../components/SucursalResumenIntegral';
import { useAuth } from '../hooks/useAuth';
import { useControlStock } from '../hooks/useControlStock';
import { useGestion } from '../hooks/useGestion';
import { useReportes } from '../hooks/useReportes';
import { getEstadoContactoSucursales, getFichaPdfUrl, getSucursal } from '../lib/api';
import { supabase } from '../lib/supabase';
import { SALUD_META } from '../lib/salud';
import {
  BLOQUES_FICHA,
  diasDesde,
  esMesActual,
  formatDate,
  gestionStateLabel,
  getBloqueScore,
  scoreColor,
  severidadColor,
  whatsappAuditLink,
  whatsappLink,
} from '../lib/utils';
import type { AuditFicha, EstadoContactoSucursal, EstadoSalud, Gestion, Sucursal } from '../types';

type AuditFiche = AuditFicha;

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

// El historial de esta ficha (auditorías, hallazgos, stock) crece mes a mes
// sin ningún filtro — separar "reciente" de "todo el historial" para que la
// pantalla no se vuelva una lista infinita a medida que pasan los meses.
// Nunca borra nada, solo decide qué se ve por defecto.
type Periodo = '3m' | '6m' | 'todo';

const PERIODO_MESES: Record<Periodo, number | null> = { '3m': 3, '6m': 6, todo: null };

function dentroDelPeriodo(fechaISO: string | null | undefined, periodo: Periodo): boolean {
  const meses = PERIODO_MESES[periodo];
  if (meses === null) return true;
  if (!fechaISO) return true; // sin fecha: no se puede descartar, se muestra igual
  const corte = new Date();
  corte.setMonth(corte.getMonth() - meses);
  return new Date(fechaISO) >= corte;
}

export default function SucursalDetail() {
  const { id } = useParams<{ id: string }>();
  const { role } = useAuth();
  const [sucursal, setSucursal] = useState<Sucursal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [fichas, setFichas] = useState<AuditFiche[]>([]);
  const [fichasLoading, setFichasLoading] = useState(true);
  const [showHallazgos, setShowHallazgos] = useState(false);
  const [showStock, setShowStock] = useState(false);
  const [showResumenIntegral, setShowResumenIntegral] = useState(false);
  const [periodo, setPeriodo] = useState<Periodo>('3m');
  const [showOrfanas, setShowOrfanas] = useState(false);
  // undefined = todavia no se intento cargar (ReminderButton muestra
  // "Cargando..."); null = ya se intento y no hay dato (falla la llamada o
  // esta sucursal no aparecio) — debe degradar a "Asignar encargado", nunca
  // quedarse en "Cargando..." para siempre.
  const [estadoContacto, setEstadoContacto] = useState<EstadoContactoSucursal | null | undefined>(undefined);
  const navigate = useNavigate();

  const canAudit = role === 'admin' || role === 'auditor';

  const { reportes } = useReportes(id ? { sucursal_id: id } : undefined);
  const { gestiones } = useGestion(id ? { sucursal_id: id } : undefined);
  const { items: stockItems } = useControlStock(id);

  const recargarEstadoContacto = () => {
    if (!id || !canAudit) return;
    getEstadoContactoSucursales()
      .then((rows) => setEstadoContacto(rows.find((r) => r.id_sucursal === id) ?? null))
      .catch(() => setEstadoContacto(null));
  };

  useEffect(() => {
    if (!id || !canAudit) return;
    let active = true;
    getEstadoContactoSucursales()
      .then((rows) => {
        if (active) setEstadoContacto(rows.find((r) => r.id_sucursal === id) ?? null);
      })
      .catch(() => {
        if (active) setEstadoContacto(null);
      });
    return () => {
      active = false;
    };
  }, [id, canAudit]);

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

  // Las fichas alimentan tanto el resumen (última auditoría) como la tabla
  // de auditorías, así que se cargan una vez al entrar.
  // Se ordena por fecha_auditoria (igual que la vista sucursales_dashboard)
  // para que la "última auditoría" del header coincida con el listado.
  // Al cambiar de sucursal hay que volver al spinner, si no se ven las fichas
  // de la anterior. Se ajusta durante el render (patrón de React para estado
  // derivado) y no dentro del efecto, donde un setState sincrónico dispara un
  // render en cascada.
  const [prevFichasId, setPrevFichasId] = React.useState(id);
  if (prevFichasId !== id) {
    setPrevFichasId(id);
    setFichasLoading(true);
  }

  React.useEffect(() => {
    if (!id) return;
    let active = true;
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

  // gestiones (useGestion sin filtro de estado) trae abiertas y cerradas de
  // toda la sucursal — se agrupan por ficha_id para que cada fila de la
  // tabla de auditorías sepa cuántos de sus desvíos siguen pendientes vs
  // resueltos. Las que no tienen ficha_id (desvíos previos al Bloque 2, o
  // creados fuera de una auditoría por WhatsApp) van aparte.
  const gestionesPorFicha = useMemo(() => {
    const map = new Map<string, Gestion[]>();
    for (const g of gestiones) {
      if (!g.ficha_id) continue;
      const lista = map.get(g.ficha_id);
      if (lista) lista.push(g);
      else map.set(g.ficha_id, [g]);
    }
    return map;
  }, [gestiones]);

  const gestionesSinFicha = useMemo(() => gestiones.filter((g) => !g.ficha_id), [gestiones]);

  // Vistas filtradas por período, solo para las TABLAS de historial — el
  // header de salud y "Acciones sugeridas" siguen usando el estado real y
  // completo (fichas/gestiones sin filtrar), nunca lo que decide mostrar el
  // selector de período.
  const fichasFiltradas = useMemo(
    () => fichas.filter((f) => dentroDelPeriodo(f.fecha_auditoria || f.created_at, periodo)),
    [fichas, periodo],
  );
  const gestionesSinFichaFiltradas = useMemo(
    () => gestionesSinFicha.filter((g) => dentroDelPeriodo(g.created_at, periodo)),
    [gestionesSinFicha, periodo],
  );
  const reportesFiltrados = useMemo(
    () => reportes.filter((r) => dentroDelPeriodo(r.fecha, periodo)),
    [reportes, periodo],
  );
  const stockItemsFiltrados = useMemo(
    () => stockItems.filter((s) => dentroDelPeriodo(s.fecha, periodo)),
    [stockItems, periodo],
  );

  // Métricas derivadas para el header (mismo criterio que la vista SQL).
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

    return { abiertos, vencidos, enRevision, ultima, dias, score, salud, auditadaEsteMes };
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

  const salud = SALUD_META[resumen.salud];
  const wa = whatsappLink(sucursal.tel_responsable);
  const sinAuditorias = fichas.length === 0 && gestionesSinFicha.length === 0;
  const sinResultadosEnPeriodo =
    !sinAuditorias && fichasFiltradas.length === 0 && gestionesSinFichaFiltradas.length === 0;

  return (
    <AppLayout title={sucursal.nombre}>
      <Breadcrumbs
        items={[
          { label: 'Sucursales', to: '/sucursales' },
          { label: sucursal.zona || 'Sin zona' },
          { label: sucursal.nombre },
        ]}
      />

      {error && <div className="mb-4"><FeedbackState title={error} tone="error" /></div>}

      {/* Header de salud */}
      <div className="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className={`h-3 w-3 rounded-full ${salud.dot}`} />
              <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold ${salud.pill}`}>
                <salud.icon className="h-3 w-3" />
                {salud.label}
              </span>
              <span className="text-sm text-gray-500">{sucursal.zona || 'Sin zona'}</span>
              {sucursal.tiene_perfumeria && (
                <span className="inline-flex items-center gap-1 rounded-full bg-primary-orange/10 px-2 py-0.5 text-xs font-medium text-primary-orange">
                  <SprayCan className="h-3 w-3" />
                  Perfumería
                </span>
              )}
              <SaludLegend />
            </div>
            <p className="mt-2 text-sm text-gray-600">
              👤 {sucursal.responsable || 'Sin encargado'}
              {sucursal.direccion && <span className="text-gray-400"> · {sucursal.direccion}</span>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {canAudit && resumen.abiertos > 0 ? (
              <ReminderButton
                idSucursal={sucursal.id}
                sucursalNombre={sucursal.nombre}
                cantidadDesvios={resumen.abiertos}
                estadoContacto={estadoContacto}
                onSent={recargarEstadoContacto}
              />
            ) : (
              wa && (
                <a
                  href={wa}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-green-200 px-3 py-2 text-sm font-medium text-green-700 transition hover:bg-green-50"
                >
                  <MessageCircle className="h-4 w-4" />
                  WhatsApp
                </a>
              )
            )}
            <a
              href={whatsappAuditLink()}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-lg bg-primary-navy px-4 py-2 text-sm font-medium text-white transition hover:bg-primary-navy/90"
            >
              <ClipboardCheck className="h-4 w-4" />
              Auditar por WhatsApp
            </a>
          </div>
        </div>
      </div>

      {/* Métricas rápidas */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-gray-100 bg-white p-3 shadow-sm">
          <p className="text-xs text-gray-500">Desvíos abiertos</p>
          <p className={`text-2xl font-bold ${resumen.abiertos > 0 ? 'text-gray-800' : 'text-green-600'}`}>
            {resumen.abiertos}
          </p>
        </div>
        <div className="rounded-lg border border-gray-100 bg-white p-3 shadow-sm">
          <p className="text-xs text-gray-500">Vencidos</p>
          <p className={`text-2xl font-bold ${resumen.vencidos > 0 ? 'text-red-600' : 'text-green-600'}`}>
            {resumen.vencidos}
          </p>
        </div>
        <div className="rounded-lg border border-gray-100 bg-white p-3 shadow-sm">
          <p className="text-xs text-gray-500">Última auditoría</p>
          <p className="flex items-center gap-1.5 pt-1 text-sm font-semibold text-gray-700">
            <Calendar className="h-4 w-4 text-gray-400" />
            {diasLabel(resumen.dias)}
          </p>
        </div>
        <div className="rounded-lg border border-gray-100 bg-white p-3 shadow-sm">
          <p className="text-xs text-gray-500">Score</p>
          <p className={`flex items-center gap-1.5 pt-0.5 text-xl font-bold ${scoreColor(resumen.score)}`}>
            <Star className="h-4 w-4" />
            {resumen.score != null ? `${Number(resumen.score).toFixed(1)}/5` : '—'}
          </p>
        </div>
      </div>

      {/* Acciones sugeridas */}
      <div className="mb-6">
        <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
          ⚡ Acciones sugeridas
        </p>
        <div className="space-y-2">
          {(() => {
            const acciones: { tone: string; text: string; onClick?: () => void; href?: string }[] = [];
            if (resumen.enRevision > 0)
              acciones.push({
                tone: 'text-amber-700 bg-amber-50 border-amber-100',
                text: `${resumen.enRevision} desvío${resumen.enRevision === 1 ? '' : 's'} esperando tu revisión`,
                onClick: () => navigate('/hoy?s=pendientes&v=decidir'),
              });
            if (resumen.dias === null || resumen.dias > 30)
              acciones.push({
                tone: 'text-gray-700 bg-gray-50 border-gray-200',
                text:
                  resumen.dias === null
                    ? 'Sin auditorías registradas — programar la primera'
                    : `Última auditoría hace ${resumen.dias} días — programar`,
                onClick: () => window.open(whatsappAuditLink(), '_blank', 'noopener'),
              });
            if (sucursal.tiene_perfumeria && resumen.dias !== null && !resumen.auditadaEsteMes)
              acciones.push({
                tone: 'text-primary-orange bg-primary-orange/5 border-primary-orange/20',
                text: 'Perfumería sin auditar este mes',
                onClick: () => window.open(whatsappAuditLink(), '_blank', 'noopener'),
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
            return acciones.map((a, i) => (
              <button key={i} type="button" onClick={a.onClick} className={claseAccion(a.tone)}>
                <span className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  {a.text}
                </span>
                <ArrowRight className="h-4 w-4 shrink-0 opacity-60" />
              </button>
            ));
          })()}
        </div>
        {canAudit && (
          <div className="mt-2">
            <AsistenteSucursal idSucursal={sucursal.id} />
          </div>
        )}
      </div>

      {/* Acceso a la última ficha + datos secundarios (hallazgos, stock) */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-4 text-xs">
        <div className="flex flex-wrap items-center gap-4">
          {resumen.ultima?.url_pdf && (
            <button
              type="button"
              onClick={() => void getFichaPdfUrl(resumen.ultima!).then((url) => url && window.open(url, '_blank', 'noopener'))}
              className="inline-flex items-center gap-1.5 font-medium text-gray-500 hover:text-gray-700"
            >
              <FileText className="h-3.5 w-3.5" />
              Última ficha PDF
            </button>
          )}
          <button
            type="button"
            onClick={() => setShowHallazgos((v) => !v)}
            className="font-medium text-gray-500 underline decoration-dotted hover:text-gray-700"
          >
            {showHallazgos ? 'Ocultar' : 'Ver'} hallazgos históricos ({reportesFiltrados.length})
          </button>
          <button
            type="button"
            onClick={() => setShowStock((v) => !v)}
            className="font-medium text-gray-500 underline decoration-dotted hover:text-gray-700"
          >
            {showStock ? 'Ocultar' : 'Ver'} stock ({stockItemsFiltrados.length})
          </button>
          {canAudit && (
            <button
              type="button"
              onClick={() => setShowResumenIntegral((v) => !v)}
              className="font-medium text-gray-500 underline decoration-dotted hover:text-gray-700"
            >
              {showResumenIntegral ? 'Ocultar' : 'Ver'} más de esta sucursal
            </button>
          )}
        </div>
        <label className="flex items-center gap-1.5 font-medium text-gray-500">
          Período
          <select
            value={periodo}
            onChange={(e) => setPeriodo(e.target.value as Periodo)}
            className="rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-transparent focus:ring-2 focus:ring-blue-500"
          >
            <option value="3m">Últimos 3 meses</option>
            <option value="6m">Últimos 6 meses</option>
            <option value="todo">Todo el historial</option>
          </select>
        </label>
      </div>

      {showResumenIntegral && (
        <div className="mb-6">
          <SucursalResumenIntegral idSucursal={sucursal.id} />
        </div>
      )}

      {showHallazgos && (
        <div className="mb-6 overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
          {reportesFiltrados.length === 0 ? (
            <div className="p-4">
              <FeedbackState
                title={reportes.length === 0 ? 'Sin hallazgos registrados' : 'Sin hallazgos en este período'}
                description={
                  reportes.length === 0
                    ? 'Los hallazgos que se cargan por WhatsApp fuera de una auditoría de perfumería aparecerán acá.'
                    : `Hay ${reportes.length} hallazgo(s) fuera del período seleccionado — probá "Todo el historial".`
                }
              />
            </div>
          ) : (
            <table className="w-full">
              <thead className="border-b bg-gray-100">
                <tr>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Fecha</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Auditor</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Área</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Descripción</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Severidad</th>
                </tr>
              </thead>
              <tbody>
                {reportesFiltrados.map((reporte) => (
                  <tr key={reporte.id} className="border-b hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm">{formatDate(reporte.fecha)}</td>
                    <td className="px-6 py-4 text-sm">{reporte.auditor}</td>
                    <td className="px-6 py-4 text-sm">{reporte.area}</td>
                    <td className="px-6 py-4 text-sm">{reporte.descripcion}</td>
                    <td className="px-6 py-4 text-sm">
                      <span className={`rounded px-3 py-1 text-xs font-semibold ${severidadColor(reporte.severidad)}`}>
                        {reporte.severidad}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {showStock && (
        <div className="mb-6 overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
          {stockItemsFiltrados.length === 0 ? (
            <div className="p-4">
              <FeedbackState
                title={stockItems.length === 0 ? 'Sin controles de stock registrados' : 'Sin controles de stock en este período'}
                description={
                  stockItems.length === 0
                    ? 'Los controles de stock cargados por WhatsApp aparecerán acá.'
                    : `Hay ${stockItems.length} control(es) fuera del período seleccionado — probá "Todo el historial".`
                }
              />
            </div>
          ) : (
            <table className="w-full">
              <thead className="border-b bg-gray-100">
                <tr>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Fecha</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Item</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Stock físico</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Stock sistema</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Diferencia</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Alerta</th>
                </tr>
              </thead>
              <tbody>
                {stockItemsFiltrados.map((item) => (
                  <tr key={item.id} className="border-b hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm">{formatDate(item.fecha)}</td>
                    <td className="px-6 py-4 text-sm">{item.nombre_item}</td>
                    <td className="px-6 py-4 text-sm font-medium">{item.stock_fisico}</td>
                    <td className="px-6 py-4 text-sm font-medium">{item.stock_sistema}</td>
                    <td className="px-6 py-4 text-sm">
                      <span className={item.diferencia !== 0 ? 'font-semibold text-red-600' : ''}>{item.diferencia}</span>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      {item.alerta !== 'NO' && <span className="rounded bg-red-100 px-2 py-1 text-xs text-red-800">{item.alerta}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Tabla de auditorías — vista principal: qué se detectó, qué se
          resolvió y qué sigue pendiente, auditoría por auditoría. */}
      <div className="rounded-lg bg-white shadow">
        <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-gray-800">Historial de auditorías</h2>
          <button
            type="button"
            onClick={() => navigate(`/sucursales?tab=fichas&sucursal_id=${id}`)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary-navy hover:text-primary-navy/80"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Ver todas en galería
          </button>
        </div>

        {fichasLoading ? (
          <div className="p-8"><FeedbackState title="Cargando auditorías..." tone="loading" /></div>
        ) : sinAuditorias ? (
          <div className="p-8">
            <FeedbackState
              title="Sin auditorías registradas"
              description="Las auditorías de perfumería realizadas por WhatsApp aparecerán aquí."
            />
          </div>
        ) : sinResultadosEnPeriodo ? (
          <div className="p-8">
            <FeedbackState
              title="Sin auditorías en este período"
              description='Esta sucursal tiene historial más viejo que el período seleccionado — probá "Todo el historial" arriba.'
              action={{ label: 'Ver todo el historial', onClick: () => setPeriodo('todo') }}
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b bg-gray-100">
                <tr>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Fecha</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">Auditor</th>
                  <th className="px-6 py-3 text-center text-sm font-semibold">Puntaje</th>
                  {BLOQUES_FICHA.map((bloque) => (
                    <th key={bloque.key} className="px-4 py-3 text-center text-sm font-semibold">
                      {bloque.label}
                    </th>
                  ))}
                  <th className="px-6 py-3 text-center text-sm font-semibold">Detectados</th>
                  <th className="px-6 py-3 text-center text-sm font-semibold">Resueltos</th>
                  <th className="px-6 py-3 text-center text-sm font-semibold">Pendientes</th>
                  <th className="px-6 py-3 text-center text-sm font-semibold">Revisión</th>
                  <th className="px-6 py-3 text-center text-sm font-semibold">Reclamar</th>
                  <th className="px-6 py-3 text-center text-sm font-semibold">PDF</th>
                </tr>
              </thead>
              <tbody>
                {fichasFiltradas.map((ficha) => {
                  const ligadas = gestionesPorFicha.get(ficha.id) ?? [];
                  const resueltos = ligadas.filter((g) => g.estado === 'Resuelta' || g.estado === 'Cerrada').length;
                  const enRevision = ligadas.filter((g) => g.estado === 'En_revision').length;
                  // "Pendientes" es lo que todavía espera al encargado — las que
                  // ya respondió y esperan que el auditor decida van en su propia
                  // columna, si no "resueltos" y "pendientes" no suman el total.
                  const pendientes = ligadas.length - resueltos - enRevision;
                  const sinVincular = ficha.desvios_count > ligadas.length;
                  return (
                    <tr
                      key={ficha.id}
                      onClick={() => navigate(`/sucursales/${id}/auditorias/${ficha.id}`)}
                      className="cursor-pointer border-b hover:bg-gray-50"
                    >
                      <td className="px-6 py-4 text-sm">
                        {formatDate(ficha.fecha_auditoria || ficha.created_at)}
                      </td>
                      <td className="px-6 py-4 text-sm">{ficha.auditor_nombre || '—'}</td>
                      <td className={`px-6 py-4 text-center text-sm ${scoreColor(ficha.puntuacion_promedio)}`}>
                        {ficha.puntuacion_promedio != null ? `${ficha.puntuacion_promedio.toFixed(1)}/5` : '—'}
                      </td>
                      {BLOQUES_FICHA.map((bloque) => {
                        const valor = getBloqueScore(ficha, bloque.key);
                        return (
                          <td key={bloque.key} className={`px-4 py-4 text-center text-sm ${scoreColor(valor)}`}>
                            {valor != null ? valor : '—'}
                          </td>
                        );
                      })}
                      <td className="px-6 py-4 text-center text-sm font-semibold">
                        <span className={ficha.desvios_count > 0 ? 'text-gray-800' : 'text-green-600'}>
                          {ficha.desvios_count}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-center text-sm font-semibold text-green-600">{resueltos}</td>
                      <td className="px-6 py-4 text-center text-sm">
                        {pendientes > 0 ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-bold text-red-700">
                            {pendientes}
                          </span>
                        ) : (
                          <span className="text-xs text-gray-300">—</span>
                        )}
                        {sinVincular && (
                          <span
                            title="Algunos desvíos de esta auditoría son anteriores al vínculo y no se pueden listar."
                            className="ml-1 text-xs text-gray-300"
                          >
                            *
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-center text-sm">
                        {enRevision > 0 ? (
                          <span
                            title="El encargado ya respondió — falta que lo revises"
                            className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-bold text-blue-700"
                          >
                            {enRevision}
                          </span>
                        ) : (
                          <span className="text-xs text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-center">
                        {canAudit && pendientes > 0 ? (
                          <ReminderButton
                            idSucursal={sucursal.id}
                            sucursalNombre={sucursal.nombre}
                            cantidadDesvios={pendientes}
                            estadoContacto={estadoContacto}
                            onSent={recargarEstadoContacto}
                            compact
                          />
                        ) : (
                          <span className="text-xs text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-center">
                        {ficha.url_pdf ? (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              void getFichaPdfUrl(ficha).then((url) => url && window.open(url, '_blank', 'noopener'));
                            }}
                            title="Ver PDF de esta auditoría"
                            className="inline-flex items-center gap-1 text-gray-400 hover:text-blue-600"
                          >
                            <FileText className="h-4 w-4" />
                          </button>
                        ) : (
                          <span className="text-xs text-gray-300">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}

                {gestionesSinFichaFiltradas.length > 0 && (() => {
                  const items = gestionesSinFichaFiltradas;
                  const resueltosSinFicha = items.filter(
                    (g) => g.estado === 'Resuelta' || g.estado === 'Cerrada',
                  ).length;
                  const enRevisionSinFicha = items.filter((g) => g.estado === 'En_revision').length;
                  const pendientesSinFicha = items.length - resueltosSinFicha - enRevisionSinFicha;
                  return (
                    <React.Fragment key="sin-ficha">
                      <tr
                        onClick={() => setShowOrfanas((v) => !v)}
                        className="cursor-pointer border-b bg-gray-50/60 hover:bg-gray-100"
                      >
                        <td colSpan={3 + BLOQUES_FICHA.length} className="px-6 py-4 text-sm text-gray-500">
                          <span className="inline-flex items-center gap-1.5">
                            {showOrfanas ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                            Sin auditoría vinculada
                          </span>
                        </td>
                        <td className="px-6 py-4 text-center text-sm font-semibold text-gray-800">
                          {items.length}
                        </td>
                        <td className="px-6 py-4 text-center text-sm font-semibold text-green-600">{resueltosSinFicha}</td>
                        <td className="px-6 py-4 text-center text-sm">
                          {pendientesSinFicha > 0 ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-bold text-red-700">
                              {pendientesSinFicha}
                            </span>
                          ) : (
                            <span className="text-xs text-gray-300">—</span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-center text-sm">
                          {enRevisionSinFicha > 0 ? (
                            <span
                              title="El encargado ya respondió — falta que lo revises"
                              className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-bold text-blue-700"
                            >
                              {enRevisionSinFicha}
                            </span>
                          ) : (
                            <span className="text-xs text-gray-300">—</span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-center">
                          {canAudit && pendientesSinFicha > 0 ? (
                            <ReminderButton
                              idSucursal={sucursal.id}
                              sucursalNombre={sucursal.nombre}
                              cantidadDesvios={pendientesSinFicha}
                              estadoContacto={estadoContacto}
                              onSent={recargarEstadoContacto}
                              compact
                            />
                          ) : (
                            <span className="text-xs text-gray-300">—</span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-center text-xs text-gray-300">—</td>
                      </tr>
                      {showOrfanas && (
                        <tr>
                          <td colSpan={9 + BLOQUES_FICHA.length} className="bg-gray-50/60 p-0">
                            <table className="w-full">
                              <tbody>
                                {items.map((gestion) => (
                                  <tr
                                    key={gestion.id_gestion}
                                    onClick={() => navigate(role === 'sucursal' ? `/mis-desvios/${gestion.id_gestion}` : `/desvios/${gestion.id_gestion}`)}
                                    className="cursor-pointer border-b border-gray-100 hover:bg-gray-100"
                                  >
                                    <td className="w-2/5 py-3 pl-12 pr-3 text-sm">{gestion.desvio}</td>
                                    <td className="px-3 py-3 text-sm">
                                      <span className={`rounded px-3 py-1 text-xs font-semibold ${severidadColor(gestion.severidad)}`}>
                                        {gestion.severidad}
                                      </span>
                                    </td>
                                    <td className="px-3 py-3 text-sm">{gestion.responsable}</td>
                                    <td className="px-3 py-3 text-sm">{formatDate(gestion.plazo_fecha)}</td>
                                    <td className="px-3 py-3 pr-6 text-sm">{gestionStateLabel(gestion.estado)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })()}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppLayout>
  );
}

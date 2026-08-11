import { useEffect, useMemo, useState } from 'react';
import { createDesvioEvento, getDesvioEventos, getFichaById, getGestionById, getReporte, getResponsableActivo, updateGestion } from '../lib/api';
import type { AuditFicha, CreateDesvioEventoInput, DesvioEvento, Gestion, GestionState, Reporte, ResponsableActivo } from '../types';

function getInitialEvent(gestion: Gestion): DesvioEvento {
  return {
    id: `initial-${gestion.id_gestion}`,
    id_gestion: gestion.id_gestion,
    tipo: 'creacion',
    comentario: `Desvío creado para ${gestion.sucursal}.`,
    actor_id: null,
    actor_nombre: gestion.responsable || null,
    metadata: {},
    created_at: gestion.created_at || gestion.updated_at || gestion.plazo_fecha,
  };
}

export function useDesvioDetail(id?: string) {
  const [gestion, setGestion] = useState<Gestion | null>(null);
  const [reporte, setReporte] = useState<Reporte | null>(null);
  const [ficha, setFicha] = useState<AuditFicha | null>(null);
  const [responsableActivo, setResponsableActivo] = useState<ResponsableActivo | null>(null);
  const [eventos, setEventos] = useState<DesvioEvento[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [eventsReady, setEventsReady] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const loadDetail = async () => {
      if (!id) {
        setLoading(false);
        setError('No se indico un desvio.');
        return;
      }

      try {
        setLoading(true);
        setError(null);

        const gestionData = await getGestionById(id);
        if (!gestionData) {
          if (!cancelled) {
            setGestion(null);
            setReporte(null);
            setFicha(null);
            setResponsableActivo(null);
            setEventos([]);
          }
          return;
        }

        const [reporteData, fichaData, responsableData, eventosData] = await Promise.all([
          gestionData.id_reporte ? getReporte(gestionData.id_reporte) : Promise.resolve(null),
          gestionData.ficha_id ? getFichaById(gestionData.ficha_id) : Promise.resolve(null),
          // Un fallo acá no debe tapar el resto del detalle: degrada a "sin
          // responsable activo", que ya es un estado que la UI sabe mostrar.
          getResponsableActivo(gestionData.id_gestion).catch(() => ({
            responsable: null,
            ventana_abierta: false,
            cantidad_desvios_abiertos: 0,
            proximo_disponible_at: null,
          })),
          getDesvioEventos(gestionData.id_gestion),
        ]);

        if (!cancelled) {
          setGestion(gestionData);
          setReporte(reporteData);
          setFicha(fichaData);
          setResponsableActivo(responsableData);
          setEventos(eventosData);
          setEventsReady(true);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'No se pudo cargar el desvío.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadDetail();

    return () => {
      cancelled = true;
    };
  }, [id, reloadKey]);

  const timeline = useMemo(() => {
    if (!gestion) return eventos;
    if (eventos.some((evento) => evento.tipo === 'creacion')) return eventos;
    return [getInitialEvent(gestion), ...eventos];
  }, [eventos, gestion]);

  const addEvento = async (input: CreateDesvioEventoInput) => {
    try {
      const evento = await createDesvioEvento(input);
      setEventos((current) => [...current, evento]);
      setEventsReady(true);
      return evento;
    } catch (err) {
      setEventsReady(false);
      throw err;
    }
  };

  const updateEstado = async (estado: GestionState, cerradoPor?: string) => {
    if (!gestion) {
      throw new Error('No hay desvio cargado.');
    }

    const updated = await updateGestion(gestion.id_gestion, estado, cerradoPor);
    setGestion(updated);
    return updated;
  };

  return {
    gestion,
    reporte,
    ficha,
    responsableActivo,
    eventos: timeline,
    loading,
    error,
    eventsReady,
    reload: () => setReloadKey((current) => current + 1),
    addEvento,
    updateEstado,
  };
}

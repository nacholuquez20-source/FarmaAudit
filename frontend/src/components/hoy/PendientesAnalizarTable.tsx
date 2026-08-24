import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '../Button';
import { FeedbackState } from '../FeedbackState';
import { useGestion } from '../../hooks/useGestion';
import { revisarGestion } from '../../lib/api';
import { supabase } from '../../lib/supabase';
import { formatDate } from '../../lib/utils';

// Bandeja de aprobación: correcciones que el responsable ya envió y esperan
// que el auditor decida. Reemplaza <DesviosGestionPanel bandeja="decidir">.
// "Aprobar" es un click directo (no pide motivo); "Rechazar" / "Gestión de
// terceros" sí piden motivo, así que esos casos se resuelven en el detalle
// completo de DesvioDetail.tsx en vez de duplicar ese modal acá.
export function PendientesAnalizarTable() {
  const navigate = useNavigate();
  const { gestiones, loading, error } = useGestion({ estado: 'En_revision' });
  const [aprobando, setAprobando] = useState<Set<string>>(new Set());
  const [aprobadas, setAprobadas] = useState<Set<string>>(new Set());
  const [respuestas, setRespuestas] = useState<Record<string, string>>({});

  const pendientes = useMemo(
    () => gestiones.filter((g) => !aprobadas.has(g.id_gestion)),
    [gestiones, aprobadas],
  );

  useEffect(() => {
    const ids = pendientes.map((g) => g.id_gestion);
    if (ids.length === 0) return;
    let active = true;

    supabase
      .from('desvio_eventos')
      .select('id_gestion, tipo, comentario, created_at')
      .in('id_gestion', ids)
      .in('tipo', ['respuesta', 'evidencia'])
      .order('created_at', { ascending: false })
      .then(({ data }) => {
        if (!active || !data) return;
        const map: Record<string, string> = {};
        for (const row of data as { id_gestion: string; tipo: string; comentario: string | null }[]) {
          if (map[row.id_gestion]) continue;
          map[row.id_gestion] = row.comentario?.trim() || (row.tipo === 'evidencia' ? 'Foto adjunta' : 'Respuesta enviada');
        }
        setRespuestas(map);
      });

    return () => {
      active = false;
    };
  }, [pendientes]);

  const handleAprobar = async (idGestion: string) => {
    setAprobando((prev) => new Set(prev).add(idGestion));
    try {
      await revisarGestion({ idGestion, accion: 'aprobar' });
      setAprobadas((prev) => new Set(prev).add(idGestion));
      toast.success('Corrección aprobada');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo aprobar la corrección');
    } finally {
      setAprobando((prev) => {
        const next = new Set(prev);
        next.delete(idGestion);
        return next;
      });
    }
  };

  if (loading) {
    return (
      <div className="p-5 lg:p-8">
        <FeedbackState title="Cargando correcciones..." tone="loading" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-5 lg:p-8">
        <FeedbackState title="Error al cargar" description={error} tone="error" />
      </div>
    );
  }

  if (pendientes.length === 0) {
    return (
      <div className="p-5 lg:p-8">
        <FeedbackState title="Sin correcciones pendientes de revisión" tone="success" />
      </div>
    );
  }

  return (
    <div className="p-5 lg:p-8">
      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
        <table className="w-full">
          <thead className="border-b bg-gray-100">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold">Fecha</th>
              <th className="px-6 py-3 text-left text-sm font-semibold">Sucursal</th>
              <th className="px-6 py-3 text-left text-sm font-semibold">Desvío</th>
              <th className="px-6 py-3 text-left text-sm font-semibold">Respuesta</th>
              <th className="px-6 py-3 text-right text-sm font-semibold">Aprobar</th>
            </tr>
          </thead>
          <tbody>
            {pendientes.map((g) => (
              <tr
                key={g.id_gestion}
                onClick={() => navigate(`/desvios/${g.id_gestion}`)}
                className="cursor-pointer border-b hover:bg-gray-50"
              >
                <td className="whitespace-nowrap px-6 py-4 text-sm">
                  {formatDate(g.en_revision_desde || g.created_at || g.plazo_fecha)}
                </td>
                <td className="whitespace-nowrap px-6 py-4 text-sm font-medium">{g.sucursal}</td>
                <td className="max-w-xs px-6 py-4 text-sm text-gray-700">{g.desvio}</td>
                <td className="px-6 py-4 text-sm text-gray-500">{respuestas[g.id_gestion] || 'Sin respuesta'}</td>
                <td className="px-6 py-4 text-right">
                  <Button
                    size="sm"
                    variant="success"
                    isLoading={aprobando.has(g.id_gestion)}
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleAprobar(g.id_gestion);
                    }}
                  >
                    <Check className="mr-1 inline h-4 w-4" />
                    Aprobar
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

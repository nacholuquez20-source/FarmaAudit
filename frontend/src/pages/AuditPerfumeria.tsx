import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { AuditBlocksPanel } from '../components/AuditBlocksPanel';
import { EvidenceCapture } from '../components/EvidenceCapture';
import { Button } from '../components/Button';
import { getSucursal } from '../lib/api';
import type { Sucursal, AuditBloqueId, AuditBloque, AuditSession } from '../types';

const INITIAL_BLOQUES: AuditBloque[] = [
  {
    id: 'LIMPIEZA',
    nombre: 'Limpieza',
    puntuacion: null,
    desvios: [],
  },
  {
    id: 'STOCK',
    nombre: 'Stock',
    puntuacion: null,
    desvios: [],
  },
  {
    id: 'OFERTAS',
    nombre: 'Ofertas',
    puntuacion: null,
    desvios: [],
  },
  {
    id: 'BURBUJAS',
    nombre: 'Burbujas',
    puntuacion: null,
    desvios: [],
  },
];

export default function AuditPerfumeria() {
  const { id: sucursalId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [sucursal, setSucursal] = useState<Sucursal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeBloque, setActiveBloque] = useState<AuditBloqueId | null>('LIMPIEZA');
  const [bloques, setBloques] = useState<AuditBloque[]>(INITIAL_BLOQUES);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const loadSucursal = async () => {
      try {
        setLoading(true);
        if (sucursalId) {
          const data = await getSucursal(sucursalId);
          setSucursal(data);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error al cargar sucursal');
      } finally {
        setLoading(false);
      }
    };

    loadSucursal();
  }, [sucursalId]);

  const handleScoreChange = (bloqueId: AuditBloqueId, score: number) => {
    setBloques((prev) =>
      prev.map((bloque) =>
        bloque.id === bloqueId
          ? { ...bloque, puntuacion: score, timestamp_inicio: new Date().toISOString() }
          : bloque
      )
    );
  };

  const handleAddEvidence = (evidence: any) => {
    if (!activeBloque) return;

    setBloques((prev) =>
      prev.map((bloque) => {
        if (bloque.id === activeBloque) {
          const desvioId = `desvio_${bloque.id}_${bloque.desvios.length + 1}`;
          const desvio = bloque.desvios.find((d) => !d.descripcion);

          if (desvio) {
            return {
              ...bloque,
              desvios: bloque.desvios.map((d) =>
                d === desvio ? { ...d, evidencias: [...d.evidencias, evidence] } : d
              ),
            };
          } else {
            return {
              ...bloque,
              desvios: [
                ...bloque.desvios,
                {
                  id: desvioId,
                  evidencias: [evidence],
                  descripcion: '',
                  timestamp: new Date().toISOString(),
                },
              ],
            };
          }
        }
        return bloque;
      })
    );
  };

  const handleSubmit = async () => {
    if (!sucursal) return;

    try {
      setSubmitting(true);
      const auditData: AuditSession = {
        id: `audit_${Date.now()}`,
        id_sucursal: sucursal.id,
        sucursal: sucursal.nombre,
        auditor_id: 'current_user_id',
        auditor_nombre: 'Current User',
        bloques,
        estado: 'enviada',
        timestamp_inicio: new Date().toISOString(),
      };

      // TODO: Send to backend
      console.log('Submitting audit:', auditData);

      navigate('/sucursales');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al enviar auditoría');
    } finally {
      setSubmitting(false);
    }
  };

  const allScored = bloques.every((b) => b.puntuacion !== null);

  if (loading) {
    return (
      <AppLayout title="Auditoria">
        <FeedbackState title="Cargando sucursal..." />
      </AppLayout>
    );
  }

  if (!sucursal) {
    return (
      <AppLayout title="Auditoria">
        <FeedbackState title="Sucursal no encontrada" />
      </AppLayout>
    );
  }

  return (
    <AppLayout title={`Auditoría - ${sucursal.nombre}`}>
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <button
            onClick={() => navigate(`/sucursales/${sucursal.id}`)}
            className="text-blue-600 hover:text-blue-800 font-medium"
          >
            ← Volver a {sucursal.nombre}
          </button>
        </div>

        {error && (
          <div className="mb-4">
            <FeedbackState title={error} tone="error" />
          </div>
        )}

        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Auditoría Perfumería</h1>
          <p className="text-gray-600">{sucursal.nombre} - {sucursal.zona}</p>
          <p className="text-sm text-gray-500 mt-2">
            Tour libre: puntuá cada área, agrega fotos y audios de los desvíos que encuentres
          </p>
        </div>

        <AuditBlocksPanel
          bloques={bloques}
          activeBloque={activeBloque}
          onSelectBloque={setActiveBloque}
          onScoreChange={handleScoreChange}
        />

        {activeBloque && (
          (() => {
            const activeBlock = bloques.find((b) => b.id === activeBloque);
            return activeBlock && activeBlock.puntuacion !== null ? (
              <div className="mt-8 bg-white rounded-lg shadow p-6">
                <h3 className="font-semibold text-gray-900 mb-4">Capturar Evidencia</h3>
                <EvidenceCapture onAddEvidence={handleAddEvidence} />
                {activeBlock.desvios.length > 0 && (
                  <div className="mt-6 space-y-3">
                    <h4 className="font-medium text-gray-800">Desvíos Detectados</h4>
                    {activeBlock.desvios.map((desvio) => (
                      <div key={desvio.id} className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                        <div className="text-sm font-medium text-gray-700">
                          {desvio.evidencias.length} evidencia{desvio.evidencias.length !== 1 ? 's' : ''}
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          {desvio.evidencias.map((e) => e.tipo).join(', ')}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : null;
          })()
        )}

        <div className="mt-8 flex gap-3 justify-end">
          <Button
            variant="outline"
            onClick={() => navigate(`/sucursales/${sucursal.id}`)}
          >
            Cancelar
          </Button>
          <Button
            variant="primary"
            disabled={!allScored || submitting}
            isLoading={submitting}
            onClick={handleSubmit}
          >
            Enviar Auditoría
          </Button>
        </div>
      </div>
    </AppLayout>
  );
}

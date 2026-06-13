import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { AuditBlocksPanel } from '../components/AuditBlocksPanel';
import { EvidenceCaptureGuided } from '../components/EvidenceCaptureGuided';
import { ProgressIndicator } from '../components/ProgressIndicator';
import { AuditSummary } from '../components/AuditSummary';
import { DesvioCreationDialog } from '../components/DesvioCreationDialog';
import { Button } from '../components/Button';
import { getSucursal, submitPerfumeriaAudit } from '../lib/api';
import { supabase } from '../lib/supabase';
import type { Sucursal, AuditBloqueId, AuditBloque, AuditEvidencia } from '../types';

const INITIAL_BLOQUES: AuditBloque[] = [
  { id: 'LIMPIEZA', nombre: 'Limpieza', puntuacion: null, desvios: [] },
  { id: 'STOCK', nombre: 'Stock', puntuacion: null, desvios: [] },
  { id: 'OFERTAS', nombre: 'Ofertas', puntuacion: null, desvios: [] },
  { id: 'BURBUJAS', nombre: 'Burbujas', puntuacion: null, desvios: [] },
];

type FormStep = 'scoring' | 'evidence' | 'summary';

export default function AuditPerfumeriaV2() {
  const { id: sucursalId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [sucursal, setSucursal] = useState<Sucursal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [formStep, setFormStep] = useState<FormStep>('scoring');
  const [activeBloque, setActiveBloque] = useState<AuditBloqueId | null>('LIMPIEZA');
  const [bloques, setBloques] = useState<AuditBloque[]>(INITIAL_BLOQUES);
  const [submitting, setSubmitting] = useState(false);
  const [showDesvioDialog, setShowDesvioDialog] = useState(false);
  const [currentDesvioId, setCurrentDesvioId] = useState<string | null>(null);

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

  const handleAddEvidence = (evidence: AuditEvidencia) => {
    if (!activeBloque) return;

    let desvioBeingDescribed: string | null = null;

    setBloques((prev) =>
      prev.map((bloque) => {
        if (bloque.id === activeBloque) {
          const desvio = bloque.desvios.find((d) => !d.descripcion);

          if (desvio) {
            desvioBeingDescribed = desvio.id;
            return {
              ...bloque,
              desvios: bloque.desvios.map((d) =>
                d === desvio ? { ...d, evidencias: [...d.evidencias, evidence] } : d
              ),
            };
          } else {
            const desvioId = `desvio_${bloque.id}_${bloque.desvios.length + 1}`;
            desvioBeingDescribed = desvioId;
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

    if (desvioBeingDescribed) {
      setCurrentDesvioId(desvioBeingDescribed);
      setShowDesvioDialog(true);
    }
  };

  const handleSaveDesvioDescription = (descripcion: string) => {
    setBloques((prev) =>
      prev.map((bloque) =>
        bloque.id === activeBloque
          ? {
              ...bloque,
              desvios: bloque.desvios.map((d) =>
                d.id === currentDesvioId ? { ...d, descripcion } : d
              ),
            }
          : bloque
      )
    );
    setShowDesvioDialog(false);
    setCurrentDesvioId(null);
  };

  const handleSubmit = async () => {
    if (!sucursal) return;

    try {
      setSubmitting(true);

      const { data } = await supabase.auth.getSession();
      const user = data.session?.user;
      const userMetadata = user?.user_metadata || {};
      const auditorNombre = userMetadata.nombre || user?.email || 'Auditor';
      const auditorPhone = user?.phone || '';

      const bloques_scores = bloques.map((bloque) => ({
        id: bloque.id,
        nombre: bloque.nombre,
        puntuacion: bloque.puntuacion || 0,
      }));

      const desvios = bloques.flatMap((bloque) =>
        bloque.desvios
          .filter((desvio) => desvio.descripcion)
          .map((desvio) => ({
            id: desvio.id,
            bloque: bloque.id,
            descripcion: desvio.descripcion,
            foto_url: desvio.evidencias.find((e) => e.tipo === 'foto')?.url || null,
          }))
      );

      const payload = {
        id_sesion: `audit_${Date.now()}`,
        sucursal_id: sucursal.id,
        sucursal_nombre: sucursal.nombre,
        auditor_nombre: auditorNombre,
        auditor_telefono: auditorPhone,
        bloques_scores,
        desvios,
      };

      await submitPerfumeriaAudit(payload);
      navigate('/sucursales');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al enviar auditoría');
    } finally {
      setSubmitting(false);
    }
  };

  const allScored = bloques.every((b) => b.puntuacion !== null);
  const totalDesvios = bloques.reduce((sum, b) => sum + b.desvios.length, 0);
  const completedDesvios = bloques.reduce(
    (sum, b) => sum + b.desvios.filter(d => d.descripcion).length,
    0
  );

  const progressSteps = [
    { id: 'scoring', label: 'Puntuar todas las áreas (1-5)', completed: allScored },
    { id: 'evidence', label: 'Capturar evidencia de desvíos', completed: totalDesvios === completedDesvios },
    { id: 'summary', label: 'Revisar y enviar', completed: false },
  ];

  if (loading) {
    return (
      <AppLayout title="Auditoria">
        <FeedbackState title="Cargando sucursal..." tone="loading" />
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
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <button
            onClick={() => navigate(`/sucursales/${sucursal.id}`)}
            className="text-blue-600 hover:text-blue-800 font-medium text-sm"
          >
            ← Volver a {sucursal.nombre}
          </button>
        </div>

        {error && (
          <div className="mb-6">
            <FeedbackState title={error} tone="error" />
          </div>
        )}

        {/* Title */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h1 className="text-3xl font-bold text-gray-900 mb-1">Auditoría Perfumería</h1>
          <p className="text-gray-600 text-sm">{sucursal.nombre} • {sucursal.zona}</p>
          <p className="text-gray-500 text-xs mt-3">
            Tour libre: puntuá cada área (1-5), agrega fotos de los desvíos
          </p>
        </div>

        {/* Progress */}
        <ProgressIndicator
          steps={progressSteps}
          currentStepId={formStep}
        />

        {formStep === 'scoring' && (
          <>
            <AuditBlocksPanel
              bloques={bloques}
              activeBloque={activeBloque}
              onSelectBloque={setActiveBloque}
              onScoreChange={handleScoreChange}
            />

            <div className="mt-8 flex gap-3 justify-end">
              <Button
                variant="outline"
                onClick={() => navigate(`/sucursales/${sucursal.id}`)}
              >
                Cancelar
              </Button>
              <Button
                variant="primary"
                disabled={!allScored}
                onClick={() => setFormStep('evidence')}
              >
                Continuar con evidencia
              </Button>
            </div>
          </>
        )}

        {formStep === 'evidence' && (
          <>
            <div className="bg-white rounded-lg shadow p-6 mb-6">
              <h2 className="text-xl font-bold text-gray-900 mb-2">Capturar Evidencia</h2>
              <p className="text-gray-600 text-sm">
                Selecciona el área donde detectaste problemas y agrega fotos
              </p>
            </div>

            <AuditBlocksPanel
              bloques={bloques}
              activeBloque={activeBloque}
              onSelectBloque={setActiveBloque}
              onScoreChange={handleScoreChange}
            />

            {activeBloque && (
              <div className="mt-8 bg-white rounded-lg shadow p-6">
                <h3 className="font-semibold text-gray-900 mb-4">
                  {bloques.find(b => b.id === activeBloque)?.nombre}
                </h3>
                <EvidenceCaptureGuided
                  onAddEvidence={handleAddEvidence}
                  blocked={!bloques.find(b => b.id === activeBloque)?.puntuacion}
                />

                {(bloques.find(b => b.id === activeBloque)?.desvios.length ?? 0) > 0 && (
                  <div className="mt-6 border-t pt-6">
                    <h4 className="font-medium text-gray-900 mb-3">Desvíos en esta área</h4>
                    <div className="space-y-2">
                      {bloques.find(b => b.id === activeBloque)?.desvios.map((desvio) => (
                        <div
                          key={desvio.id}
                          className={`p-3 rounded-lg border text-sm ${
                            desvio.descripcion
                              ? 'bg-green-50 border-green-200'
                              : 'bg-yellow-50 border-yellow-200'
                          }`}
                        >
                          <div className="font-medium text-gray-900">
                            {desvio.evidencias.length} evidencia{desvio.evidencias.length !== 1 ? 's' : ''}
                          </div>
                          {desvio.descripcion && (
                            <p className="text-gray-700 mt-1 text-xs">{desvio.descripcion}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="mt-8 flex gap-3 justify-end">
              <Button
                variant="outline"
                onClick={() => setFormStep('scoring')}
              >
                Atrás
              </Button>
              <Button
                variant="primary"
                onClick={() => setFormStep('summary')}
              >
                Revisar y enviar
              </Button>
            </div>
          </>
        )}

        {formStep === 'summary' && (
          <>
            <AuditSummary bloques={bloques} />

            <div className="mt-8 flex gap-3 justify-end">
              <Button
                variant="outline"
                onClick={() => setFormStep('evidence')}
              >
                Atrás
              </Button>
              <Button
                variant="primary"
                disabled={submitting}
                isLoading={submitting}
                onClick={handleSubmit}
              >
                Enviar Auditoría
              </Button>
            </div>
          </>
        )}
      </div>

      {activeBloque && currentDesvioId && (
        <DesvioCreationDialog
          isOpen={showDesvioDialog}
          onClose={() => {
            setShowDesvioDialog(false);
            setCurrentDesvioId(null);
          }}
          onSave={handleSaveDesvioDescription}
          evidencias={
            bloques
              .find((b) => b.id === activeBloque)
              ?.desvios.find((d) => d.id === currentDesvioId)?.evidencias || []
          }
        />
      )}
    </AppLayout>
  );
}

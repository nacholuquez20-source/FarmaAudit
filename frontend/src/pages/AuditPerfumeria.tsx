import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { AuditBlocksPanel } from '../components/AuditBlocksPanel';
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
          ? { ...bloque, puntuacion: score }
          : bloque
      )
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

import { CheckCircle2, Circle, AlertCircle } from 'lucide-react';
import { ScoreSelector } from './ScoreSelector';
import type { AuditBloqueId, AuditBloque } from '../types';

interface AuditBlocksPanelProps {
  bloques: AuditBloque[];
  activeBloque: AuditBloqueId | null;
  onSelectBloque: (bloqueId: AuditBloqueId) => void;
  onScoreChange: (bloqueId: AuditBloqueId, score: number) => void;
}

const BLOQUES_CONFIG: Record<AuditBloqueId, { nombre: string; descripcion: string }> = {
  LIMPIEZA: {
    nombre: 'Limpieza & Organización',
    descripcion: 'Estado de las góndolas, orden general, polvo, desorden',
  },
  STOCK: {
    nombre: 'Stock & Inventario',
    descripcion: 'Niveles de inventario, productos vencidos, reposición',
  },
  OFERTAS: {
    nombre: 'Ofertas & Promociones',
    descripcion: 'Precios correctos, promociones vigentes, carteles actualizados',
  },
  BURBUJAS: {
    nombre: 'Displays & Señalización',
    descripcion: 'Displays atractivos, señalización clara, marca visual',
  },
};

export function AuditBlocksPanel({
  bloques,
  activeBloque,
  onSelectBloque,
  onScoreChange,
}: AuditBlocksPanelProps) {
  const getBlockStatus = (bloque: AuditBloque) => {
    if (bloque.puntuacion === null) return 'pending';
    if (bloque.puntuacion <= 3) return 'desvio';
    return 'ok';
  };

  const getBlockIcon = (status: string) => {
    switch (status) {
      case 'ok':
        return <CheckCircle2 className="w-5 h-5 text-green-500" />;
      case 'desvio':
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      default:
        return <Circle className="w-5 h-5 text-gray-300" />;
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Bloques List */}
      <div className="space-y-3">
        <h3 className="font-semibold text-gray-900 mb-4">Áreas de Auditoria</h3>
        {bloques.map((bloque) => {
          const config = BLOQUES_CONFIG[bloque.id];
          const status = getBlockStatus(bloque);
          const isActive = activeBloque === bloque.id;

          return (
            <button
              key={bloque.id}
              onClick={() => onSelectBloque(bloque.id)}
              className={`w-full text-left p-4 rounded-lg border-2 transition ${
                isActive
                  ? 'border-blue-600 bg-blue-50'
                  : 'border-gray-200 bg-white hover:border-gray-300'
              }`}
            >
              <div className="flex gap-3 items-start">
                {getBlockIcon(status)}
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-gray-900">{config.nombre}</div>
                  <div className="text-xs text-gray-500 mt-1">{config.descripcion}</div>
                  {bloque.puntuacion !== null && (
                    <div className="mt-2">
                      <span
                        className={`inline-block text-sm font-semibold px-2 py-1 rounded ${
                          bloque.puntuacion >= 4
                            ? 'bg-green-100 text-green-700'
                            : bloque.puntuacion >= 3
                              ? 'bg-yellow-100 text-yellow-700'
                              : 'bg-red-100 text-red-700'
                        }`}
                      >
                        {bloque.puntuacion}/5
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Active Bloque Details */}
      {activeBloque && (
        <div className="lg:col-span-2">
          {(() => {
            const activeBlock = bloques.find((b) => b.id === activeBloque);
            if (!activeBlock) return null;
            const config = BLOQUES_CONFIG[activeBloque];

            return (
              <div className="bg-white rounded-lg border border-gray-200 p-6">
                <h2 className="text-2xl font-bold text-gray-900 mb-2">{config.nombre}</h2>
                <p className="text-gray-600 mb-6">{config.descripcion}</p>

                <div className="bg-gray-50 rounded-lg p-6 mb-6">
                  <h3 className="font-semibold text-gray-900 mb-4">Puntuación</h3>
                  <ScoreSelector
                    value={activeBlock.puntuacion}
                    onChange={(score) => onScoreChange(activeBloque, score)}
                  />
                </div>

                {activeBlock.puntuacion && activeBlock.puntuacion <= 3 && (
                  <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                    <p className="text-sm text-red-800">
                      ⚠️ Se detectarán desvíos en base a tu puntuación. Podrás agregar evidencia fotográfica,
                      audio y texto.
                    </p>
                  </div>
                )}
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}

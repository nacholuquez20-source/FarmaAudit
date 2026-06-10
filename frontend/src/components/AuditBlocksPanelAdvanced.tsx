import { CheckCircle2, Circle, AlertCircle } from 'lucide-react';
import { ScoreSelector } from './ScoreSelector';
import type { AuditBloqueId, AuditBloque } from '../types';

interface BrandScore {
  id: string;
  nombre: string;
  puntuacion: number | null;
}

interface AuditBloqueAdvanced extends AuditBloque {
  subItems?: BrandScore[];
}

interface AuditBlocksPanelAdvancedProps {
  bloques: AuditBloqueAdvanced[];
  activeBloque: AuditBloqueId | null;
  onSelectBloque: (bloqueId: AuditBloqueId) => void;
  onScoreChange: (bloqueId: AuditBloqueId, score: number) => void;
  onBrandScoreChange?: (bloqueId: AuditBloqueId, brandId: string, score: number) => void;
}

const BLOQUES_CONFIG: Record<AuditBloqueId, { nombre: string; descripcion: string; brands?: { id: string; nombre: string }[] }> = {
  LIMPIEZA: {
    nombre: 'Limpieza & Organización',
    descripcion: 'Estado de las góndolas, orden general, polvo, desorden',
  },
  STOCK: {
    nombre: 'Stock & Inventario',
    descripcion: 'Niveles de inventario, productos vencidos, reposición',
  },
  OFERTAS: {
    nombre: 'Ofertas & Exhibición de Marcas',
    descripcion: 'Precios correctos, promociones vigentes, exhibición por marca',
    brands: [
      { id: 'unilever', nombre: 'Unilever' },
      { id: 'colgate', nombre: 'Colgate-Palmolive' },
      { id: 'haleon', nombre: 'Haleon' },
      { id: 'genomma', nombre: 'Genomma Lab' },
    ],
  },
  BURBUJAS: {
    nombre: 'Displays & Señalización',
    descripcion: 'Displays atractivos, señalización clara, marca visual',
  },
};

export function AuditBlocksPanelAdvanced({
  bloques,
  activeBloque,
  onSelectBloque,
  onScoreChange,
  onBrandScoreChange,
}: AuditBlocksPanelAdvancedProps) {
  const getBlockStatus = (bloque: AuditBloqueAdvanced) => {
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
          const hasBrands = config.brands && bloque.subItems;

          return (
            <div key={bloque.id}>
              <button
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
                          className={`inline-flex items-center gap-1 text-sm font-semibold px-2 py-1 rounded ${
                            bloque.puntuacion >= 4
                              ? 'bg-green-100 text-green-700'
                              : bloque.puntuacion >= 3
                                ? 'bg-yellow-100 text-yellow-700'
                                : 'bg-red-100 text-red-700'
                          }`}
                        >
                          <CheckCircle2 className="w-4 h-4" />
                          {bloque.puntuacion}/5
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </button>

              {/* Brands Sub-items for OFERTAS */}
              {isActive && hasBrands && bloque.subItems && (
                <div className="mt-2 ml-2 space-y-2 pl-4 border-l-2 border-blue-300">
                  {bloque.subItems.map((brand) => (
                    <div
                      key={brand.id}
                      className="bg-blue-50 rounded-lg p-3 border border-blue-200"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium text-gray-900">{brand.nombre}</span>
                        {brand.puntuacion !== null ? (
                          <span className="text-xs font-semibold text-blue-600">
                            ✓ {brand.puntuacion}/5
                          </span>
                        ) : (
                          <span className="text-xs text-gray-500">Sin puntuar</span>
                        )}
                      </div>
                      <div className="flex gap-1">
                        {[1, 2, 3, 4, 5].map((score) => (
                          <button
                            key={score}
                            onClick={() => onBrandScoreChange?.(bloque.id, brand.id, score)}
                            className={`flex-1 py-1.5 text-xs font-medium rounded transition ${
                              brand.puntuacion === score
                                ? 'bg-blue-600 text-white'
                                : 'bg-white border border-gray-300 text-gray-700 hover:border-blue-400'
                            }`}
                          >
                            {score}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
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
            const hasBrands = config.brands && activeBlock.subItems;

            return (
              <div className="bg-white rounded-lg border border-gray-200 p-6">
                <h2 className="text-2xl font-bold text-gray-900 mb-2">{config.nombre}</h2>
                <p className="text-gray-600 mb-6">{config.descripcion}</p>

                {/* Main Score */}
                <div className="bg-gray-50 rounded-lg p-6 mb-6">
                  <h3 className="font-semibold text-gray-900 mb-4">Puntuación General</h3>
                  <ScoreSelector
                    value={activeBlock.puntuacion}
                    onChange={(score) => onScoreChange(activeBloque, score)}
                  />
                </div>

                {/* Brands Detailed View */}
                {hasBrands && activeBlock.subItems && (
                  <div className="bg-blue-50 rounded-lg p-6 border border-blue-200">
                    <h3 className="font-semibold text-gray-900 mb-4">
                      Evaluación por Marca
                    </h3>
                    <p className="text-sm text-gray-600 mb-4">
                      Puntúa cómo está exhibida cada marca en la sucursal
                    </p>
                    <div className="space-y-4">
                      {activeBlock.subItems.map((brand) => (
                        <div key={brand.id} className="bg-white rounded-lg p-4">
                          <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2">
                              {brand.puntuacion ? (
                                <CheckCircle2 className="w-5 h-5 text-green-500" />
                              ) : (
                                <Circle className="w-5 h-5 text-gray-300" />
                              )}
                              <span className="font-medium text-gray-900">
                                {brand.nombre}
                              </span>
                            </div>
                            {brand.puntuacion && (
                              <span className="text-sm font-bold text-blue-600">
                                {brand.puntuacion}/5
                              </span>
                            )}
                          </div>
                          <div className="flex gap-2">
                            {[1, 2, 3, 4, 5].map((score) => (
                              <button
                                key={score}
                                onClick={() => onBrandScoreChange?.(activeBloque, brand.id, score)}
                                className={`flex-1 py-2 text-sm font-medium rounded transition ${
                                  brand.puntuacion === score
                                    ? 'bg-blue-600 text-white shadow-lg'
                                    : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                                }`}
                              >
                                {score}
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Warning */}
                {activeBlock.puntuacion && activeBlock.puntuacion <= 3 && (
                  <div className="bg-red-50 border border-red-200 rounded-lg p-4 mt-6">
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

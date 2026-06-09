import { AlertCircle, CheckCircle2, Camera, Mic, Type } from 'lucide-react';
import type { AuditBloque } from '../types';

interface AuditSummaryProps {
  bloques: AuditBloque[];
  showingValidation?: boolean;
}

export function AuditSummary({ bloques, showingValidation = false }: AuditSummaryProps) {
  const totalDesvios = bloques.reduce((sum, b) => sum + b.desvios.length, 0);
  const completedDesvios = bloques.reduce(
    (sum, b) => sum + b.desvios.filter(d => d.descripcion).length,
    0
  );
  const incompleteDesvios = bloques.reduce(
    (sum, b) => sum + b.desvios.filter(d => !d.descripcion).length,
    0
  );

  const getEvidenceIcon = (tipo: string) => {
    switch (tipo) {
      case 'foto':
        return <Camera className="w-4 h-4" />;
      case 'audio':
        return <Mic className="w-4 h-4" />;
      case 'texto_manual':
        return <Type className="w-4 h-4" />;
      default:
        return null;
    }
  };

  return (
    <div className={`rounded-lg p-6 mb-6 ${showingValidation ? 'bg-yellow-50 border border-yellow-200' : 'bg-gray-50 border border-gray-200'}`}>
      <div className="flex items-start gap-3 mb-6">
        {showingValidation ? (
          <AlertCircle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-1" />
        ) : (
          <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0 mt-1" />
        )}
        <div>
          <h3 className="font-semibold text-gray-900">Resumen de Auditoría</h3>
          {showingValidation && (
            <p className="text-sm text-yellow-700 mt-1">
              Hay {incompleteDesvios} desvío{incompleteDesvios !== 1 ? 's' : ''} sin descripción que se ignorarán
            </p>
          )}
        </div>
      </div>

      {/* Score Summary */}
      <div className="bg-white rounded-lg p-4 mb-4">
        <h4 className="font-medium text-gray-900 mb-3 text-sm">Puntuaciones</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {bloques.map((bloque) => (
            <div key={bloque.id} className="text-center">
              <div className="text-2xl font-bold text-gray-900">
                {bloque.puntuacion || '—'}
              </div>
              <div className="text-xs text-gray-600 mt-1">{bloque.nombre}</div>
              {bloque.desvios.length > 0 && (
                <div className="text-xs font-medium text-red-600 mt-1">
                  {bloque.desvios.length} desvío{bloque.desvios.length !== 1 ? 's' : ''}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Deviations Summary */}
      {totalDesvios > 0 && (
        <div className="bg-white rounded-lg p-4">
          <h4 className="font-medium text-gray-900 mb-3 text-sm">
            Desvíos Encontrados ({completedDesvios}/{totalDesvios})
          </h4>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {bloques.map((bloque) =>
              bloque.desvios.map((desvio) => (
                <div
                  key={desvio.id}
                  className={`p-3 rounded border text-sm ${
                    desvio.descripcion
                      ? 'bg-green-50 border-green-200'
                      : 'bg-red-50 border-red-200'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1">
                      <div className="font-medium text-gray-900">
                        {bloque.nombre}
                      </div>
                      {desvio.descripcion ? (
                        <p className="text-gray-700 mt-1">{desvio.descripcion}</p>
                      ) : (
                        <p className="text-red-700 mt-1">⚠️ Sin descripción (se ignorará)</p>
                      )}
                    </div>
                  </div>

                  {desvio.evidencias.length > 0 && (
                    <div className="flex gap-1 mt-2">
                      {desvio.evidencias.map((ev) => (
                        <div
                          key={ev.id}
                          className="flex items-center gap-1 bg-white px-2 py-1 rounded text-xs text-gray-600"
                        >
                          {getEvidenceIcon(ev.tipo)}
                          <span>
                            {ev.tipo === 'foto'
                              ? 'Foto'
                              : ev.tipo === 'audio'
                                ? `Audio (${ev.duracion})`
                                : 'Texto'}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {totalDesvios === 0 && (
        <div className="bg-white rounded-lg p-4 text-center">
          <p className="text-gray-600 text-sm">
            ✅ Sin desvíos detectados. La auditoría se registrará como exitosa.
          </p>
        </div>
      )}
    </div>
  );
}

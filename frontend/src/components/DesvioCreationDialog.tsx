import { X } from 'lucide-react';
import { useState } from 'react';
import { Button } from './Button';
import type { AuditEvidencia } from '../types';

interface DesvioCreationDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (descripcion: string) => void;
  evidencias: AuditEvidencia[];
}

const QUICK_TEMPLATES = [
  'Polvo en góndolas',
  'Desorden general',
  'Falta de reposición',
  'Precios incorrectos',
  'Displays dañados',
  'Productos vencidos',
];

export function DesvioCreationDialog({
  isOpen,
  onClose,
  onSave,
  evidencias,
}: DesvioCreationDialogProps) {
  const [description, setDescription] = useState('');

  if (!isOpen) return null;

  const handleSave = () => {
    if (description.trim()) {
      onSave(description);
      setDescription('');
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white border-b p-4 flex justify-between items-center">
          <h2 className="font-semibold text-gray-900">Describir Desvío</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <p className="text-sm text-gray-600 mb-3">
              {evidencias.length} evidencia{evidencias.length !== 1 ? 's' : ''} capturada
              {evidencias.length !== 1 ? 's' : ''}:
            </p>
            <div className="space-y-2">
              {evidencias.map((ev) => (
                <div
                  key={ev.id}
                  className="bg-gray-50 rounded px-3 py-2 text-xs text-gray-600 flex items-center gap-2"
                >
                  <span className="inline-block w-2 h-2 rounded-full bg-blue-500" />
                  {ev.tipo === 'foto' && '📸 Foto'}
                  {ev.tipo === 'audio' && `🎤 Audio (${ev.duracion})`}
                  {ev.tipo === 'texto_manual' && '📝 Texto'}
                </div>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Descripción del Desvío
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe qué observaste..."
              className="w-full h-24 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
            />
          </div>

          <div>
            <p className="text-xs font-medium text-gray-600 mb-2">Plantillas rápidas:</p>
            <div className="space-y-2">
              {QUICK_TEMPLATES.map((template) => (
                <button
                  key={template}
                  onClick={() => setDescription(template)}
                  className="w-full text-left px-3 py-2 rounded border border-gray-200 hover:bg-gray-50 text-sm text-gray-700 transition"
                >
                  {template}
                </button>
              ))}
            </div>
          </div>

          <div className="flex gap-2 pt-4">
            <Button variant="outline" onClick={onClose} className="flex-1">
              Cancelar
            </Button>
            <Button
              variant="primary"
              onClick={handleSave}
              disabled={!description.trim()}
              className="flex-1"
            >
              Crear Desvío
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

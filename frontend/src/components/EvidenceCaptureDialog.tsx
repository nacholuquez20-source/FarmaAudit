import { useState } from 'react';
import { X, Mic } from 'lucide-react';
import type { AuditEvidencia } from '../types';

interface EvidenceCaptureDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onAddEvidence: (evidence: AuditEvidencia) => void;
  photoUrl?: string;
  mode: 'photo' | 'audio' | 'text';
}

export function EvidenceCaptureDialog({ isOpen, onClose, onAddEvidence, photoUrl, mode }: EvidenceCaptureDialogProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime] = useState(0);
  const [textInput, setTextInput] = useState('');

  if (!isOpen) return null;

  const handleAddAudio = () => {
    const evidence: AuditEvidencia = {
      id: `audio_${Date.now()}`,
      tipo: 'audio',
      url: 'placeholder_audio_url',
      duracion: `${recordingTime}s`,
      timestamp: new Date().toISOString(),
      asociado_a: photoUrl ? 'foto_001' : undefined,
    };
    onAddEvidence(evidence);
    onClose();
  };

  const handleAddText = () => {
    if (!textInput.trim()) return;
    const evidence: AuditEvidencia = {
      id: `texto_${Date.now()}`,
      tipo: 'texto_manual',
      contenido: textInput,
      timestamp: new Date().toISOString(),
      asociado_a: photoUrl ? 'foto_001' : undefined,
    };
    onAddEvidence(evidence);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white border-b p-4 flex justify-between items-center">
          <h2 className="font-semibold text-gray-900">
            {mode === 'photo' && '¿Algo más para esta foto?'}
            {mode === 'audio' && 'Grabar audio'}
            {mode === 'text' && 'Agregar texto'}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6">
          {photoUrl && mode === 'photo' && (
            <div className="mb-6">
              <img src={photoUrl} alt="Evidence" className="w-full h-48 object-cover rounded-lg" />
            </div>
          )}

          {mode === 'audio' && (
            <div className="space-y-4">
              <div className="flex gap-4 justify-center">
                <button
                  onClick={() => setIsRecording(!isRecording)}
                  className={`p-4 rounded-full transition ${
                    isRecording ? 'bg-red-500 hover:bg-red-600' : 'bg-blue-500 hover:bg-blue-600'
                  } text-white`}
                >
                  <Mic className="w-6 h-6" />
                </button>
              </div>
              {isRecording && (
                <div className="text-center">
                  <div className="text-3xl font-bold text-red-600">{recordingTime}s</div>
                  <p className="text-sm text-gray-600 mt-2">Grabando...</p>
                </div>
              )}
              <div className="flex gap-2 pt-4">
                <button
                  onClick={onClose}
                  className="flex-1 px-4 py-2 text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleAddAudio}
                  disabled={!recordingTime}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300"
                >
                  Guardar audio
                </button>
              </div>
            </div>
          )}

          {mode === 'text' && (
            <div className="space-y-4">
              <textarea
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                placeholder="Describe lo que observaste..."
                className="w-full h-40 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              />
              <div className="flex gap-2">
                <button
                  onClick={onClose}
                  className="flex-1 px-4 py-2 text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleAddText}
                  disabled={!textInput.trim()}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300"
                >
                  Guardar texto
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

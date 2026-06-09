import { useRef, useState } from 'react';
import { Camera, Mic, Type, X, ChevronRight, CheckCircle2, Plus } from 'lucide-react';
import { Button } from './Button';
import { useAudioRecorder } from '../hooks/useAudioRecorder';
import type { AuditEvidencia } from '../types';

interface EvidenceCaptureGuidedProps {
  onAddEvidence: (evidence: AuditEvidencia) => void;
  blocked?: boolean;
}

type CaptureStep = 'initial' | 'photo' | 'audio' | 'text';

export function EvidenceCaptureGuided({ onAddEvidence, blocked = false }: EvidenceCaptureGuidedProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<CaptureStep>('initial');
  const [selectedPhoto, setSelectedPhoto] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [textContent, setTextContent] = useState('');
  const [recordingError, setRecordingError] = useState<string | null>(null);

  const { isRecording, duration, audioBlob, startRecording, stopRecording, resetRecording } =
    useAudioRecorder();

  const handlePhotoSelect = (file: File) => {
    setSelectedPhoto(file);
    const reader = new FileReader();
    reader.onload = (e) => {
      setPreviewUrl(e.target?.result as string);
      setStep('photo');
    };
    reader.readAsDataURL(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && file.type.startsWith('image/')) {
      handlePhotoSelect(file);
    }
  };

  const handleAddPhoto = () => {
    if (!selectedPhoto || !previewUrl) return;
    const evidence: AuditEvidencia = {
      id: `foto_${Date.now()}`,
      tipo: 'foto',
      url: previewUrl,
      timestamp: new Date().toISOString(),
    };
    onAddEvidence(evidence);
    handleReset();
  };

  const handleStartAudio = async () => {
    try {
      await startRecording();
      setStep('audio');
    } catch (err) {
      setRecordingError(`Error al acceder al micrófono: ${err instanceof Error ? err.message : 'Desconocido'}`);
    }
  };

  const handleStopAudio = () => {
    stopRecording();
  };

  const handleAddAudio = async () => {
    if (!audioBlob) {
      setRecordingError('No hay audio grabado');
      return;
    }

    const audioUrl = URL.createObjectURL(audioBlob);
    const evidence: AuditEvidencia = {
      id: `audio_${Date.now()}`,
      tipo: 'audio',
      url: audioUrl,
      duracion: `${duration}s`,
      timestamp: new Date().toISOString(),
    };
    onAddEvidence(evidence);
    handleReset();
  };

  const handleAddText = () => {
    if (!textContent.trim()) return;
    const evidence: AuditEvidencia = {
      id: `texto_${Date.now()}`,
      tipo: 'texto_manual',
      contenido: textContent,
      timestamp: new Date().toISOString(),
    };
    onAddEvidence(evidence);
    handleReset();
  };

  const handleReset = () => {
    setStep('initial');
    setSelectedPhoto(null);
    setPreviewUrl(null);
    setTextContent('');
    resetRecording();
    setRecordingError(null);
  };

  if (blocked) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-center">
        <p className="text-gray-600 text-sm">
          Primero debe puntuar este bloque para agregar evidencia
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Step: Initial */}
      {step === 'initial' && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <h4 className="font-semibold text-gray-900 mb-4">Agregar Evidencia</h4>
          <p className="text-sm text-gray-600 mb-6">
            Selecciona qué tipo de evidencia deseas agregar para este desvío
          </p>

          <div className="grid grid-cols-3 gap-3">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="p-4 rounded-lg border-2 border-blue-300 bg-white hover:bg-blue-100 transition flex flex-col items-center gap-2 text-gray-700 hover:text-blue-700"
            >
              <Camera className="w-6 h-6" />
              <span className="text-sm font-medium">Foto</span>
            </button>

            <button
              onClick={handleStartAudio}
              className="p-4 rounded-lg border-2 border-blue-300 bg-white hover:bg-blue-100 transition flex flex-col items-center gap-2 text-gray-700 hover:text-blue-700"
            >
              <Mic className="w-6 h-6" />
              <span className="text-sm font-medium">Audio</span>
            </button>

            <button
              onClick={() => setStep('text')}
              className="p-4 rounded-lg border-2 border-blue-300 bg-white hover:bg-blue-100 transition flex flex-col items-center gap-2 text-gray-700 hover:text-blue-700"
            >
              <Type className="w-6 h-6" />
              <span className="text-sm font-medium">Texto</span>
            </button>
          </div>

          <button
            onClick={handleReset}
            className="w-full mt-4 py-2 text-gray-600 hover:text-gray-900 text-sm font-medium"
          >
            o completar sin agregar
          </button>
        </div>
      )}

      {/* Step: Photo */}
      {step === 'photo' && previewUrl && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
          <h4 className="font-semibold text-gray-900">Revisar Foto</h4>
          <img src={previewUrl} alt="Preview" className="w-full h-48 object-cover rounded-lg" />

          <div className="bg-blue-50 rounded-lg p-3 text-sm text-blue-700">
            ✓ Foto capturada. Puede agregar audio o texto adicional.
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setStep('initial')}
              className="flex-1 py-2 px-4 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 font-medium text-sm transition"
            >
              Cambiar foto
            </button>
            <button
              onClick={handleAddPhoto}
              className="flex-1 py-2 px-4 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium text-sm transition flex items-center justify-center gap-2"
            >
              <CheckCircle2 className="w-4 h-4" />
              Guardar foto
            </button>
          </div>
        </div>
      )}

      {/* Step: Audio */}
      {step === 'audio' && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
          <h4 className="font-semibold text-gray-900">Grabar Audio</h4>

          {isRecording ? (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-center">
              <div className="text-4xl font-bold text-red-600 mb-2">{duration}s</div>
              <p className="text-red-700 text-sm mb-4">Grabando...</p>
              <div className="flex gap-2">
                <button
                  onClick={handleStopAudio}
                  className="flex-1 py-2 px-4 bg-red-600 text-white rounded-lg hover:bg-red-700 font-medium text-sm"
                >
                  Detener
                </button>
                <button
                  onClick={() => {
                    resetRecording();
                    setStep('initial');
                  }}
                  className="flex-1 py-2 px-4 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 font-medium text-sm"
                >
                  Cancelar
                </button>
              </div>
            </div>
          ) : audioBlob ? (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 space-y-4">
              <div className="text-center">
                <p className="text-blue-900 font-medium">Audio grabado: {duration}s</p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    resetRecording();
                    setStep('initial');
                  }}
                  className="flex-1 py-2 px-4 border border-blue-300 rounded-lg text-blue-700 hover:bg-blue-100 font-medium text-sm"
                >
                  Grabar de nuevo
                </button>
                <button
                  onClick={handleAddAudio}
                  className="flex-1 py-2 px-4 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium text-sm flex items-center justify-center gap-2"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  Guardar
                </button>
              </div>
            </div>
          ) : (
            <div className="bg-blue-50 rounded-lg p-4 text-center">
              <button
                onClick={handleStartAudio}
                className="w-full py-3 px-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium flex items-center justify-center gap-2"
              >
                <Mic className="w-5 h-5" />
                Iniciar grabación
              </button>
            </div>
          )}

          {recordingError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-red-700 text-sm">
              {recordingError}
            </div>
          )}
        </div>
      )}

      {/* Step: Text */}
      {step === 'text' && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
          <h4 className="font-semibold text-gray-900">Agregar Texto</h4>
          <textarea
            value={textContent}
            onChange={(e) => setTextContent(e.target.value)}
            placeholder="Describe lo que observaste..."
            className="w-full h-32 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
          />
          <div className="flex gap-2">
            <button
              onClick={() => setStep('initial')}
              className="flex-1 py-2 px-4 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 font-medium text-sm"
            >
              Cancelar
            </button>
            <button
              onClick={handleAddText}
              disabled={!textContent.trim()}
              className="flex-1 py-2 px-4 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <CheckCircle2 className="w-4 h-4" />
              Guardar texto
            </button>
          </div>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFileChange}
      />
    </div>
  );
}

import { useRef, useState } from 'react';
import { Camera, Mic, Type, X, Plus } from 'lucide-react';
import { Button } from './Button';
import type { AuditEvidencia } from '../types';

interface EvidenceCaptureProps {
  onAddEvidence: (evidence: AuditEvidencia) => void;
  disabled?: boolean;
}

export function EvidenceCapture({ onAddEvidence, disabled = false }: EvidenceCaptureProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedPhoto, setSelectedPhoto] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [showActions, setShowActions] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [showTextInput, setShowTextInput] = useState(false);
  const [textContent, setTextContent] = useState('');

  const handlePhotoSelect = (file: File) => {
    setSelectedPhoto(file);
    const reader = new FileReader();
    reader.onload = (e) => {
      setPreviewUrl(e.target?.result as string);
      setShowActions(true);
    };
    reader.readAsDataURL(file);
  };

  const handlePhotoCapture = () => {
    fileInputRef.current?.click();
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
    setSelectedPhoto(null);
    setPreviewUrl(null);
    setShowActions(false);
    setTextContent('');
  };

  const handleAddAudio = () => {
    const evidence: AuditEvidencia = {
      id: `audio_${Date.now()}`,
      tipo: 'audio',
      url: 'placeholder_audio',
      duracion: `${recordingDuration}s`,
      timestamp: new Date().toISOString(),
    };
    onAddEvidence(evidence);
    setIsRecording(false);
    setRecordingDuration(0);
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
    setTextContent('');
    setShowTextInput(false);
  };

  const handleCancel = () => {
    setSelectedPhoto(null);
    setPreviewUrl(null);
    setShowActions(false);
    setShowTextInput(false);
    setTextContent('');
    setIsRecording(false);
    setRecordingDuration(0);
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <button
          onClick={handlePhotoCapture}
          disabled={disabled || showActions || isRecording || showTextInput}
          className="p-4 rounded-lg border-2 border-dashed border-gray-300 hover:border-blue-400 hover:bg-blue-50 disabled:opacity-50 disabled:cursor-not-allowed transition flex flex-col items-center gap-2 text-gray-600 hover:text-blue-600"
        >
          <Camera className="w-6 h-6" />
          <span className="text-sm font-medium">Foto</span>
        </button>

        <button
          onClick={() => setIsRecording(!isRecording)}
          disabled={disabled || showActions || showTextInput}
          className={`p-4 rounded-lg border-2 transition flex flex-col items-center gap-2 font-medium text-sm ${
            isRecording
              ? 'border-red-400 bg-red-50 text-red-600'
              : 'border-dashed border-gray-300 hover:border-blue-400 hover:bg-blue-50 text-gray-600 hover:text-blue-600'
          } ${(disabled || showActions || showTextInput) && !isRecording ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          <Mic className="w-6 h-6" />
          <span>{isRecording ? 'Grabando...' : 'Audio'}</span>
        </button>

        <button
          onClick={() => setShowTextInput(!showTextInput)}
          disabled={disabled || showActions || isRecording}
          className="p-4 rounded-lg border-2 border-dashed border-gray-300 hover:border-blue-400 hover:bg-blue-50 disabled:opacity-50 disabled:cursor-not-allowed transition flex flex-col items-center gap-2 text-gray-600 hover:text-blue-600"
        >
          <Type className="w-6 h-6" />
          <span className="text-sm font-medium">Texto</span>
        </button>
      </div>

      {isRecording && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
          <div className="flex-1">
            <div className="text-2xl font-bold text-red-600">{recordingDuration}s</div>
            <p className="text-sm text-red-700">Grabando audio...</p>
          </div>
          <Button variant="danger" size="sm" onClick={handleAddAudio}>
            Guardar
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setIsRecording(false);
              setRecordingDuration(0);
            }}
          >
            Cancelar
          </Button>
        </div>
      )}

      {showTextInput && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 space-y-3">
          <textarea
            value={textContent}
            onChange={(e) => setTextContent(e.target.value)}
            placeholder="Describe lo que observaste..."
            className="w-full h-32 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
          />
          <div className="flex gap-2 justify-end">
            <Button variant="outline" size="sm" onClick={handleCancel}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={!textContent.trim()}
              onClick={handleAddText}
            >
              Guardar
            </Button>
          </div>
        </div>
      )}

      {previewUrl && showActions && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-3">
          <img src={previewUrl} alt="Preview" className="w-full h-48 object-cover rounded" />
          <div className="space-y-2">
            <p className="text-sm font-medium text-gray-700">¿Quieres agregar audio o texto a esta foto?</p>
            <div className="flex gap-2 flex-wrap">
              <Button variant="outline" size="sm" onClick={() => setShowTextInput(true)}>
                <Type className="w-4 h-4 mr-1" />
                Texto
              </Button>
              <Button variant="outline" size="sm" onClick={() => setIsRecording(true)}>
                <Mic className="w-4 h-4 mr-1" />
                Audio
              </Button>
              <Button variant="primary" size="sm" onClick={handleAddPhoto}>
                <Plus className="w-4 h-4 mr-1" />
                Agregar foto
              </Button>
              <Button variant="danger" size="sm" onClick={handleCancel}>
                <X className="w-4 h-4 mr-1" />
                Cancelar
              </Button>
            </div>
          </div>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFileChange}
        disabled={disabled}
      />
    </div>
  );
}

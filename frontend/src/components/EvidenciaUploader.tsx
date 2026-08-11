import { useEffect, useMemo, useRef, useState } from 'react';
import { FeedbackState } from './FeedbackState';
import { useEvidenciaUpload } from '../hooks/useEvidenciaUpload';
import type { DesvioEvento } from '../types';

const MAX_FILE_SIZE = 10 * 1024 * 1024;
const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];

interface EvidenciaUploaderProps {
  idGestion: string;
  onUploaded?: (evento: DesvioEvento) => void;
}

function isAcceptedFile(file: File): boolean {
  return ACCEPTED_TYPES.includes(file.type);
}

export function EvidenciaUploader({ idGestion, onUploaded }: EvidenciaUploaderProps) {
  const { upload, uploading, progress, error } = useEvidenciaUpload(idGestion);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [descripcion, setDescripcion] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);

  const previewUrl = useMemo(() => {
    if (!file || !file.type.startsWith('image/')) return null;
    return URL.createObjectURL(file);
  }, [file]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const selectFile = (selected: File | null) => {
    setLocalError(null);
    if (!selected) {
      setFile(null);
      return;
    }
    if (!isAcceptedFile(selected)) {
      setFile(null);
      setLocalError('Formato no permitido. Usa JPG, PNG, WEBP o PDF.');
      return;
    }
    if (selected.size > MAX_FILE_SIZE) {
      setFile(null);
      setLocalError('El archivo supera el maximo de 10MB.');
      return;
    }
    setFile(selected);
  };

  const handleSubmit = async () => {
    if (!file) {
      setLocalError('Selecciona un archivo para subir.');
      return;
    }

    const evento = await upload(file, descripcion);
    setFile(null);
    setDescripcion('');
    onUploaded?.(evento);
  };

  return (
    <section className="rounded-lg bg-white p-6 shadow">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Subir evidencia</h2>
        <p className="text-sm text-gray-500">Fotos o PDF quedan guardados en Supabase Storage.</p>
      </div>

      {(localError || error) && (
        <div className="mb-4">
          <FeedbackState title={localError || error || ''} tone="warning" />
        </div>
      )}

      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click();
        }}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          selectFile(event.dataTransfer.files.item(0));
        }}
        className="mb-4 flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-5 text-center hover:border-blue-400 hover:bg-blue-50"
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/*,application/pdf"
          className="hidden"
          onChange={(event) => selectFile(event.target.files?.item(0) ?? null)}
        />
        {previewUrl ? (
          <img src={previewUrl} alt="Preview de evidencia" className="h-32 max-w-full rounded object-cover" />
        ) : file ? (
          <div className="text-sm font-medium text-gray-700">{file.name}</div>
        ) : (
          <>
            <div className="text-sm font-medium text-gray-700">Arrastra una imagen o PDF</div>
            <div className="mt-1 text-xs text-gray-500">JPG, PNG, WEBP o PDF - maximo 10MB</div>
          </>
        )}
      </div>

      <label className="mb-4 block text-sm font-medium text-gray-700">
        Descripcion
        <textarea
          value={descripcion}
          onChange={(event) => setDescripcion(event.target.value)}
          rows={2}
          placeholder="Describí brevemente la evidencia"
          className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
        />
      </label>

      {uploading && (
        <div className="mb-4">
          <div className="h-2 overflow-hidden rounded-full bg-gray-200">
            <div className="h-full bg-blue-600 transition-all" style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={handleSubmit}
        disabled={uploading || !file}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-300 disabled:text-gray-600"
      >
        {uploading ? 'Subiendo...' : 'Subir evidencia'}
      </button>
    </section>
  );
}

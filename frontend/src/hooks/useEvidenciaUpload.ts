import { useMemo, useState } from 'react';
import { createDesvioEvento, crearNotificacionesDesvio, uploadEvidencia } from '../lib/api';
import { useAuth } from './useAuth';
import type { DesvioEvento, DesvioOrigen, EvidenciaStorageMetadata } from '../types';

export function useEvidenciaUpload(idGestion: string) {
  const { user, profile, role } = useAuth();
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const origen: DesvioOrigen = useMemo(() => (role === 'sucursal' ? 'sucursal' : 'auditor'), [role]);

  const upload = async (file: File, descripcion: string): Promise<DesvioEvento> => {
    const comentario = descripcion.trim() || 'Evidencia subida desde la app.';
    const actorNombre = profile?.nombre || user?.email || 'Usuario';

    setUploading(true);
    setProgress(10);
    setError(null);

    try {
      const result = await uploadEvidencia(idGestion, file, origen);
      setProgress(70);

      const metadata: EvidenciaStorageMetadata = {
        foto_path: result.path,
        foto_url_signed: result.signedUrl,
        mime_type: file.type,
        size_bytes: file.size,
        origen,
      };

      const evento = await createDesvioEvento({
        id_gestion: idGestion,
        tipo: 'evidencia',
        comentario,
        actor_id: user?.id || null,
        actor_nombre: actorNombre,
        metadata: metadata as unknown as Record<string, unknown>,
      });

      await crearNotificacionesDesvio({
        idGestion,
        origen,
        tipo: 'mensaje_nuevo',
      });

      setProgress(100);
      return evento;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'No se pudo subir la evidencia.';
      setError(message);
      throw err;
    } finally {
      window.setTimeout(() => {
        setUploading(false);
        setProgress(0);
      }, 500);
    }
  };

  return { upload, uploading, progress, error, origen };
}

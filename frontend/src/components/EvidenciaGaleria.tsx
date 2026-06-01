import { useEffect, useMemo, useState } from 'react';
import { FeedbackState } from './FeedbackState';
import { ImageLightbox } from './ImageLightbox';
import { getSignedUrl } from '../lib/api';
import { formatDateTime } from '../lib/utils';
import type { DesvioEvento, DesvioOrigen } from '../types';

interface EvidenciaGaleriaProps {
  eventos: DesvioEvento[];
}

interface EvidenciaItem {
  id: string;
  comentario: string;
  created_at: string;
  actor_nombre: string | null;
  origen: DesvioOrigen;
  path: string | null;
  bucket: string | null;
  legacyUrl: string | null;
  mimeType: string | null;
}

function readString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function readOrigen(value: unknown): DesvioOrigen {
  return value === 'sucursal' ? 'sucursal' : 'auditor';
}

function isImage(mimeType: string | null, url: string): boolean {
  if (mimeType?.startsWith('image/')) return true;
  return /\.(jpe?g|png|webp)(\?|$)/i.test(url);
}

export function EvidenciaGaleria({ eventos }: EvidenciaGaleriaProps) {
  const [signedUrls, setSignedUrls] = useState<Record<string, string>>({});
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  const evidencias = useMemo<EvidenciaItem[]>(
    () => eventos
      .filter((evento) => evento.tipo === 'evidencia')
      .map((evento) => ({
        id: evento.id,
        comentario: evento.comentario,
        created_at: evento.created_at,
        actor_nombre: evento.actor_nombre,
        origen: readOrigen(evento.metadata?.origen),
        path: readString(evento.metadata?.foto_path),
        bucket: readString(evento.metadata?.bucket),
        legacyUrl: readString(evento.metadata?.evidencia_url),
        mimeType: readString(evento.metadata?.mime_type),
      }))
      .filter((item) => item.path || item.legacyUrl),
    [eventos],
  );

  useEffect(() => {
    let cancelled = false;
    const paths = evidencias.map((item) => item.path).filter((path): path is string => Boolean(path));
    const missingPaths = paths.filter((path) => !signedUrls[path]);
    if (missingPaths.length === 0) return;

    const loadUrls = async () => {
      const entries = await Promise.all(
        missingPaths.map(async (path) => {
          try {
            const bucket = evidencias.find((item) => item.path === path)?.bucket || undefined;
            return [path, await getSignedUrl(path, bucket)] as const;
          } catch {
            return [path, ''] as const;
          }
        }),
      );
      if (!cancelled) {
        setSignedUrls((current) => ({ ...current, ...Object.fromEntries(entries) }));
      }
    };

    void loadUrls();
    return () => {
      cancelled = true;
    };
  }, [evidencias, signedUrls]);

  if (evidencias.length === 0) {
    return (
      <section className="rounded-lg bg-white p-6 shadow">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">Galeria de evidencias</h2>
        <FeedbackState title="No hay evidencias subidas todavia." />
      </section>
    );
  }

  const imageEvidencias = evidencias.filter((item) => {
    const url = item.path ? signedUrls[item.path] : item.legacyUrl;
    return url && isImage(item.mimeType, url);
  });

  const handleImageClick = (index: number) => {
    setLightboxIndex(index);
  };

  const handlePrevious = () => {
    if (lightboxIndex !== null && lightboxIndex > 0) {
      setLightboxIndex(lightboxIndex - 1);
    }
  };

  const handleNext = () => {
    if (lightboxIndex !== null && lightboxIndex < imageEvidencias.length - 1) {
      setLightboxIndex(lightboxIndex + 1);
    }
  };

  return (
    <section className="rounded-lg bg-white p-6 shadow">
      <h2 className="mb-4 text-lg font-semibold text-gray-900">Galeria de evidencias</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {evidencias.map((item, index) => {
          const url = item.path ? signedUrls[item.path] : item.legacyUrl;
          const badge = item.origen === 'sucursal' ? 'Encargado' : 'Auditor';
          const isImageFile = url && isImage(item.mimeType, url);
          const imageIndex = isImageFile ? imageEvidencias.findIndex((e) => e.id === item.id) : -1;

          return (
            <article key={item.id} className="rounded-lg border border-gray-200 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <span className="rounded bg-gray-100 px-2 py-1 text-xs font-semibold text-gray-700">{badge}</span>
                <span className="text-xs text-gray-500">{formatDateTime(item.created_at)}</span>
              </div>
              {url ? (
                isImageFile ? (
                  <button
                    onClick={() => imageIndex >= 0 && handleImageClick(imageIndex)}
                    className="group block w-full cursor-pointer"
                    type="button"
                    aria-label={`Open ${item.comentario || 'image'}`}
                  >
                    <img
                      src={url}
                      alt={item.comentario || 'Evidencia'}
                      className="h-32 w-full rounded object-cover ring-1 ring-gray-200 transition group-hover:opacity-75 group-hover:ring-blue-400"
                    />
                  </button>
                ) : (
                  <a href={url} target="_blank" rel="noreferrer" className="group block">
                    <div className="flex h-32 items-center justify-center rounded bg-gray-100 text-sm font-medium text-blue-700">
                      Abrir archivo
                    </div>
                  </a>
                )
              ) : (
                <div className="flex h-32 items-center justify-center rounded bg-gray-100 text-sm text-gray-500">
                  URL no disponible
                </div>
              )}
              <p className="mt-3 text-sm text-gray-700">{item.comentario}</p>
              {item.actor_nombre && <p className="mt-1 text-xs text-gray-500">Por {item.actor_nombre}</p>}
              {item.legacyUrl && !item.path && (
                <a href={item.legacyUrl} target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm font-medium text-blue-600">
                  Abrir evidencia externa
                </a>
              )}
            </article>
          );
        })}
      </div>

      {lightboxIndex !== null && imageEvidencias[lightboxIndex] && (() => {
        const item = imageEvidencias[lightboxIndex];
        const url = item.path ? signedUrls[item.path] : item.legacyUrl;
        return url ? (
          <ImageLightbox
            src={url}
            alt={item.comentario || 'Evidencia'}
            onClose={() => setLightboxIndex(null)}
            currentIndex={lightboxIndex}
            totalImages={imageEvidencias.length}
            onPrevious={handlePrevious}
            onNext={handleNext}
          />
        ) : null;
      })()}
    </section>
  );
}

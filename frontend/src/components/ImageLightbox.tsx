import { X, ChevronLeft, ChevronRight } from 'lucide-react';
import { useEffect } from 'react';

interface ImageLightboxProps {
  src: string;
  alt: string;
  onClose: () => void;
  currentIndex?: number;
  totalImages?: number;
  onPrevious?: () => void;
  onNext?: () => void;
}

export function ImageLightbox({ src, alt, onClose, currentIndex, totalImages, onPrevious, onNext }: ImageLightboxProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft' && onPrevious) onPrevious();
      if (e.key === 'ArrowRight' && onNext) onNext();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, onPrevious, onNext]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-90">
      <div className="relative flex items-center justify-center w-full h-full p-4">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-10 rounded-full bg-white bg-opacity-20 p-2 hover:bg-opacity-30 text-white transition"
          aria-label="Close"
        >
          <X size={24} />
        </button>

        {/* Image */}
        <img
          src={src}
          alt={alt}
          className="max-h-full max-w-full rounded-lg object-contain"
        />

        {/* Navigation arrows */}
        {onPrevious && (
          <button
            onClick={onPrevious}
            className="absolute left-4 rounded-full bg-white bg-opacity-20 p-2 hover:bg-opacity-30 text-white transition"
            aria-label="Previous image"
          >
            <ChevronLeft size={24} />
          </button>
        )}

        {onNext && (
          <button
            onClick={onNext}
            className="absolute right-4 rounded-full bg-white bg-opacity-20 p-2 hover:bg-opacity-30 text-white transition"
            aria-label="Next image"
          >
            <ChevronRight size={24} />
          </button>
        )}

        {/* Image counter */}
        {currentIndex !== undefined && totalImages !== undefined && totalImages > 1 && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-black bg-opacity-50 px-4 py-2 text-sm font-medium text-white">
            {currentIndex + 1} / {totalImages}
          </div>
        )}
      </div>
    </div>
  );
}

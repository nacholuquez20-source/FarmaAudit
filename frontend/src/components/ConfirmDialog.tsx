import { useEffect, useRef } from 'react';
import { Button } from './Button';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: 'danger' | 'primary';
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirmar',
  cancelLabel = 'Cancelar',
  tone = 'primary',
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = `confirm-dialog-title-${title.replace(/\s+/g, '-').toLowerCase()}`;

  useEffect(() => {
    if (!open) return;
    // El cancelar queda con foco por default (no el destructivo): en un
    // diálogo que suele abrirse para archivar/borrar algo, un Enter
    // apurado no debería confirmar por accidente.
    cancelRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !loading) onCancel();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, loading, onCancel]);

  if (!open) return null;

  return (
    <>
      <button type="button" aria-label="Cerrar" onClick={onCancel} className="fixed inset-0 z-50 cursor-default bg-slate-950/40" />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onCancel}>
        <div
          role="alertdialog"
          aria-modal="true"
          aria-labelledby={titleId}
          onClick={(event) => event.stopPropagation()}
          className="w-full max-w-md rounded-lg bg-white p-6 shadow-2xl"
        >
          <h3 id={titleId} className="text-lg font-bold text-slate-950">{title}</h3>
          {description && <p className="mt-2 text-sm text-slate-600">{description}</p>}

          <div className="mt-5 flex justify-end gap-2">
            <Button ref={cancelRef} type="button" variant="outline" onClick={onCancel} disabled={loading}>
              {cancelLabel}
            </Button>
            <Button
              type="button"
              variant={tone === 'danger' ? 'danger' : 'primary'}
              onClick={onConfirm}
              isLoading={loading}
            >
              {confirmLabel}
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}

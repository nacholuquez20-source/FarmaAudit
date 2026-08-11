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
  if (!open) return null;

  return (
    <>
      <button type="button" aria-label="Cerrar" onClick={onCancel} className="fixed inset-0 z-50 cursor-default bg-slate-950/40" />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onCancel}>
        <div
          role="alertdialog"
          aria-modal="true"
          onClick={(event) => event.stopPropagation()}
          className="w-full max-w-md rounded-lg bg-white p-6 shadow-2xl"
        >
          <h3 className="text-lg font-bold text-slate-950">{title}</h3>
          {description && <p className="mt-2 text-sm text-slate-600">{description}</p>}

          <div className="mt-5 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onCancel} disabled={loading}>
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

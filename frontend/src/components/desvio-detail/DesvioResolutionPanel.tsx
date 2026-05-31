import type { Gestion } from '../../types';

interface DesvioResolutionPanelProps {
  gestion: Gestion;
  updatingStatus: boolean;
  resolutionComment: string;
  evidenceText: string;
  evidenceUrl: string;
  onCommentChange: (value: string) => void;
  onEvidenceTextChange: (value: string) => void;
  onEvidenceUrlChange: (value: string) => void;
  onMarkInProgress: () => void;
  onClose: () => void;
  onResolve: (event: React.FormEvent) => void;
}

export function DesvioResolutionPanel({
  gestion,
  updatingStatus,
  resolutionComment,
  evidenceText,
  evidenceUrl,
  onCommentChange,
  onEvidenceTextChange,
  onEvidenceUrlChange,
  onMarkInProgress,
  onClose,
  onResolve,
}: DesvioResolutionPanelProps) {
  return (
    <section className="rounded-lg bg-white p-6 shadow lg:col-span-3">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Resolucion y cierre</h2>
          <p className="text-sm text-gray-500">Registra respuesta, evidencia y cierre con trazabilidad.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onMarkInProgress}
            disabled={updatingStatus || gestion.estado === 'En_proceso' || gestion.estado === 'Cerrada'}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:bg-gray-100 disabled:text-gray-400"
          >
            Marcar en proceso
          </button>
          <button
            type="button"
            onClick={onClose}
            disabled={updatingStatus || gestion.estado === 'Cerrada'}
            className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:bg-gray-300 disabled:text-gray-600"
          >
            Cerrar desvio
          </button>
        </div>
      </div>

      <form onSubmit={onResolve} className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <label className="text-sm font-medium text-gray-700 lg:col-span-3">
          Comentario de resolucion
          <textarea
            value={resolutionComment}
            onChange={(event) => onCommentChange(event.target.value)}
            rows={3}
            required
            placeholder="Describe que hizo el responsable para resolver el desvio"
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
          />
        </label>

        <label className="text-sm font-medium text-gray-700 lg:col-span-2">
          Evidencia o respuesta
          <input
            type="text"
            value={evidenceText}
            onChange={(event) => onEvidenceTextChange(event.target.value)}
            placeholder="Texto breve, numero de remito, descripcion de foto, etc."
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
          />
        </label>

        <label className="text-sm font-medium text-gray-700">
          URL de evidencia
          <input
            type="url"
            value={evidenceUrl}
            onChange={(event) => onEvidenceUrlChange(event.target.value)}
            placeholder="https://..."
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal focus:border-transparent focus:ring-2 focus:ring-blue-500"
          />
        </label>

        <div className="lg:col-span-3">
          <button
            type="submit"
            disabled={updatingStatus || gestion.estado === 'Cerrada'}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-300 disabled:text-gray-600"
          >
            {updatingStatus ? 'Guardando...' : 'Marcar como resuelto'}
          </button>
        </div>
      </form>
    </section>
  );
}

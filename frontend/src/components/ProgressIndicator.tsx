import { CheckCircle2, Circle } from 'lucide-react';

interface ProgressStep {
  id: string;
  label: string;
  completed: boolean;
}

interface ProgressIndicatorProps {
  steps: ProgressStep[];
  currentStepId?: string;
}

export function ProgressIndicator({ steps, currentStepId }: ProgressIndicatorProps) {
  const completedCount = steps.filter(s => s.completed).length;
  const progressPercentage = (completedCount / steps.length) * 100;

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900">Progreso de la Auditoría</h3>
        <span className="text-sm font-medium text-gray-600">
          {completedCount}/{steps.length} completado
        </span>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-200 rounded-full h-2 mb-6 overflow-hidden">
        <div
          className="bg-blue-600 h-2 transition-all duration-300"
          style={{ width: `${progressPercentage}%` }}
        />
      </div>

      {/* Steps */}
      <div className="space-y-2">
        {steps.map((step) => (
          <div key={step.id} className="flex items-center gap-3">
            {step.completed ? (
              <CheckCircle2 className="w-5 h-5 text-green-500 flex-shrink-0" />
            ) : (
              <Circle className="w-5 h-5 text-gray-300 flex-shrink-0" />
            )}
            <span
              className={`text-sm ${
                step.id === currentStepId
                  ? 'font-semibold text-blue-600'
                  : step.completed
                    ? 'text-gray-600 line-through'
                    : 'text-gray-600'
              }`}
            >
              {step.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

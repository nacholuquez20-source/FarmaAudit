import { CheckCircle2 } from 'lucide-react';

interface CompletionCheckmarkProps {
  completed: boolean;
  label?: string;
  animated?: boolean;
}

export function CompletionCheckmark({
  completed,
  label = 'Completado',
  animated = true,
}: CompletionCheckmarkProps) {
  if (!completed) return null;

  return (
    <div
      className={`inline-flex items-center gap-2 px-3 py-1 rounded-full bg-green-100 text-green-700 text-sm font-medium ${
        animated ? 'animate-in slide-in-from-bottom-2' : ''
      }`}
    >
      <CheckCircle2 className="w-4 h-4" />
      <span>{label}</span>
    </div>
  );
}

interface CompletionListProps {
  items: Array<{
    id: string;
    label: string;
    completed: boolean;
  }>;
  title?: string;
}

export function CompletionList({ items, title }: CompletionListProps) {
  const completedCount = items.filter((i) => i.completed).length;
  const totalCount = items.length;
  const percentComplete = (completedCount / totalCount) * 100;

  return (
    <div className="space-y-3">
      {title && (
        <div className="flex items-center justify-between mb-4">
          <h4 className="font-semibold text-gray-900">{title}</h4>
          <span className="text-sm font-medium text-gray-600">
            {completedCount}/{totalCount}
          </span>
        </div>
      )}

      {/* Progress bar */}
      {totalCount > 0 && (
        <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden">
          <div
            className="bg-green-500 h-1.5 transition-all duration-500 ease-out"
            style={{ width: `${percentComplete}%` }}
          />
        </div>
      )}

      {/* Items */}
      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.id}
            className={`flex items-center gap-3 p-2 rounded-lg transition ${
              item.completed
                ? 'bg-green-50 text-green-700'
                : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            <div className="flex-shrink-0">
              {item.completed ? (
                <CheckCircle2 className="w-5 h-5 text-green-600" />
              ) : (
                <div className="w-5 h-5 rounded-full border-2 border-gray-300" />
              )}
            </div>
            <span className={`text-sm font-medium flex-1 ${item.completed ? 'line-through text-green-600' : ''}`}>
              {item.label}
            </span>
            {item.completed && (
              <span className="text-xs font-bold text-green-600">✓</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

interface StepCheckerProps {
  steps: Array<{
    id: string;
    label: string;
    status: 'pending' | 'in-progress' | 'completed';
  }>;
}

export function StepChecker({ steps }: StepCheckerProps) {
  const completedSteps = steps.filter((s) => s.status === 'completed').length;
  const currentStep = steps.find((s) => s.status === 'in-progress');

  return (
    <div className="space-y-4">
      {/* Step list */}
      <div className="space-y-2">
        {steps.map((step, index) => (
          <div key={step.id} className="flex items-center gap-3">
            {/* Connector line */}
            <div className="flex flex-col items-center">
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition ${
                  step.status === 'completed'
                    ? 'bg-green-500 text-white'
                    : step.status === 'in-progress'
                      ? 'bg-blue-500 text-white animate-pulse'
                      : 'bg-gray-300 text-white'
                }`}
              >
                {step.status === 'completed' ? '✓' : index + 1}
              </div>
              {index < steps.length - 1 && (
                <div
                  className={`w-0.5 h-8 ${
                    step.status === 'completed'
                      ? 'bg-green-500'
                      : 'bg-gray-200'
                  }`}
                />
              )}
            </div>

            {/* Label */}
            <span
              className={`text-sm font-medium ${
                step.status === 'completed'
                  ? 'text-green-600'
                  : step.status === 'in-progress'
                    ? 'text-blue-600 font-bold'
                    : 'text-gray-500'
              }`}
            >
              {step.label}
            </span>
          </div>
        ))}
      </div>

      {/* Summary */}
      {completedSteps > 0 && (
        <div className="bg-green-50 rounded-lg p-3 border border-green-200">
          <p className="text-sm text-green-700 font-medium">
            ✓ {completedSteps}/{steps.length} pasos completados
            {currentStep && ` • Actualmente: ${currentStep.label}`}
          </p>
        </div>
      )}
    </div>
  );
}

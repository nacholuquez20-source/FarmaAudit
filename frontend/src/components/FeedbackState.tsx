import { AlertCircle, AlertTriangle, CheckCircle2, Info, Loader2 } from 'lucide-react';

type Tone = 'neutral' | 'error' | 'warning' | 'info' | 'success' | 'loading';

interface FeedbackStateProps {
  title: string;
  description?: string;
  tone?: Tone;
  action?: { label: string; onClick: () => void };
}

const config: Record<Tone, { wrapper: string; iconClass: string; Icon: React.ElementType | null }> = {
  neutral: { wrapper: 'bg-white text-gray-600', iconClass: 'text-gray-400', Icon: null },
  loading: { wrapper: 'bg-white text-gray-600', iconClass: 'text-gray-400 animate-spin', Icon: Loader2 },
  error: { wrapper: 'bg-red-50 text-red-800 border border-red-200', iconClass: 'text-red-500', Icon: AlertCircle },
  warning: { wrapper: 'bg-yellow-50 text-yellow-900 border border-yellow-200', iconClass: 'text-yellow-500', Icon: AlertTriangle },
  info: { wrapper: 'bg-blue-50 text-blue-900 border border-blue-200', iconClass: 'text-blue-500', Icon: Info },
  success: { wrapper: 'bg-green-50 text-green-900 border border-green-200', iconClass: 'text-green-500', Icon: CheckCircle2 },
};

export function FeedbackState({ title, description, tone = 'neutral', action }: FeedbackStateProps) {
  const { wrapper, iconClass, Icon } = config[tone];

  return (
    <div className={`rounded-lg p-8 text-center shadow-sm ${wrapper}`}>
      {Icon && (
        <span className={`mb-3 inline-flex ${iconClass}`}>
          <Icon className="h-8 w-8" />
        </span>
      )}
      <div className="font-semibold">{title}</div>
      {description && <div className="mt-1.5 text-sm opacity-75">{description}</div>}
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="mt-4 rounded-lg border border-current px-4 py-2 text-sm font-medium opacity-80 transition hover:opacity-100"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}

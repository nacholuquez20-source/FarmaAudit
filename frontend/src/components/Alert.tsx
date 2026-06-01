import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';
import { useState } from 'react';

type AlertType = 'info' | 'success' | 'warning' | 'error';

interface AlertProps {
  type: AlertType;
  title: string;
  message?: string;
  dismissible?: boolean;
  onDismiss?: () => void;
}

const typeConfig = {
  info: {
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    icon: Info,
    iconColor: 'text-blue-600',
    titleColor: 'text-blue-900',
  },
  success: {
    bg: 'bg-green-50',
    border: 'border-green-200',
    icon: CheckCircle2,
    iconColor: 'text-green-600',
    titleColor: 'text-green-900',
  },
  warning: {
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    icon: AlertTriangle,
    iconColor: 'text-amber-600',
    titleColor: 'text-amber-900',
  },
  error: {
    bg: 'bg-red-50',
    border: 'border-red-200',
    icon: AlertCircle,
    iconColor: 'text-red-600',
    titleColor: 'text-red-900',
  },
};

export function Alert({ type, title, message, dismissible = false, onDismiss }: AlertProps) {
  const [isDismissed, setIsDismissed] = useState(false);

  const config = typeConfig[type];
  const IconComponent = config.icon;

  const handleDismiss = () => {
    setIsDismissed(true);
    onDismiss?.();
  };

  if (isDismissed) return null;

  return (
    <div className={`rounded-lg border ${config.bg} ${config.border} p-4`}>
      <div className="flex gap-3">
        <IconComponent className={`flex-shrink-0 ${config.iconColor}`} size={20} />
        <div className="flex-1">
          <h3 className={`font-semibold ${config.titleColor}`}>{title}</h3>
          {message && <p className="mt-1 text-sm text-gray-700">{message}</p>}
        </div>
        {dismissible && (
          <button
            onClick={handleDismiss}
            className="flex-shrink-0 text-gray-400 hover:text-gray-600 transition"
            aria-label="Dismiss"
          >
            <X size={18} />
          </button>
        )}
      </div>
    </div>
  );
}

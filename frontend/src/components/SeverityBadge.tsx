import { AlertTriangle, AlertCircle, AlertOctagon } from 'lucide-react';
import { getSeverityStyles } from '../lib/design-tokens';
import type { SeverityType } from '../types';

interface SeverityBadgeProps {
  severity: SeverityType;
  size?: 'sm' | 'md' | 'lg';
}

const sizeClasses = {
  sm: 'px-2 py-1 text-xs gap-1',
  md: 'px-3 py-1.5 text-sm gap-1.5',
  lg: 'px-4 py-2 text-base gap-2',
};

const iconSizes = {
  sm: 16,
  md: 18,
  lg: 20,
};

function getSeverityIcon(severity: string, size: number) {
  switch (severity.toLowerCase()) {
    case 'crítico':
      return <AlertOctagon size={size} />;
    case 'alta prioridad':
      return <AlertTriangle size={size} />;
    case 'en alerta':
      return <AlertCircle size={size} />;
    default:
      return null;
  }
}

export function SeverityBadge({ severity, size = 'md' }: SeverityBadgeProps) {
  const styles = getSeverityStyles(severity);

  return (
    <span
      className={`inline-flex items-center rounded-full font-semibold ${sizeClasses[size]}`}
      style={{
        backgroundColor: styles.bg,
        color: styles.fg,
      }}
    >
      {getSeverityIcon(severity, iconSizes[size])}
      {severity}
    </span>
  );
}

import { getStatusStyles } from '../lib/design-tokens';
import type { StatusType } from '../types';

interface StatusBadgeProps {
  status: StatusType;
  size?: 'sm' | 'md' | 'lg';
}

const sizeClasses = {
  sm: 'px-2 py-1 text-xs',
  md: 'px-3 py-1.5 text-sm',
  lg: 'px-4 py-2 text-base',
};

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const styles = getStatusStyles(status);

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold ${sizeClasses[size]}`}
      style={{
        backgroundColor: styles.bg,
        color: styles.fg,
      }}
    >
      <span
        className="h-2 w-2 rounded-full"
        style={{ backgroundColor: styles.dot }}
      />
      {status}
    </span>
  );
}

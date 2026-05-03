interface FeedbackStateProps {
  title: string;
  description?: string;
  tone?: 'neutral' | 'error' | 'warning' | 'info';
}

const toneStyles = {
  neutral: 'bg-white text-gray-600',
  error: 'bg-red-100 text-red-800',
  warning: 'bg-yellow-50 text-yellow-900 border border-yellow-200',
  info: 'bg-blue-50 text-blue-900 border border-blue-200',
};

export function FeedbackState({ title, description, tone = 'neutral' }: FeedbackStateProps) {
  return (
    <div className={`rounded-lg p-8 text-center shadow ${toneStyles[tone]}`}>
      <div className="font-medium">{title}</div>
      {description && <div className="mt-2 text-sm opacity-80">{description}</div>}
    </div>
  );
}

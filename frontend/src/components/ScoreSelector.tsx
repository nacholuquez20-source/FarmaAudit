import { Star } from 'lucide-react';

interface ScoreSelectorProps {
  value: number | null;
  onChange: (score: number) => void;
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
}

export function ScoreSelector({ value, onChange, size = 'md', disabled = false }: ScoreSelectorProps) {
  const sizeClasses = {
    sm: 'w-8 h-8',
    md: 'w-10 h-10',
    lg: 'w-12 h-12',
  };

  const scores = [1, 2, 3, 4, 5];

  const getScoreColor = (score: number) => {
    if (!value) return 'text-gray-300';
    if (score <= value) {
      if (value >= 4) return 'text-green-500';
      if (value >= 3) return 'text-yellow-500';
      return 'text-red-500';
    }
    return 'text-gray-300';
  };

  const getScoreLabel = (score: number) => {
    switch (score) {
      case 1:
        return 'Muy Mal';
      case 2:
        return 'Mal';
      case 3:
        return 'Regular';
      case 4:
        return 'Bien';
      case 5:
        return 'Excelente';
      default:
        return '';
    }
  };

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="flex gap-2">
        {scores.map((score) => (
          <button
            key={score}
            onClick={() => !disabled && onChange(score)}
            disabled={disabled}
            className={`${sizeClasses[size]} flex items-center justify-center transition-transform hover:scale-110 ${
              disabled ? 'cursor-not-allowed' : 'cursor-pointer'
            }`}
          >
            <Star className={`w-full h-full ${getScoreColor(score)} ${value && score <= value ? 'fill-current' : ''}`} />
          </button>
        ))}
      </div>
      {value && (
        <div className="text-center">
          <div className="text-2xl font-bold text-gray-800">{value}/5</div>
          <div className="text-sm text-gray-600">{getScoreLabel(value)}</div>
        </div>
      )}
    </div>
  );
}

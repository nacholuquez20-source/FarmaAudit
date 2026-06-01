import React from 'react';

type TextareaSize = 'sm' | 'md' | 'lg';

interface TextareaProps extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'size'> {
  label?: string;
  textareaSize?: TextareaSize;
  error?: string;
  helperText?: string;
  charLimit?: number;
}

const sizeClasses: Record<TextareaSize, string> = {
  sm: 'px-2.5 py-1.5 text-sm min-h-[6rem]',
  md: 'px-3 py-2 text-base min-h-[8rem]',
  lg: 'px-4 py-2.5 text-lg min-h-[10rem]',
};

export function Textarea({
  label,
  textareaSize = 'md',
  error,
  helperText,
  charLimit,
  value,
  className = '',
  disabled = false,
  ...props
}: TextareaProps) {
  const charCount = typeof value === 'string' ? value.length : 0;
  const isAtLimit = charLimit && charCount >= charLimit;

  const classes = `
    w-full rounded-lg border resize-vertical transition-colors
    ${error ? 'border-red-500 focus:border-red-600 focus:ring-red-100' : 'border-gray-300 focus:border-primary-navy focus:ring-blue-100'}
    ${sizeClasses[textareaSize]}
    disabled:bg-gray-100 disabled:text-gray-500 disabled:cursor-not-allowed disabled:border-gray-200
    focus:outline-none focus:ring-2
    ${className}
  `.trim();

  return (
    <div className="w-full">
      {label && (
        <label className="mb-2 block text-sm font-medium text-gray-900">
          {label}
        </label>
      )}
      <textarea
        value={value}
        disabled={disabled}
        className={classes}
        {...props}
      />
      <div className="mt-1 flex justify-between text-sm">
        <div>
          {error && (
            <p className="text-red-600">{error}</p>
          )}
          {helperText && !error && (
            <p className="text-gray-500">{helperText}</p>
          )}
        </div>
        {charLimit && (
          <p className={`font-medium ${isAtLimit ? 'text-red-600' : 'text-gray-500'}`}>
            {charCount}/{charLimit}
          </p>
        )}
      </div>
    </div>
  );
}

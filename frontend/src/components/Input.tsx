import React from 'react';

type InputSize = 'sm' | 'md' | 'lg';
type InputType = 'text' | 'email' | 'password' | 'number' | 'tel' | 'url' | 'search' | 'date' | 'time';

interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size' | 'type'> {
  label?: string;
  type?: InputType;
  inputSize?: InputSize;
  error?: string;
  helperText?: string;
}

const sizeClasses: Record<InputSize, string> = {
  sm: 'px-2.5 py-1.5 text-sm',
  md: 'px-3 py-2 text-base',
  lg: 'px-4 py-2.5 text-lg',
};

export function Input({
  label,
  type = 'text',
  inputSize = 'md',
  error,
  helperText,
  className = '',
  disabled = false,
  ...props
}: InputProps) {
  const classes = `
    w-full rounded-lg border transition-colors
    ${error ? 'border-red-500 focus:border-red-600 focus:ring-red-100' : 'border-gray-300 focus:border-primary-navy focus:ring-blue-100'}
    ${sizeClasses[inputSize]}
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
      <input
        type={type}
        disabled={disabled}
        className={classes}
        {...props}
      />
      {error && (
        <p className="mt-1 text-sm text-red-600">{error}</p>
      )}
      {helperText && !error && (
        <p className="mt-1 text-sm text-gray-500">{helperText}</p>
      )}
    </div>
  );
}

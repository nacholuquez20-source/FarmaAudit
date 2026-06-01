import React from 'react';
import { ChevronDown } from 'lucide-react';

type SelectSize = 'sm' | 'md' | 'lg';

export interface SelectOption {
  value: string | number;
  label: string;
  disabled?: boolean;
}

interface SelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  label?: string;
  selectSize?: SelectSize;
  error?: string;
  helperText?: string;
  options: SelectOption[];
  placeholder?: string;
}

const sizeClasses: Record<SelectSize, string> = {
  sm: 'px-2.5 py-1.5 text-sm',
  md: 'px-3 py-2 text-base',
  lg: 'px-4 py-2.5 text-lg',
};

export function Select({
  label,
  selectSize = 'md',
  error,
  helperText,
  options,
  placeholder,
  className = '',
  disabled = false,
  ...props
}: SelectProps) {
  const classes = `
    w-full appearance-none rounded-lg border pr-9 transition-colors
    ${error ? 'border-red-500 focus:border-red-600 focus:ring-red-100' : 'border-gray-300 focus:border-primary-navy focus:ring-blue-100'}
    ${sizeClasses[selectSize]}
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
      <div className="relative">
        <select
          disabled={disabled}
          className={classes}
          {...props}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((option) => (
            <option
              key={option.value}
              value={option.value}
              disabled={option.disabled}
            >
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDown
          className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400"
          size={20}
        />
      </div>
      {error && (
        <p className="mt-1 text-sm text-red-600">{error}</p>
      )}
      {helperText && !error && (
        <p className="mt-1 text-sm text-gray-500">{helperText}</p>
      )}
    </div>
  );
}

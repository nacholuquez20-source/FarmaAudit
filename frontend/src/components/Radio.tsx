import React from 'react';

interface RadioOption {
  value: string | number;
  label: string;
  disabled?: boolean;
}

interface RadioGroupProps {
  label?: string;
  name: string;
  options: RadioOption[];
  value?: string | number;
  onChange?: (value: string | number) => void;
  error?: string;
  helperText?: string;
  disabled?: boolean;
}

export function RadioGroup({
  label,
  name,
  options,
  value,
  onChange,
  error,
  helperText,
  disabled = false,
}: RadioGroupProps) {
  return (
    <div className="space-y-3">
      {label && (
        <label className="block text-sm font-medium text-gray-900">
          {label}
        </label>
      )}
      <div className="space-y-2">
        {options.map((option) => (
          <div key={option.value} className="flex items-center gap-3">
            <input
              type="radio"
              id={`${name}-${option.value}`}
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={(e) => onChange?.(e.target.value)}
              disabled={disabled || option.disabled}
              className="sr-only"
            />
            <div
              className={`
                relative h-5 w-5 rounded-full border-2 transition-colors
                ${error ? 'border-red-500' : 'border-gray-300'}
                ${!disabled && !option.disabled && 'cursor-pointer hover:border-gray-400'}
                ${disabled || option.disabled ? 'bg-gray-100 border-gray-200' : 'bg-white'}
                ${value === option.value ? 'border-primary-navy bg-white' : ''}
              `.trim()}
            >
              {value === option.value && (
                <div className="absolute inset-1 rounded-full bg-primary-navy" />
              )}
            </div>
            <label
              htmlFor={`${name}-${option.value}`}
              className={`text-sm ${disabled || option.disabled ? 'text-gray-500' : 'text-gray-900 cursor-pointer'}`}
            >
              {option.label}
            </label>
          </div>
        ))}
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

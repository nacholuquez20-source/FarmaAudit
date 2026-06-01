import React from 'react';
import { Check } from 'lucide-react';

interface CheckboxProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export function Checkbox({
  label,
  error,
  className = '',
  disabled = false,
  ...props
}: CheckboxProps) {
  return (
    <div className="flex items-start gap-3">
      <div className="relative">
        <input
          type="checkbox"
          disabled={disabled}
          className="sr-only"
          {...props}
        />
        <div
          className={`
            relative h-5 w-5 rounded border-2 transition-colors
            ${error ? 'border-red-500' : 'border-gray-300'}
            ${!disabled && !props.disabled && 'cursor-pointer hover:border-gray-400'}
            ${disabled ? 'bg-gray-100 border-gray-200' : 'bg-white'}
            ${props.checked ? 'border-primary-navy bg-primary-navy' : ''}
          `.trim()}
        >
          {props.checked && (
            <Check size={16} className="absolute inset-0.5 text-white" />
          )}
        </div>
      </div>
      {label && (
        <div className="flex-1">
          <label className={`text-sm ${disabled ? 'text-gray-500' : 'text-gray-900'}`}>
            {label}
          </label>
          {error && (
            <p className="mt-0.5 text-sm text-red-600">{error}</p>
          )}
        </div>
      )}
    </div>
  );
}

// Design tokens for consistent styling across the application
export const DESIGN_TOKENS = {
  colors: {
    // Primary brand
    primary: {
      navy: '#1e3a6d',
      orange: '#f15a29',
      green: '#2a9d5f',
    },
    // Status states for deviations
    status: {
      abierta: {
        bg: '#e0eaff',
        fg: '#1e3a6d',
        dot: '#1e3a6d',
      },
      en_proceso: {
        bg: '#fff1e6',
        fg: '#9a3a12',
        dot: '#f15a29',
      },
      resuelta: {
        bg: '#e7f6ec',
        fg: '#1e6f3d',
        dot: '#2a9d5f',
      },
      cerrada: {
        bg: '#f1f4f9',
        fg: '#475467',
        dot: '#667085',
      },
      vencida: {
        bg: '#fee2e2',
        fg: '#991b1b',
        dot: '#dc2626',
      },
    },
    // Severity levels
    severity: {
      critico: {
        bg: '#fee2e2',
        fg: '#991b1b',
        label: 'bg-red-100 text-red-900',
      },
      alta: {
        bg: '#fef3c7',
        fg: '#92400e',
        label: 'bg-amber-100 text-amber-900',
      },
      media: {
        bg: '#dbeafe',
        fg: '#1e40af',
        label: 'bg-blue-100 text-blue-900',
      },
      baja: {
        bg: '#dcfce7',
        fg: '#166534',
        label: 'bg-green-100 text-green-900',
      },
    },
    // Role-based colors
    roles: {
      auditor: '#10b981',
      sucursal: '#3b82f6',
      admin: '#8b5cf6',
    },
    // Neutral palette
    neutral: {
      50: '#f9fafb',
      100: '#f3f4f6',
      200: '#e5e7eb',
      300: '#d1d5db',
      400: '#9ca3af',
      500: '#6b7280',
      600: '#4b5563',
      700: '#374151',
      800: '#1f2937',
      900: '#111827',
    },
  },
  spacing: {
    xs: '0.25rem',
    sm: '0.5rem',
    md: '1rem',
    lg: '1.5rem',
    xl: '2rem',
    '2xl': '3rem',
  },
  shadows: {
    xs: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
    sm: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
    md: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
    lg: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
  },
  transitions: {
    fast: '150ms cubic-bezier(0.4, 0, 0.2, 1)',
    base: '200ms cubic-bezier(0.4, 0, 0.2, 1)',
    slow: '300ms cubic-bezier(0.4, 0, 0.2, 1)',
  },
} as const;

// Helper functions for status and severity styling
export function getStatusStyles(status: string) {
  const key = status.toLowerCase().replace(/\s+/g, '_');
  return DESIGN_TOKENS.colors.status[key as keyof typeof DESIGN_TOKENS.colors.status] ||
    DESIGN_TOKENS.colors.status.cerrada;
}

export function getSeverityStyles(severity: string) {
  const key = severity.toLowerCase();
  return DESIGN_TOKENS.colors.severity[key as keyof typeof DESIGN_TOKENS.colors.severity] ||
    DESIGN_TOKENS.colors.severity.baja;
}

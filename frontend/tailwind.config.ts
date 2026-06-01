import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Primary brand colors
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
        // Status colors - Deviations
        status: {
          abierta: {
            bg: '#e0eaff',
            text: '#1e3a6d',
            border: '#1e3a6d',
            dot: '#1e3a6d',
          },
          'en-proceso': {
            bg: '#fff1e6',
            text: '#9a3a12',
            border: '#f15a29',
            dot: '#f15a29',
          },
          resuelta: {
            bg: '#e7f6ec',
            text: '#1e6f3d',
            border: '#2a9d5f',
            dot: '#2a9d5f',
          },
          cerrada: {
            bg: '#f1f4f9',
            text: '#475467',
            border: '#667085',
            dot: '#667085',
          },
          vencida: {
            bg: '#fee2e2',
            text: '#991b1b',
            border: '#dc2626',
            dot: '#dc2626',
          },
        },
        // Severity levels
        severity: {
          critico: {
            bg: '#fee2e2',
            text: '#991b1b',
            border: '#dc2626',
          },
          alta: {
            bg: '#fef3c7',
            text: '#92400e',
            border: '#f59e0b',
          },
          media: {
            bg: '#dbeafe',
            text: '#1e40af',
            border: '#3b82f6',
          },
          baja: {
            bg: '#dcfce7',
            text: '#166534',
            border: '#22c55e',
          },
        },
        // Role colors
        role: {
          auditor: '#10b981',
          sucursal: '#3b82f6',
          admin: '#8b5cf6',
        },
        // Brand
        orange: '#f15a29',
        navy: '#1e3a6d',
        green: '#2a9d5f',
      },
      spacing: {
        xs: '0.25rem',
        sm: '0.5rem',
        md: '1rem',
        lg: '1.5rem',
        xl: '2rem',
        '2xl': '3rem',
      },
      typography: {
        sm: ['0.875rem', { lineHeight: '1.25rem' }],
        base: ['1rem', { lineHeight: '1.5rem' }],
        lg: ['1.125rem', { lineHeight: '1.75rem' }],
        xl: ['1.25rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.5rem', { lineHeight: '2rem' }],
      },
      animation: {
        'spin-slow': 'spin 3s linear infinite',
        'fade-in': 'fadeIn 0.3s ease-in',
        'slide-up': 'slideUp 0.3s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
};

export default config;

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Primary colors - OCR-LLM 绿色主色
        primary: {
          50: '#ecfdf3',
          100: '#d1fae1',
          200: '#a7f3c8',
          300: '#6ee7a1',
          400: '#34d37a',
          500: '#018c39',
          600: '#017a32',
          700: '#016629',
          800: '#014e20',
          900: '#013a18',
          950: '#0b1f10',
        },
        accent: {
          400: '#a78bfa',
          500: '#8b5cf6',
          600: '#7c3aed',
        },
        success: {
          500: '#10b981',
        },
        warning: {
          500: '#f59e0b',
        },
        error: {
          500: '#ef4444',
        },
        // Background
        bg: {
          primary: '#0f172a',
          secondary: '#111f36',
          tertiary: '#13264a',
          card: '#162b52',
          hover: '#1b3566',
        },
        // Text
        text: {
          primary: '#f1f5f9',
          secondary: '#cbd5e1',
          muted: '#94a3b8',
        },
        // Border
        border: {
          default: '#334155',
          focus: '#018c39',
        },
      },
      fontFamily: {
        sans: ['Fira Sans', 'Noto Sans SC', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['Fira Code', 'JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        'xl': '0.75rem',
        '2xl': '1rem',
      },
      animation: {
        'fadeIn': 'fadeIn 0.3s ease-out',
        'slideInUp': 'slideInUp 0.4s ease-out',
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          'from': { opacity: '0', transform: 'translateY(10px)' },
          'to': { opacity: '1', transform: 'translateY(0)' },
        },
        slideInUp: {
          'from': { opacity: '0', transform: 'translateY(20px)' },
          'to': { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-glow': {
          '0%, 100%': { boxShadow: '0 0 20px rgba(1, 140, 57, 0.3)' },
          '50%': { boxShadow: '0 0 40px rgba(1, 140, 57, 0.6)' },
        },
      },
    },
  },
  plugins: [],
}




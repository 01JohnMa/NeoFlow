/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Primary colors - NeoFlow violet accent
        primary: {
          50: '#f5f3ff',
          100: '#ede9fe',
          200: '#ddd6fe',
          300: '#c4b5fd',
          400: '#a78bfa',
          500: '#7c5cff',
          600: '#6848e8',
          700: '#5635c7',
          800: '#3e278f',
          900: '#281b5f',
          950: '#17102f',
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
        // Surface / text / border 使用语义 CSS 变量：
        // 默认深色；`.theme-light` 作用域内切换为浅色（Playground 内容区）
        bg: {
          primary: 'rgb(var(--nf-bg-primary) / <alpha-value>)',
          secondary: 'rgb(var(--nf-bg-secondary) / <alpha-value>)',
          tertiary: 'rgb(var(--nf-bg-tertiary) / <alpha-value>)',
          card: 'rgb(var(--nf-bg-card) / <alpha-value>)',
          hover: 'rgb(var(--nf-bg-hover) / <alpha-value>)',
        },
        text: {
          primary: 'rgb(var(--nf-text-primary) / <alpha-value>)',
          secondary: 'rgb(var(--nf-text-secondary) / <alpha-value>)',
          muted: 'rgb(var(--nf-text-muted) / <alpha-value>)',
        },
        border: {
          default: 'rgb(var(--nf-border-default) / <alpha-value>)',
          focus: '#7c5cff',
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

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#ecfeff',
          100: '#cffaff',
          200: '#a5f3fc',
          300: '#67e8f9',
          400: '#22d3ee',
          500: '#06b6d4', // Cyan
          600: '#0891b2',
          700: '#0e7490',
          800: '#155e75',
          900: '#164e63',
          950: '#083344',
        },
        navy: {
          800: '#0b1329',
          850: '#0f172a',
          900: '#090d16',
          950: '#050811',
        },
        panel: {
          dark: '#0f172a',
          darker: '#090d16',
          border: 'rgba(56, 189, 248, 0.15)',
          light: '#ffffff',
          lightborder: '#e2e8f0',
        },
        status: {
          normal: '#10b981',      // Emerald green
          transient: '#f59e0b',   // Amber
          anomaly: '#ef4444',     // Bright Red
          fault: '#ec4899',       // Purple/Pink
          calibrating: '#3b82f6', // Blue
        }
      },
      fontFamily: {
        sans: ['Inter', 'Outfit', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      boxShadow: {
        'glow-cyan': '0 0 25px -5px rgba(6, 182, 212, 0.4)',
        'glow-red': '0 0 25px -5px rgba(239, 68, 68, 0.5)',
        'glow-amber': '0 0 25px -5px rgba(245, 158, 11, 0.4)',
        'glass': '0 8px 32px 0 rgba(0, 0, 0, 0.37)',
      },
      animation: {
        'pulse-glow': 'pulseGlow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'water-flow': 'waterFlow 3s linear infinite',
        'ripple': 'ripple 1.5s ease-out infinite',
      },
      keyframes: {
        pulseGlow: {
          '0%, 100%': { opacity: 1, filter: 'drop-shadow(0 0 10px rgba(6, 182, 212, 0.8))' },
          '50%': { opacity: 0.6, filter: 'drop-shadow(0 0 2px rgba(6, 182, 212, 0.2))' },
        },
        waterFlow: {
          '0%': { strokeDashoffset: '40' },
          '100%': { strokeDashoffset: '0' },
        },
        ripple: {
          '0%': { transform: 'scale(0.8)', opacity: '1' },
          '100%': { transform: 'scale(2.2)', opacity: '0' },
        }
      }
    },
  },
  plugins: [],
}

import type { Config } from 'tailwindcss'

// Every colour is a CSS variable ("R G B" channels) defined in src/styles/tokens.css,
// so Tailwind's opacity modifiers work (bg-signal-green/20) and a light theme
// only has to redefine the variables.
const channel = (name: string) => `rgb(var(--c-${name}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: { 0: channel('canvas-0'), 1: channel('canvas-1'), 2: channel('canvas-2') },
        surface: { DEFAULT: channel('surface'), raised: channel('surface-raised') },
        line: channel('line'),
        ink: { DEFAULT: channel('ink'), muted: channel('ink-muted'), dim: channel('ink-dim') },
        signal: {
          green: channel('green'),
          amber: channel('amber'),
          red: channel('red'),
          cyan: channel('cyan'),
          violet: channel('violet'),
        },
        train: {
          express: channel('express'),
          passenger: channel('passenger'),
          freight: channel('freight'),
        },
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'Inter', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: { '2xl': '1rem', '3xl': '1.5rem' },
      boxShadow: {
        panel: '0 1px 0 0 rgb(255 255 255 / 0.04) inset, 0 20px 50px -20px rgb(0 0 0 / 0.7)',
        glow: '0 0 0 1px rgb(var(--c-cyan) / 0.35), 0 8px 30px -6px rgb(var(--c-cyan) / 0.45)',
      },
    },
  },
  plugins: [],
} satisfies Config

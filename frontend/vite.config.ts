import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API allows CORS from http://localhost:5173 only, so the dev server
// must run on exactly that origin.
export default defineConfig({
  plugins: [react()],
  server: { host: 'localhost', port: 5173, strictPort: true },
  preview: { host: 'localhost', port: 5173, strictPort: true },
  build: {
    rollupOptions: {
      output: {
        // vendor chunks cache well and keep every chunk under the 500 kB warning
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          motion: ['framer-motion'],
          ui: ['@radix-ui/react-dialog', '@radix-ui/react-tooltip', '@radix-ui/react-tabs', '@radix-ui/react-toast', '@radix-ui/react-radio-group', 'lucide-react'],
          data: ['@tanstack/react-query', 'zustand'],
        },
      },
    },
  },
})

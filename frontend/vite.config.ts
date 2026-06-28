import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/static/spa/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: path.resolve(__dirname, '../src/web/static/spa'),
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 5173,
    proxy: {
      // BUG C-2: FastAPI v2 corre en :8000 (arrancado por src/main.py:309).
      // Antes solo se proxyeaba /api a Flask:5000, así que las llamadas a
      // /api/v2/* caían en Flask y devolvían 404. Ahora /api/v2 va a FastAPI
      // y el resto de /api sigue yendo a Flask. El orden importa: la ruta
      // más específica (/api/v2) debe ir antes que la general (/api).
      '/api/v2': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:5000',
        ws: true,
      },
    },
  },
})

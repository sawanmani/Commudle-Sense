import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The UI calls /api/* and Vite forwards it to FastAPI, so the browser only ever talks to one
// origin: no CORS changes on the backend. Point it elsewhere with API_TARGET=http://127.0.0.1:8010
const API_TARGET = process.env.API_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180, // not 5173: other local projects (e.g. Docker dashboards) often claim it
    strictPort: true,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, '') },
      // FastAPI's interactive docs page loads /openapi.json from the site root
      '/docs': { target: API_TARGET, changeOrigin: true },
      '/openapi.json': { target: API_TARGET, changeOrigin: true },
    },
  },
  preview: {
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})

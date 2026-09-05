import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // The SSE endpoint needs buffering disabled; Vite's proxy passes it through.
      '/api': { target: 'http://localhost:8000', changeOrigin: true, ws: false }
    }
  },
  build: { outDir: 'dist', sourcemap: false, chunkSizeWarningLimit: 900 }
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev proxy forwards /api to the FastAPI backend so the browser stays same-origin.
export default defineConfig({
  plugins: [react()],
  server: {
    // Listen on all interfaces (incl. IPv4 0.0.0.0). Vite's default "localhost"
    // binds IPv6 ::1 only in the Dev Container, which VS Code port forwarding
    // (IPv4 127.0.0.1) can't reach -> blank screen in the browser.
    host: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})

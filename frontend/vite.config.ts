import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The browser only talks to this origin; /api is forwarded to our backend (never to the upstream).
const backendUrl = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 4000,
    strictPort: true,
    proxy: { '/api': backendUrl },
  },
})

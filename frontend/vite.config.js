import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// In live mode the UI talks to the FastAPI backend through this dev proxy,
// so the browser sees one origin and CORS is not needed during development.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_BACKEND_URL || 'http://localhost:8000'
  return {
    plugins: [react()],
    test: { environment: 'jsdom', setupFiles: ['./src/test/setup.js'], css: false },
    server: {
      port: 5173,
      proxy: {
        '/api': target,
        '/mock': target,
        '/evidence': target,
        '/video_feed': target,
        '/ws': { target, ws: true, changeOrigin: true },
      },
    },
  }
})

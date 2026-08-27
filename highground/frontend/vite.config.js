import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The SPA calls /api on its own origin and Vite forwards to Django on :8000.
// Same-origin keeps the session cookie working with no CORS layer at all.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',  // bind IPv4 explicitly; the default binds ::1 only
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      // Django admin is screens 14/19 (ADR-002), so it ships on the same
      // origin and inherits the session. /static carries its CSS.
      '/admin': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/static': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      // Uploaded files (registration documents). Without this the admin's
      // PDF links fall through to the SPA's index.html and render the app
      // instead of the file — a 200, so nothing looks broken.
      '/media': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})

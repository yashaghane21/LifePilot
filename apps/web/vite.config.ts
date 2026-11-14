import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // The browser only ever talks to the Vite origin; /api is forwarded to FastAPI.
    // One origin means no CORS, and the refresh cookie behaves exactly as in production.
    proxy: {
      // LIFEPILOT_API lets end-to-end tests point at a separate backend instance.
      '/api': process.env.LIFEPILOT_API ?? 'http://localhost:8000',
    },
  },
})

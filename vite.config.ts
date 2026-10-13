
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [tailwindcss(), react()],
    resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    // Явно IPv4: иначе Vite садится на ::1, и браузер по localhost не достучится
    host: '127.0.0.1',
    // Разработка с CRM: VITE_API_URL=/api/v1, запросы уходят на локальную CRM с того же адреса,
    // поэтому кука сессии работает без CORS
    proxy: {
      '/api': process.env.CRM_DEV_URL || 'http://127.0.0.1:18081',
    },
  },
})

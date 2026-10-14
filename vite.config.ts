
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import fs from 'fs'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'

// Подложка карты (public/maps, 130+ МБ) в сборку для CRM не попадает: CRM отдаёт её из своей
// папки maps/, и выкладка фронта не тащит файл каждый раз
const skipMapTilesForCrm = (): Plugin => {
  let outDir = ''
  return {
    name: 'skip-map-tiles-for-crm',
    apply: (_, env) => env.command === 'build' && env.mode === 'crm',
    configResolved(config) {
      outDir = path.resolve(config.root, config.build.outDir)
    },
    closeBundle() {
      fs.rmSync(path.join(outDir, 'maps'), { recursive: true, force: true })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [tailwindcss(), react(), skipMapTilesForCrm()],
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

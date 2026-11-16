import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import { readonlyProxy } from './local/readonly-proxy.ts'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss(), readonlyProxy(loadEnv(mode, process.cwd(), 'ROOM_'))],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { host: '127.0.0.1', port: 5173, strictPort: true },
}))

import path from 'path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/tenants': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/scenarios': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/incidents': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/counterfactual': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ask': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/graph': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/memory': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/benchmark': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/inspect': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})

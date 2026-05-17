import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': '/src',
    },
  },
  server: {
    proxy: {
      '/ws/simple-ide': {
        target: 'http://127.0.0.1:8001',
        ws: true,
        changeOrigin: true,
        rewrite: (path) => path.replace('/ws/simple-ide', '/ws/coding'),
      },
      '/ws/coding': {
        target: 'http://127.0.0.1:8001',
        ws: true,
        changeOrigin: true,
      },
      '/ws/terminal': {
        target: 'http://127.0.0.1:8001',
        ws: true,
        changeOrigin: true,
      },
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks: {
          monaco: ['monaco-editor'],
          xterm: ['@xterm/xterm', '@xterm/addon-fit'],
        },
      },
    },
  },
  optimizeDeps: {
    include: [
      'monaco-editor/esm/vs/editor/editor.api',
    ],
  },
})

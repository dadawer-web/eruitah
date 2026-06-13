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
    headers: {
      'Cross-Origin-Embedder-Policy': 'require-corp',
      'Cross-Origin-Opener-Policy': 'same-origin',
    },
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
    target: 'esnext',
    rollupOptions: {
      output: {
        format: 'es',
        inlineDynamicImports: false,
        manualChunks(id) {
          if (id.includes('monaco-editor')) return 'monaco'
          if (id.includes('@xterm')) return 'xterm'
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

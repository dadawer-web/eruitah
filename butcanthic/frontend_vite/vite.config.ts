import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  define: {
    'process.env.NODE_ENV': '"production"',
  },
  server: {
    port: 5174,
    host: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
    },
  },
  build: {
    lib: {
      entry: 'src/index.tsx',
      name: 'PPTViewer',
      fileName: 'ppt-viewer',
      formats: ['iife'],
    },
    outDir: '../static/ppt-viewer',
    emptyOutDir: false,
    rollupOptions: {
      output: {
        assetFileNames: 'ppt-viewer.[ext]',
      },
    },
  },
});

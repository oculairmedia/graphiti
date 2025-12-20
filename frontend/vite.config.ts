import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { componentTagger } from "lovable-tagger";
import { visualizer } from "rollup-plugin-visualizer";

export default defineConfig(({ mode }) => ({
  esbuild: {
    pure: mode === 'production' ? ['console.log', 'console.debug', 'console.info'] : [],
  },
  build: {
    rollupOptions: {
      output: {
        // CRITICAL FIX: Use object syntax to avoid circular dependencies
        // Function-based manualChunks was causing React circular imports
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react/jsx-runtime'],
        },
        chunkFileNames: 'chunk-[hash].js',
      },
    },
    chunkSizeWarningLimit: 1200,
  },
  server: {
    host: "::",
    port: 8084,
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
    proxy: {
      '/api': { target: 'http://localhost:3000', changeOrigin: true },
      '/ws': { target: 'http://localhost:8003', ws: true, changeOrigin: true },
      '/graphiti': { target: 'http://localhost:8003', changeOrigin: true, rewrite: (p) => p.replace(/^\/graphiti/, '') },
    },
  },
  plugins: [
    react(),
    mode === 'development' && componentTagger(),
    mode === 'production' && visualizer({ filename: 'dist/stats.html', open: false, gzipSize: true, brotliSize: true }),
  ].filter(Boolean),
  resolve: {
    alias: { "@": path.resolve(process.cwd(), "./src") },
    dedupe: ['react', 'react-dom', 'react/jsx-runtime'],
  },
  optimizeDeps: {
    include: ['react', 'react-dom', 'react/jsx-runtime'],
  },
}));

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { componentTagger } from "lovable-tagger";
import { visualizer } from "rollup-plugin-visualizer";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  // PERFORMANCE FIX (GRAPH-68): Strip console.log/debug in production builds
  // This eliminates 80+ console statements that cause GC pressure from string allocations
  // Note: console.error and console.warn are preserved for production error tracking
  esbuild: {
    pure: mode === 'production' ? ['console.log', 'console.debug', 'console.info'] : [],
  },
  build: {
    // Optimize chunk splitting
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          // Core React - small, critical
          if (id.includes('node_modules/react/') || id.includes('node_modules/react-dom/')) {
            return 'vendor-react';
          }
          // Radix UI components - used throughout UI
          if (id.includes('node_modules/@radix-ui/')) {
            return 'vendor-radix';
          }
          // Cosmograph and D3 - large, lazy-loaded with graph
          if (id.includes('node_modules/@cosmograph/') || id.includes('node_modules/d3')) {
            return 'vendor-graph';
          }
          // DuckDB - large, lazy-loaded
          if (id.includes('node_modules/@duckdb/') || id.includes('node_modules/apache-arrow')) {
            return 'vendor-duckdb';
          }
          // Charts - used in stats panels
          if (id.includes('node_modules/recharts')) {
            return 'vendor-charts';
          }
          // Icons - tree-shaken but still sizeable
          if (id.includes('node_modules/lucide-react')) {
            return 'vendor-icons';
          }
          // TanStack Query - data fetching
          if (id.includes('node_modules/@tanstack/')) {
            return 'vendor-query';
          }
          // Zustand - state management
          if (id.includes('node_modules/zustand')) {
            return 'vendor-zustand';
          }
          // Floating UI - used by Radix popovers
          if (id.includes('node_modules/@floating-ui/')) {
            return 'vendor-floating';
          }
        },
        // Optimize chunk names
        chunkFileNames: (chunkInfo) => {
          const facadeModuleId = chunkInfo.facadeModuleId ? chunkInfo.facadeModuleId.split('/').pop() : 'chunk';
          return `${facadeModuleId}-[hash].js`;
        },
      },
    },
    // Silence chunk size warnings - we're intentionally splitting vendors
    chunkSizeWarningLimit: 600,
  },
  server: {
    host: "::",
    port: 8084,
    // PERFORMANCE: Enable cross-origin isolation for SharedArrayBuffer + Worker multi-threading
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
    proxy: {
      '/api': {
        target: 'http://localhost:3000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'http://localhost:8003',
        ws: true,
        changeOrigin: true,
        configure: (proxy, options) => {
          proxy.on('error', (err) => {
            console.log('WebSocket proxy error:', err);
          });
          proxy.on('proxyReqWs', (proxyReq, req, socket) => {
            console.log('WebSocket upgrade request:', req.url);
          });
        },
      },
      '/graphiti': {
        target: 'http://localhost:8003',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/graphiti/, ''),
      },
    },
  },
  plugins: [
    react({
      babel: {
        plugins: ['babel-plugin-react-compiler']
      }
    }),
    mode === 'development' && componentTagger(),
    // Generate bundle analysis on build (open dist/stats.html to view)
    mode === 'production' && visualizer({
      filename: 'dist/stats.html',
      open: false,
      gzipSize: true,
      brotliSize: true,
    }),
  ].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(process.cwd(), "./src"),
    },
    // CRITICAL: Deduplicate React to fix "Cannot read properties of undefined (reading 'createContext')"
    // This ensures all packages use the same React instance, preventing version conflicts
    dedupe: ['react', 'react-dom'],
  },
}));

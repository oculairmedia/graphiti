import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { componentTagger } from "lovable-tagger";

export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8082,
    proxy: {
      '/api': {
        target: 'http://localhost:4543',
        changeOrigin: true,
      },
      '/ws': {
        target: 'http://localhost:4543',
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
    mode === 'development' &&
    componentTagger(),
  ].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(process.cwd(), "./src"),
    },
  },
  define: {
    'import.meta.env.VITE_RUST_WS_URL': JSON.stringify('ws://localhost:4543/ws'),
    'import.meta.env.VITE_RUST_WS_PORT': JSON.stringify('4543'),
  },
}));

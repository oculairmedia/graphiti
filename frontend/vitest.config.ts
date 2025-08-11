/// <reference types="vitest/config" />
import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config';

export default defineConfig((configEnv) => 
  mergeConfig(
    viteConfig(configEnv),
    defineConfig({
      test: {
      // Test configuration
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      
      // Coverage configuration
      coverage: {
        reporter: ['text', 'json', 'html'],
        exclude: [
          'node_modules/',
          'src/test/',
          '*.config.ts',
          '*.config.js',
          'src/types/',
          'src/**/*.d.ts',
        ],
      },
      
      // Include patterns
      include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
      
      // Exclude patterns
      exclude: ['node_modules', 'dist', '.idea', '.git', '.cache'],
      
      // Mock configuration
      mockReset: true,
      clearMocks: true,
      restoreMocks: true,
      
      // Threading
      pool: 'threads',
      poolOptions: {
        threads: {
          singleThread: false,
        },
      },
      
      // Timeouts
      testTimeout: 10000,
      hookTimeout: 10000,
    },
  })
  )
);
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// BrainSync web UI. Relative base: ServiceHub serves the page under /s/<id>/, so every URL must be relative.
export default defineConfig({
  base: './',
  plugins: [vue()],
  build: {
    // style.css colors are light-dark() tokens (the theme toggle sets color-scheme). Below these versions the
    // CSS minifier rewrites them into a prefers-color-scheme query, which the toggle can't override.
    cssTarget: ['chrome123', 'firefox120', 'safari17.5'],
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
    restoreMocks: true,
  },
  server: {
    port: 26509,
    strictPort: true,
    host: '127.0.0.1',
    proxy: { '/api': { target: 'http://127.0.0.1:26508' } },
  },
})

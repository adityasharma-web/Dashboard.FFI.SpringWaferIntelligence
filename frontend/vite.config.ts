import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8090',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
    alias: {
      /* plotly.js needs a real browser; tests assert on the figure builders
         and on what the stub receives instead. */
      'plotly.js-dist-min': fileURLToPath(new URL('./src/test/plotlyStub.ts', import.meta.url)),
    },
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/main.tsx', 'src/**/*.d.ts'],
      reporter: ['text', 'lcov'],
    },
  },
})

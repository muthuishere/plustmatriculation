import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Builds straight into ../docs so GitHub Pages can serve the repo's /docs
// folder. emptyOutDir is off on purpose: docs/ also holds assets/ (the paper
// corpus and extracted text) and data/ (the JSON + Parquet), none of which
// Vite knows about and all of which it would otherwise delete.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: '../docs',
    emptyOutDir: false,
    assetsDir: 'app',
    target: 'es2022',
  },
  worker: { format: 'es' },
  optimizeDeps: { exclude: ['@duckdb/duckdb-wasm'] },
})

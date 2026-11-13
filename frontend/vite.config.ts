import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { viteStaticCopy } from 'vite-plugin-static-copy'

export default defineConfig({
  plugins: [vue(), viteStaticCopy({ targets: ['cmaps', 'standard_fonts', 'wasm'].map(directory => ({ src: `node_modules/pdfjs-dist/${directory}/*`, dest: `pdfjs/${directory}`, rename: { stripBase: true } })) })],
  server: { proxy: { '/api': process.env.API_TARGET || 'http://127.0.0.1:8000' } },
})

import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:4173', channel: 'chrome', screenshot: 'only-on-failure' },
  webServer: [
    { command: '"..\\.venv\\Scripts\\python.exe" ..\\tests\\e2e_server.py', url: 'http://127.0.0.1:8001/api/setup', timeout: 30000 },
    { command: 'npm run dev -- --port 4173 --strictPort', url: 'http://127.0.0.1:4173', env: { API_TARGET: 'http://127.0.0.1:8001' } },
  ],
})

import { definePlaywrightConfig } from '@wshno/playwright-config'

// Runs against the PVE container from docker-compose.e2e.yml. Shared defaults (testDir ./tests,
// forbidOnly, reporters, trace/screenshot/video on failure) come from @wshno/playwright-config.
//
// The tests share one node and its VM IDs, so they run one at a time.
export default definePlaywrightConfig({
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env.PVE_URL ?? 'https://localhost:8006',
    // pveproxy serves a self-signed certificate generated at first boot.
    ignoreHTTPSErrors: true,
  },
})

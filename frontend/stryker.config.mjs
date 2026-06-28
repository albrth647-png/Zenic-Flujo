/**
 * Stryker config — baseline de mutation testing para Fase 2
 *
 * Target: src/utils/humanize.ts (módulo pequeño, puro, con tests indirectos)
 * Test runner: vitest
 *
 * Para correr: npx stryker run
 */
export default {
  mutate: ["src/utils/humanize.ts"],
  coverageAnalysis: "perTest",
  testRunner: "vitest",
  reporters: ["clear-text", "html", "json"],
  timeoutMS: 60000,
  concurrency: 2,
  thresholds: {
    high: 80,
    low: 60,
    break: 0,
  },
  vitest: {
    configFile: "vitest.config.ts",
  },
}

import { base, ignores, node, playwright } from '@wshno/eslint-config'

// @wshno/eslint-config: JS/TS and SonarJS recommended, Node globals, and the Playwright rules for the specs.
/** @type {import('eslint').Linter.Config[]} */
export default [
  ...ignores,
  { ignores: ['playwright-report/**', 'test-results/**'] },
  ...base,
  ...node,
  ...playwright(['tests/**/*.ts']),
]

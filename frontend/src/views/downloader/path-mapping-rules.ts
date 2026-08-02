/**
 * Generates an external path from the first matching path-mapping rule.
 * Rules use the format: source{#**#}target.
 */
export function generateExternalPathFromRules(
  internalPath: string,
  rulesText?: string
): string | null {
  if (!rulesText) {
    return null
  }

  const normalizedRulesText = rulesText.trim()
  if (!normalizedRulesText) {
    return null
  }

  const rules = normalizedRulesText
    .split('\n')
    .filter(line => line.trim())
    .sort((a, b) => b.length - a.length)

  for (const rule of rules) {
    const separator = '{#**#}'
    if (!rule.includes(separator)) {
      continue
    }

    const [source, target] = rule.split(separator)
    if (!source || !target) {
      continue
    }

    const normalizedSource = source.trim()
    const normalizedTarget = target.trim()
    if (internalPath.startsWith(normalizedSource)) {
      const relativePath = internalPath.substring(normalizedSource.length)
      return normalizedTarget + relativePath
    }
  }

  return null
}

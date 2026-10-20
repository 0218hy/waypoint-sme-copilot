/** One dotted milestone line on a week-indexed chart; `label` is null when a nearby line carries it. */
export interface MilestoneMark {
  /** Category index on the x axis. */
  x: number
  label: string | null
}

/** Smallest gap between two marker labels, in px: room for two range labels like "5–7". */
export const MIN_LABEL_GAP_PX = 26

/**
 * Milestone lines for a chart whose x axis is `weeks`. Every milestone keeps its own line, but
 * milestones closer than `minGapPx` on screen share one label, e.g. "5–7", on the first line of
 * the group. Numbers match the list under the chart (1-based position in `milestones`).
 */
export function milestoneMarks(
  milestones: readonly (readonly [number, string])[],
  weeks: readonly number[],
  plotWidthPx: number,
  minGapPx = MIN_LABEL_GAP_PX,
): MilestoneMark[] {
  const idx = new Map(weeks.map((w, i) => [w, i]))
  const pts = milestones
    .map(([w], i) => ({ n: i + 1, x: idx.get(w) }))
    .filter((p): p is { n: number; x: number } => p.x !== undefined)
    .sort((a, b) => a.x - b.x || a.n - b.n)
  const pxPerStep = plotWidthPx / Math.max(1, weeks.length - 1)
  const minSteps = Math.max(1, minGapPx / Math.max(pxPerStep, 0.001))
  const groups: { x: number; ns: number[] }[] = []
  for (const p of pts) {
    const g = groups[groups.length - 1]
    if (g && p.x - g.x < minSteps) g.ns.push(p.n)
    else groups.push({ x: p.x, ns: [p.n] })
  }
  const labels = new Map(groups.map((g) => [g.x, groupLabel(g.ns)]))
  return [...new Set(pts.map((p) => p.x))].map((x) => ({ x, label: labels.get(x) ?? null }))
}

/** "5", "5–7" for a consecutive run, else "2, 5". */
export function groupLabel(ns: readonly number[]): string {
  const s = [...ns].sort((a, b) => a - b)
  if (s.length === 1) return String(s[0])
  const consecutive = s.every((n, i) => i === 0 || n === s[i - 1]! + 1)
  return consecutive ? `${s[0]}–${s[s.length - 1]}` : s.join(', ')
}

// Widget fixtures for the dev gallery and tests: one JSON file per widget state.
import type { Widget } from '@/contracts/types'

const modules = import.meta.glob<Widget>('./fixtures/*.json', { eager: true, import: 'default' })

export const fixtures: { name: string; widget: Widget }[] = Object.entries(modules)
  .map(([path, widget]) => ({ name: path.replace('./fixtures/', '').replace('.json', ''), widget }))
  .sort((a, b) => a.name.localeCompare(b.name))

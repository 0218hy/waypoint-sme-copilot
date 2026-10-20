import EChartsReactCore from 'echarts-for-react/esm/core'
import type { EChartsOption } from 'echarts-for-react/lib/types'
import { echarts, registerMapOnce } from './echarts'
import { useChartTheme, useReducedMotion } from './theme'

export interface EChartProps {
  option: EChartsOption
  height: number
  /** Short description for assistive tech; a text fallback should sit next to the chart. */
  label: string
  onEvents?: Record<string, (params: unknown) => void>
  className?: string
  /** GeoJSON maps the option refers to, registered once by name before rendering. */
  maps?: Record<string, unknown>
}

/** ECharts with the SVG renderer (crisp on phones, works in WebViews). Loaded lazily via EChart. */
export default function EChartImpl({ option, height, label, onEvents, className, maps }: EChartProps) {
  for (const [name, geo] of Object.entries(maps ?? {})) registerMapOnce(name, geo)
  const reduced = useReducedMotion()
  const theme = useChartTheme()
  const tooltip = option.tooltip
    ? {
        backgroundColor: theme.surface,
        borderColor: theme.border,
        textStyle: { color: theme.text, fontSize: 12 },
        extraCssText: 'border-radius:10px;box-shadow:0 4px 12px rgba(0,0,0,.12);',
        ...option.tooltip,
      }
    : undefined
  return (
    <div role="img" aria-label={label} className={className}>
      <EChartsReactCore
        echarts={echarts}
        option={{ animation: !reduced, animationDuration: 300, animationDurationUpdate: 200, ...option, ...(tooltip ? { tooltip } : {}) }}
        notMerge
        lazyUpdate
        opts={{ renderer: 'svg' }}
        style={{ height, width: '100%' }}
        onEvents={onEvents}
      />
    </div>
  )
}

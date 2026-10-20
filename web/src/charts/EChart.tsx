import { lazy, Suspense } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import type { EChartProps } from './EChartImpl'

// ECharts is the largest dependency; load it on the first chart, not with the chat shell.
const EChartImpl = lazy(() => import('./EChartImpl'))

export function EChart(props: EChartProps) {
  return (
    <Suspense fallback={<Skeleton className="w-full" height={props.height} />}>
      <EChartImpl {...props} />
    </Suspense>
  )
}

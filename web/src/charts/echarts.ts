// Tree-shaken ECharts: register only what Waypoint's charts use.
import { BarChart, LineChart, MapChart, ScatterChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GeoComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import * as echarts from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'

echarts.use([
  BarChart,
  LineChart,
  MapChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  MarkAreaComponent,
  VisualMapComponent,
  GeoComponent,
  DataZoomComponent,
  SVGRenderer,
])

export { echarts }

const registered = new Map<string, unknown>()

/** Register a GeoJSON map once per name. */
export function registerMapOnce(name: string, geojson: unknown): void {
  if (registered.get(name) === geojson) return
  echarts.registerMap(name, geojson as Parameters<typeof echarts.registerMap>[1])
  registered.set(name, geojson)
}

import 'leaflet/dist/leaflet.css'
import { CircleMarker, MapContainer, TileLayer, Tooltip } from 'react-leaflet'

export interface UnitPin {
  id: string
  lat: number
  lng: number
  label: string
  chosen?: boolean
}

// OneMap raster tiles (EPSG:3857). OneMap's terms require its attribution. The official logo is
// not bundled (fetching third-party files needs the owner's say-so), and loading it from
// onemap.gov.sg at runtime would break the no-CDN rule (SPEC §2.4). So the attribution is text,
// linking to OneMap and SLA. To show the logo, add it as web/public/onemap-logo.png and set
// ONEMAP_LOGO to 'onemap-logo.png'.
export const ONEMAP_TILES = 'https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png'
const ONEMAP_LOGO: string | null = null
const ONEMAP_ATTRIBUTION =
  (ONEMAP_LOGO ? `<img src="${ONEMAP_LOGO}" style="height:20px;width:20px;" alt="OneMap logo"/>&nbsp;` : '') +
  'Map data &copy; <a href="https://www.onemap.gov.sg/" target="_blank" rel="noopener noreferrer">OneMap</a>, <a href="https://www.sla.gov.sg/" target="_blank" rel="noopener noreferrer">Singapore Land Authority</a>'

// Singapore's extent; OneMap tiles exist only here.
const SG_BOUNDS: [[number, number], [number, number]] = [
  [1.144, 103.535],
  [1.494, 104.1],
]

export default function UnitMap({ pins, label }: { pins: UnitPin[]; label: string }) {
  const lats = pins.map((p) => p.lat)
  const lngs = pins.map((p) => p.lng)
  const bounds: [[number, number], [number, number]] =
    pins.length > 0
      ? [
          [Math.min(...lats) - 0.004, Math.min(...lngs) - 0.004],
          [Math.max(...lats) + 0.004, Math.max(...lngs) + 0.004],
        ]
      : SG_BOUNDS
  return (
    <div role="region" aria-label={label} className="overflow-hidden rounded-xl border border-border">
      <MapContainer
        bounds={bounds}
        maxBounds={SG_BOUNDS}
        minZoom={11}
        maxZoom={19}
        scrollWheelZoom={false}
        style={{ height: 220, width: '100%' }}
      >
        <TileLayer url={ONEMAP_TILES} attribution={ONEMAP_ATTRIBUTION} detectRetina maxNativeZoom={19} />
        {pins.map((p) => (
          <CircleMarker
            key={p.id}
            center={[p.lat, p.lng]}
            radius={p.chosen ? 11 : 9}
            pathOptions={{ color: '#ffffff', weight: 2, fillColor: p.chosen ? '#0f766e' : '#17202b', fillOpacity: 0.95 }}
          >
            <Tooltip direction="top" offset={[0, -8]} permanent>
              {p.label}
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}

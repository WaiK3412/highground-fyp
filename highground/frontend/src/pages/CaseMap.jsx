/**
 * Screen 07's Map view — the visible queue at the precision each role may see.
 *
 * The server decides what is a point and what is only a village count
 * (/api/cases/map/); this component draws what it is given and nothing more.
 * Plain Leaflet rather than react-leaflet (ADR-003 revision): one dependency
 * with a standard licence. React owns the page; Leaflet owns only the element
 * behind `container`.
 *
 * The tiles come from OpenStreetMap's public server, which is best-effort. If
 * they fail, the markers still draw on a blank background and a banner says
 * so — a grey box with no explanation is the failure this avoids.
 */

import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Configurable, as OSM's tile usage policy asks, so a different provider or a
// self-hosted server needs no code change.
const TILE_URL = import.meta.env.VITE_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
// Kelantan's centre point from the HDX gazetteer, shown until markers arrive.
const KELANTAN = [5.398, 102.077]

// Same three bands as the queue's score chips.
const TONE = { High: 'danger', Medium: 'warning', Low: 'success' }
// Nearby markers overlap; the most urgent one is drawn on top.
const LAYER = { High: 3000, Medium: 2000, Low: 1000 }

// Case and village text can come from older free-text submissions, so it is
// set as text content — never passed to Leaflet as an HTML string.
function tooltip(lines) {
  const node = document.createElement('div')
  lines.forEach((line) => {
    const row = document.createElement('div')
    row.textContent = line
    node.appendChild(row)
  })
  return node
}

function pinIcon(point) {
  const tone = TONE[point.priority_band] || 'neutral'
  const ring = point.claimed_by_you ? ' ops-pin--ring' : ''
  return L.divIcon({
    className: 'case-map__icon',
    html: `<span class="ops-pin ops-pin--${tone}${ring}"></span>`,
    iconSize: [26, 26],
    // The teardrop is a rotated square; its tip sits below the centre.
    iconAnchor: [13, 31],
  })
}

function areaIcon(area) {
  const tone = TONE[area.highest_band] || 'neutral'
  const count = Number(area.case_count) || 0
  return L.divIcon({
    className: 'case-map__icon',
    html: `<span class="ops-marker ops-marker--${tone}">${count}</span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  })
}

export default function CaseMap({ points, areas, onOpenCase, onOpenArea }) {
  const container = useRef(null)
  const map = useRef(null)
  const layer = useRef(null)
  const handlers = useRef({ onOpenCase, onOpenArea })
  const [tilesFailed, setTilesFailed] = useState(false)

  // Markers call the newest handlers without being rebuilt when they change.
  useEffect(() => {
    handlers.current = { onOpenCase, onOpenArea }
  }, [onOpenCase, onOpenArea])

  useEffect(() => {
    // fadeAnimation off: in testing, the first tiles loaded but stayed at
    // opacity 0 because Leaflet's frame-driven fade-in never completed. Tiles
    // now show as soon as they arrive.
    const instance = L.map(container.current, { center: KELANTAN, zoom: 9, fadeAnimation: false })
    L.tileLayer(TILE_URL, { attribution: ATTRIBUTION, maxZoom: 18 })
      .on('tileerror', () => setTilesFailed(true))
      .addTo(instance)
    layer.current = L.layerGroup().addTo(instance)
    map.current = instance

    // Opening the case panel narrows this column; Leaflet has to be told.
    const resize = new ResizeObserver(() => instance.invalidateSize())
    resize.observe(container.current)
    return () => {
      resize.disconnect()
      instance.remove()
      map.current = null
    }
  }, [])

  useEffect(() => {
    const group = layer.current
    if (!group) return
    group.clearLayers()
    const bounds = []

    areas.forEach((area) => {
      const at = [Number(area.latitude), Number(area.longitude)]
      bounds.push(at)
      const label = `${area.name}: ${area.case_count} ${area.case_count === 1 ? 'case' : 'cases'}`
      L.marker(at, { icon: areaIcon(area), title: label, keyboard: true, zIndexOffset: LAYER[area.highest_band] || 0 })
        .bindTooltip(tooltip([label, 'Exact locations are held by the claiming organisation.']))
        .on('click', () => handlers.current.onOpenArea(area.name))
        .addTo(group)
    })

    points.forEach((point) => {
      const at = [Number(point.latitude), Number(point.longitude)]
      bounds.push(at)
      const lines = [
        `#${point.reference} · ${point.village}`,
        `${point.status_display}${point.score_total != null ? ` · score ${point.score_total}` : ''}`,
      ]
      if (point.precision === 'village') lines.push('Placed at the village centre — no household pin yet.')
      L.marker(at, {
        icon: pinIcon(point),
        title: `#${point.reference}`,
        keyboard: true,
        zIndexOffset: LAYER[point.priority_band] || 0,
      })
        .bindTooltip(tooltip(lines))
        .on('click', () => handlers.current.onOpenCase(point.id))
        .addTo(group)
    })

    if (bounds.length) map.current.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 })
  }, [points, areas])

  return (
    <div className="case-map">
      {tilesFailed && (
        <div className="banner banner--warning" role="status">
          <span className="body text-sm">
            <span className="title">Map background unavailable.</span> Case locations are still
            shown; the list view has every case.
          </span>
        </div>
      )}
      <div ref={container} className="case-map__canvas" aria-label="Map of visible cases" />
    </div>
  )
}

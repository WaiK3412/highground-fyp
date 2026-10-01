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

// Same tones as the queue's priority chips, keyed by class (classes-1.0).
const TONE = { 1: 'danger', 2: 'warning', 3: 'success' }
// Nearby markers overlap; the most urgent one is drawn on top.
const LAYER = { 1: 3000, 2: 2000, 3: 1000 }

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

function pinIcon(point, selected, isOfficer) {
  const tone = TONE[point.priority_class] || 'neutral'
  const ring = point.claimed_by_you ? ' ops-pin--ring' : ''
  const chosen = selected ? ' ops-pin--selected' : ''
  const hasDuplicate = isOfficer && point.has_open_duplicate
  const duplicate = hasDuplicate ? ' ops-pin--duplicate' : ''
  return L.divIcon({
    className: 'case-map__icon',
    html: `<span class="ops-pin ops-pin--${tone}${ring}${chosen}${duplicate}">${hasDuplicate ? '<span class="ops-pin__duplicate" aria-hidden="true">!</span>' : ''}</span>`,
    iconSize: [26, 26],
    // The teardrop is a rotated square; its tip sits below the centre.
    iconAnchor: [13, 31],
  })
}

function areaIcon(area) {
  const tone = TONE[area.highest_class] || 'neutral'
  const count = Number(area.case_count) || 0
  return L.divIcon({
    className: 'case-map__icon',
    html: `<span class="ops-marker ops-marker--${tone}">${count}</span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  })
}

/**
 * `children` is drawn over the map — the case popover — so the map stays in
 * view while a case is read, as on the design's command map (screen 10).
 */
export default function CaseMap({
  points,
  areas,
  isOfficer = false,
  selectedId,
  onOpenCase,
  onOpenArea,
  onMapClick,
  children,
}) {
  const container = useRef(null)
  const map = useRef(null)
  const layer = useRef(null)
  const handlers = useRef({ onOpenCase, onOpenArea, onMapClick })
  const [tilesFailed, setTilesFailed] = useState(false)
  const [legendOpen, setLegendOpen] = useState(false)

  // Markers call the newest handlers without being rebuilt when they change.
  useEffect(() => {
    handlers.current = { onOpenCase, onOpenArea, onMapClick }
  }, [onOpenCase, onOpenArea, onMapClick])

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
    // A click on the map itself (markers do not bubble to it) dismisses the popover.
    instance.on('click', () => handlers.current.onMapClick?.())

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

    areas.forEach((area) => {
      const at = [Number(area.latitude), Number(area.longitude)]
      const label = `${area.name}: ${area.case_count} ${area.case_count === 1 ? 'case' : 'cases'}`
      L.marker(at, { icon: areaIcon(area), title: label, keyboard: true, zIndexOffset: LAYER[area.highest_class] || 0 })
        .bindTooltip(tooltip([label, 'Exact locations are held by the claiming organisation.']))
        .on('click', () => handlers.current.onOpenArea(area.name))
        .addTo(group)
    })

    points.forEach((point) => {
      const at = [Number(point.latitude), Number(point.longitude)]
      const lines = [
        `#${point.reference} · ${point.village}`,
        `${point.status_display}${point.priority_label ? ` · ${point.priority_label}` : ''}`,
      ]
      if (point.precision === 'village') lines.push('Placed at the village centre — no household pin yet.')
      const hasDuplicate = isOfficer && point.has_open_duplicate
      if (hasDuplicate) lines.push('Possible duplicate — officer review needed.')
      L.marker(at, {
        icon: pinIcon(point, point.id === selectedId, isOfficer),
        title: `#${point.reference}${hasDuplicate ? ' · Possible duplicate' : ''}`,
        keyboard: true,
        // The selected pin rises above everything else.
        zIndexOffset: point.id === selectedId ? 5000 : LAYER[point.priority_class] || 0,
      })
        .bindTooltip(tooltip(lines))
        .on('click', () => handlers.current.onOpenCase(point.id))
        .addTo(group)
    })

  }, [points, areas, selectedId, isOfficer])

  // Fit to the markers when the data changes, not when a pin is selected, so
  // choosing a case never throws away the user's zoom.
  useEffect(() => {
    const bounds = [...areas, ...points].map((item) => [Number(item.latitude), Number(item.longitude)])
    if (bounds.length && map.current) map.current.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 })
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
      <div className="case-map__stage">
        <div ref={container} className="case-map__canvas" aria-label="Map of visible cases" />
        <div className="case-map__legend">
          <button
            type="button"
            className="case-map__legend-toggle"
            aria-expanded={legendOpen}
            aria-controls="case-map-legend-content"
            onClick={() => setLegendOpen((open) => !open)}
          >
            Map legend <span aria-hidden="true">{legendOpen ? '−' : '+'}</span>
          </button>
          <div id="case-map-legend-content" className="case-map__legend-body" hidden={!legendOpen}>
            <p className="case-map__legend-title">Priority class</p>
            {[
              ['danger', '1 Health-critical'],
              ['warning', '2 At risk'],
              ['success', '3 Standard'],
              ['neutral', 'Not yet classified'],
            ].map(([tone, label]) => (
              <div className="case-map__legend-row" key={tone}>
                <span className={`case-map__legend-pin case-map__legend-pin--${tone}`} aria-hidden="true" />
                <span>{label}</span>
              </div>
            ))}
            <p className="case-map__legend-title">Map symbols</p>
            <div className="case-map__legend-row">
              <span className="case-map__legend-pin case-map__legend-pin--neutral" aria-hidden="true" />
              <span>One case. A pin may sit at the village centre when no household pin is available.</span>
            </div>
            <div className="case-map__legend-row">
              <span className="case-map__legend-bubble" aria-hidden="true">3</span>
              <span>Village count. Colour shows the highest priority class in that group.</span>
            </div>
            <div className="case-map__legend-row">
              <span className="case-map__legend-ring" aria-hidden="true" />
              <span>Your organisation has claimed this case.</span>
            </div>
            {isOfficer && (
              <div className="case-map__legend-row">
                <span className="case-map__legend-duplicate" aria-hidden="true">!</span>
                <span>Possible duplicate. An officer must review the flag.</span>
              </div>
            )}
          </div>
        </div>
        {children}
      </div>
    </div>
  )
}

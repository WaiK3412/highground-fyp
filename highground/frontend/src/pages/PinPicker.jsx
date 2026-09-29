/**
 * Screen 05a's "Pin your home on the map" — optional, centred on the chosen
 * village.
 *
 * Optional on purpose: the village is the required location, so a map whose
 * tiles fail to load (OpenStreetMap's public server is best-effort) never
 * stops a household from asking for help. Same plain-Leaflet approach as
 * CaseMap.jsx: React owns the page, Leaflet owns only the element behind
 * `container`.
 *
 * Every way of placing the pin (tap, drag, "use my location", keyboard) goes
 * through `place`, which applies the same distance rule as the server.
 */

import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { pinProblem } from '../geo'

const TILE_URL = import.meta.env.VITE_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
// Close enough to pick out houses and roads, far enough to see the village.
const VILLAGE_ZOOM = 15

const HOME_ICON = L.divIcon({
  className: 'case-map__icon',
  html: '<span class="ops-pin ops-pin--selected ops-pin--home"></span>',
  iconSize: [26, 26],
  iconAnchor: [13, 31],
})

const GEO_ERRORS = {
  1: 'Location permission was refused. Tap the map to place the pin instead.',
  2: 'Your phone could not find its location. Tap the map to place the pin instead.',
  3: 'Finding your location took too long. Tap the map to place the pin instead.',
}

const round6 = (value) => Number(value.toFixed(6))

export default function PinPicker({ village, value, onChange }) {
  const container = useRef(null)
  const map = useRef(null)
  const marker = useRef(null)
  const latest = useRef({ village, value, onChange })
  const [tilesFailed, setTilesFailed] = useState(false)
  const [message, setMessage] = useState(null)
  const [locating, setLocating] = useState(false)

  useEffect(() => {
    latest.current = { village, value, onChange }
  }, [village, value, onChange])

  // The single entry point for a new pin; refuses one the server would refuse.
  const place = useRef((latitude, longitude) => {
    const { village: current, onChange: change } = latest.current
    const problem = pinProblem(current, latitude, longitude)
    if (problem) {
      setMessage(problem)
      return false
    }
    setMessage(null)
    change({ latitude: round6(latitude), longitude: round6(longitude) })
    return true
  })

  useEffect(() => {
    const instance = L.map(container.current, {
      center: [Number(latest.current.village.latitude), Number(latest.current.village.longitude)],
      zoom: VILLAGE_ZOOM,
      fadeAnimation: false,
    })
    L.tileLayer(TILE_URL, { attribution: ATTRIBUTION, maxZoom: 19 })
      .on('tileerror', () => setTilesFailed(true))
      .addTo(instance)
    instance.on('click', (event) => place.current(event.latlng.lat, event.latlng.lng))
    map.current = instance

    const resize = new ResizeObserver(() => instance.invalidateSize())
    resize.observe(container.current)
    return () => {
      resize.disconnect()
      instance.remove()
      map.current = null
      marker.current = null
    }
  }, [])

  // A different village moves the map there.
  useEffect(() => {
    map.current?.setView([Number(village.latitude), Number(village.longitude)], VILLAGE_ZOOM)
  }, [village.latitude, village.longitude])

  // Draw the pin the form holds; a rejected drag snaps back to it.
  useEffect(() => {
    const instance = map.current
    if (!instance) return
    if (!value) {
      marker.current?.remove()
      marker.current = null
      return
    }
    const at = [value.latitude, value.longitude]
    if (!marker.current) {
      marker.current = L.marker(at, {
        icon: HOME_ICON, draggable: true, keyboard: true, title: 'Your home',
      })
        .on('dragend', (event) => {
          const moved = event.target.getLatLng()
          if (!place.current(moved.lat, moved.lng)) {
            const kept = latest.current.value
            event.target.setLatLng([kept.latitude, kept.longitude])
          }
        })
        .addTo(instance)
    } else {
      marker.current.setLatLng(at)
    }
  }, [value])

  function locateMe() {
    if (!navigator.geolocation) {
      setMessage('This browser cannot share its location. Tap the map to place the pin instead.')
      return
    }
    setLocating(true)
    setMessage(null)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false)
        const { latitude, longitude } = position.coords
        if (place.current(latitude, longitude)) map.current?.setView([latitude, longitude], 17)
      },
      (error) => {
        setLocating(false)
        setMessage(GEO_ERRORS[error.code] || GEO_ERRORS[2])
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    )
  }

  // For keyboard users: pan with the arrow keys, then drop the pin in the middle.
  function pinAtCentre() {
    const centre = map.current?.getCenter()
    if (centre) place.current(centre.lat, centre.lng)
  }

  return (
    <div className="field">
      <label id="pin-picker-label">
        Pin your home on the map <span className="text-muted">(optional)</span>
      </label>
      <div className="pin-picker">
        <div
          ref={container}
          className="pin-picker__canvas"
          role="application"
          aria-labelledby="pin-picker-label"
          aria-describedby="pin-picker-help"
        />
        <button
          type="button"
          className="btn btn--secondary btn--sm pin-picker__locate"
          onClick={locateMe}
          disabled={locating}
        >
          {locating ? 'Finding you…' : 'Use my current location'}
        </button>
      </div>
      <span className="help" id="pin-picker-help">
        Tap the map to drop the pin on your house, or drag it to adjust. Using a keyboard? Move the map
        with the arrow keys, then choose &ldquo;Pin the centre of the map&rdquo;.
      </span>
      <div className="row" style={{ gap: '0.8rem', flexWrap: 'wrap' }}>
        <button type="button" className="btn btn--ghost btn--sm" onClick={pinAtCentre}>
          Pin the centre of the map
        </button>
        {value && (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => {
              setMessage(null)
              onChange(null)
            }}
          >
            Remove pin
          </button>
        )}
      </div>
      {message && (
        <p className="help" role="alert" style={{ color: 'var(--danger-600)' }}>
          {message}
        </p>
      )}
      {tilesFailed && (
        <p className="help" role="status">
          The map background could not load. You can still continue without a pin — your village will be
          used.
        </p>
      )}
    </div>
  )
}

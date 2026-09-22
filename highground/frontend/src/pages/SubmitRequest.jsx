/**
 * Screens 05a · 05 · 05b · 05c · 05d — the five-step submit wizard (FR3).
 *
 * Ported from the frozen design contract. Two deliberate departures, both
 * agreed before building:
 *
 *   1. Step 1's map pin-drop is deferred. The design asks for a Leaflet
 *      pin, but a tile fetch that fails live is a grey box in front of an
 *      examiner, so location is captured as a controlled village (a coded
 *      area from /api/locations/) plus address text, and latitude/longitude
 *      are left null. The case is mapped at its village's centre point.
 *      The pin's privacy banner went with it — it promises something about
 *      "your exact pin" that this build does not yet collect.
 *
 *   2. Step 4 holds the chosen photos in state and previews them. On submit,
 *      api.createCase switches the request to multipart and Django stores up
 *      to five validated JPEG, PNG or WebP files through CasePhoto.file_path.
 *
 * All answers live in this component until step 5. There are no drafts and
 * no partial saves: the design's final step reviews the whole request before
 * anything is sent, which only works if nothing was sent earlier.
 */

import { Fragment, useEffect, useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'

const STEPS = ['Household', 'Home & damage', 'Safety & needs', 'Photos', 'Review & submit']

// These values are the database's, not the screen's. Every `value` below has
// to match a TextChoices member in cases.models.CaseRecord, or the serializer
// rejects the request — the label is what the household reads, the value is
// what the scoring engine keys on.
const DAMAGE_CATEGORIES = [
  { value: 'cleanup', label: 'Cleanup', desc: 'Mud, debris and silt removal' },
  { value: 'repair', label: 'Repair', desc: 'Structural or utility damage' },
  { value: 'essential_items', label: 'Essential items', desc: 'Food, water, bedding, medicine' },
  { value: 'agriculture', label: 'Agriculture', desc: 'Crops, livestock or equipment' },
]

// `waterY` is the surface line in the house SVG's own coordinates: the floor
// is y=150 and the figure's head tops out at y=96, so the four levels read
// against the person standing in the room. 126 is the frozen design's own
// value for waist; the others are derived around it.
const FLOOD_DEPTHS = [
  { value: 'ankle', label: 'Below ankle', desc: 'under 0.3 m', waterY: 142 },
  { value: 'knee', label: 'Knee height', desc: '0.3 to 0.5 m', waterY: 134 },
  { value: 'waist', label: 'Waist height', desc: '0.5 to 1 m indoors', waterY: 126 },
  { value: 'above_head', label: 'Above head', desc: 'more than 1 m', waterY: 94 },
]

const LIVEABILITY = [
  { value: 'liveable', label: 'Yes — we can stay here' },
  { value: 'partial', label: 'Partially — some rooms unusable' },
  { value: 'unliveable', label: 'No — we cannot stay here' },
]

const ACCESS_LEVELS = [
  { value: 'normal', label: 'Yes — normal access' },
  { value: 'four_wd', label: 'Only high vehicles / 4x4' },
  { value: 'foot', label: 'On foot only' },
  { value: 'cut_off', label: 'Completely cut off' },
]

// Wording is the frozen design's, verbatim (design-prototype-v2 screen 05b). The
// last option deliberately says "call 999 first": HighGround runs alongside the
// emergency services, it does not stand in for them.
const URGENCY = [
  { value: 'none', label: 'No safety concerns', desc: 'Everyone is safe and well' },
  {
    value: 'health_risk',
    label: 'Health concern',
    desc: 'Damp or mould exposure, minor illness, hygiene risk',
  },
  {
    value: 'medical_disrupted',
    label: 'Medical needs disrupted',
    desc: 'Medication, medical equipment or ongoing treatment affected by the flood',
  },
  {
    value: 'urgent',
    label: 'Someone needs urgent medical attention',
    desc: 'We will flag this to the district office — but call 999 first',
  },
]

const VULNERABILITY_FLAGS = [
  { value: 'elderly', label: 'Elderly members (60+)' },
  { value: 'child_under_5', label: 'Children under 5' },
  { value: 'disability', label: 'Members with medical needs or disability' },
  { value: 'single_parent', label: 'Single-parent household' },
]

const NEEDS_FLAGS = [
  { value: 'food', label: 'Food' },
  { value: 'water', label: 'Safe drinking water' },
  { value: 'hygiene', label: 'Hygiene items' },
  { value: 'bedding', label: 'Bedding & clothing' },
  { value: 'medicine', label: 'Medicine' },
  { value: 'baby_supplies', label: 'Baby supplies' },
]

const MAX_PHOTOS = 5

const PATHS = {
  logo: 'M2.5 12.5L4 11.5 12 5 20 11.5 21.5 12.5 M3 16q3-2 6 0t6 0t6 0 M3 19.5q3-2 6 0t6 0t6 0',
  home: 'M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75',
  plus: 'M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m3.75 9v6m3-3H9m1.5-12H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z',
  folder: 'M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z',
  bell: 'M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0',
  heart: 'M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z',
  user: 'M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z',
  arrow: 'M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3',
  camera: 'M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z',
  info: 'M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z',
  warning: 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z',
}

function Icon({ path, strokeWidth = 1.5, style }) {
  return (
    <svg fill="none" viewBox="0 0 24 24" strokeWidth={strokeWidth} stroke="currentColor" style={style}>
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  )
}

function Required() {
  return <span className="required">*</span>
}

function Stepper({ current }) {
  return (
    <div className="card card--flat" style={{ marginBottom: '2.4rem', padding: '1.6rem 2.4rem' }}>
      <div className="stepper">
        {STEPS.map((label, index) => {
          const state = index === current ? ' step--active' : index < current ? ' step--done' : ''
          return (
            <Fragment key={label}>
              <div className={`step${state}`}>
                <span className="step__dot">{index + 1}</span>
                <span className="step__label">{label}</span>
              </div>
              {index < STEPS.length - 1 && <span className="step__line" />}
            </Fragment>
          )
        })}
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- step 1 */

function StepHousehold({ data, set, villages, onRetryVillages }) {
  return (
    <>
      <div className="card" style={{ marginBottom: '2.4rem' }}>
        <h3 style={{ marginBottom: '0.4rem' }}>Who needs help?</h3>
        <p className="text-sm text-muted" style={{ marginBottom: '2.4rem' }}>
          We use this to contact you about your case.
        </p>

        <div className="stack" style={{ gap: '2.4rem' }}>
          <div className="input-group">
            <div className="field">
              <label>
                Full name <Required />
              </label>
              <input
                className="input"
                type="text"
                value={data.full_name}
                onChange={(e) => set({ full_name: e.target.value })}
              />
            </div>
            <div className="field">
              <label>
                Household members <Required />
              </label>
              <select
                className="input"
                value={data.household_size}
                onChange={(e) => set({ household_size: Number(e.target.value) })}
              >
                {Array.from({ length: 15 }, (_, i) => i + 1).map((n) => (
                  <option key={n} value={n}>
                    {n} {n === 1 ? 'person' : 'people'}
                  </option>
                ))}
              </select>
              <span className="help">Everyone currently living in the home.</span>
            </div>
          </div>

          <div className="input-group">
            <div className="field">
              <label>
                Mobile number <Required />
              </label>
              <input
                className="input"
                type="text"
                value={data.phone}
                onChange={(e) => set({ phone: e.target.value })}
                placeholder="012-345 6789"
              />
            </div>
            <div className="field">
              <label>
                Alternative contact <span className="text-muted">(optional)</span>
              </label>
              <input
                className="input"
                type="text"
                value={data.alt_contact}
                onChange={(e) => set({ alt_contact: e.target.value })}
                placeholder="A neighbour or relative we can call"
              />
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '2.4rem' }}>
        <h3 style={{ marginBottom: '0.4rem' }}>Where is your home?</h3>
        <p className="text-sm text-muted" style={{ marginBottom: '2.4rem' }}>
          Kampung addresses can be hard to find — a nearby landmark helps teams reach you faster.
        </p>

        <div className="input-group">
          <div className="field">
            <label>
              Village / area <Required />
            </label>
            <select
              className="input"
              value={data.location_code}
              onChange={(e) => set({ location_code: e.target.value })}
              disabled={villages.loading || Boolean(villages.error)}
            >
              <option value="">{villages.loading ? 'Loading villages…' : 'Choose your village…'}</option>
              {byDistrict(villages.rows).map(([district, rows]) => (
                <optgroup key={district} label={district}>
                  {rows.map((v) => (
                    <option key={v.code} value={v.code}>
                      {v.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            {villages.error ? (
              <p className="help" role="alert" style={{ color: 'var(--danger-600)' }}>
                Couldn&apos;t load villages.{' '}
                <button
                  type="button"
                  onClick={onRetryVillages}
                  style={{ background: 'none', border: 0, padding: 0, color: 'inherit', textDecoration: 'underline', cursor: 'pointer', font: 'inherit' }}
                >
                  Try again
                </button>
              </p>
            ) : (
              <p className="help">Not listed? Choose the nearest village and describe the place below.</p>
            )}
          </div>
          <div className="field">
            <label>
              Address or landmark <Required />
            </label>
            <input
              className="input"
              type="text"
              value={data.address}
              onChange={(e) => set({ address: e.target.value })}
              placeholder="No. 14, Jalan Masjid, near the surau"
            />
            <span className="help">Road, house number, or a nearby landmark (masjid, balai raya, school).</span>
          </div>
        </div>
      </div>
    </>
  )
}

/* The design guide's headline motif — "rising water: how high did the water
   get?". The house is the frozen design's SVG; the only thing this adds is
   moving the waterline with the answer, which is what makes it an input
   rather than a picture. Water is withheld until a depth is chosen, so the
   fill is a response to the household rather than a default reading. */
function DepthHouse({ waterY }) {
  const crest = waterY - 4
  const wave =
    `M10 ${waterY} Q 22 ${crest} 34 ${waterY} T 58 ${waterY} T 82 ${waterY} T 106 ${waterY} ` +
    `T 130 ${waterY} T 154 ${waterY} T 178 ${waterY} T 202 ${waterY} T 226 ${waterY} ` +
    `L 230 ${waterY} L 230 150 L 10 150 Z`

  return (
    <div className="depth-picker__house">
      <svg viewBox="0 0 240 170" fill="none" aria-hidden="true">
        <defs>
          <linearGradient id="depth-water" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#8AD5DB" stopOpacity="0.85" />
            <stop offset="1" stopColor="#2D9AA3" stopOpacity="0.9" />
          </linearGradient>
        </defs>
        <polygon points="38,60 120,16 202,60" fill="#F2EEE7" stroke="#A8A099" strokeWidth="2" strokeLinejoin="round" />
        <rect x="50" y="60" width="140" height="90" fill="#FFFFFF" stroke="#A8A099" strokeWidth="2" />
        <rect x="80" y="105" width="26" height="45" fill="#F2EEE7" stroke="#A8A099" strokeWidth="2" />
        <rect x="130" y="85" width="32" height="26" fill="#F3FAFA" stroke="#A8A099" strokeWidth="2" />
        <circle cx="218" cy="102" r="6" stroke="#746D66" strokeWidth="2" />
        <line x1="218" y1="108" x2="218" y2="134" stroke="#746D66" strokeWidth="2" />
        <line x1="218" y1="116" x2="210" y2="126" stroke="#746D66" strokeWidth="2" />
        <line x1="218" y1="116" x2="226" y2="126" stroke="#746D66" strokeWidth="2" />
        <line x1="218" y1="134" x2="212" y2="150" stroke="#746D66" strokeWidth="2" />
        <line x1="218" y1="134" x2="224" y2="150" stroke="#746D66" strokeWidth="2" />
        <line x1="10" y1="150" x2="230" y2="150" stroke="#746D66" strokeWidth="2" />
        {waterY != null && (
          <>
            <path d={wave} fill="url(#depth-water)" />
            <line x1="10" y1={waterY} x2="230" y2={waterY} stroke="#155E63" strokeWidth="1.5" strokeDasharray="5 4" />
          </>
        )}
      </svg>
    </div>
  )
}

/* ---------------------------------------------------------------- step 2 */

function StepDamage({ data, set }) {
  return (
    <>
      <div className="card" style={{ marginBottom: '2.4rem' }}>
        <h3 style={{ marginBottom: '0.4rem' }}>What kind of help do you need?</h3>
        <p className="text-sm text-muted" style={{ marginBottom: '2.4rem' }}>
          Pick the closest match. An officer will confirm the details.
        </p>

        <div className="stack" style={{ gap: '1.2rem' }}>
          {DAMAGE_CATEGORIES.map((option) => (
            <label
              key={option.value}
              className={`radio-card${data.damage_category === option.value ? ' radio-card--selected' : ''}`}
              style={{ alignItems: 'center', cursor: 'pointer' }}
            >
              <input
                type="radio"
                name="damage_category"
                checked={data.damage_category === option.value}
                onChange={() => set({ damage_category: option.value })}
                style={{ width: '1.8rem', height: '1.8rem', accentColor: 'var(--teal-700)' }}
              />
              <span>
                <span className="title">{option.label}</span>
                <span className="desc"> — {option.desc}</span>
              </span>
            </label>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginBottom: '2.4rem' }}>
        <div className="stack" style={{ gap: '2.4rem' }}>
          <div className="field">
            <label>
              Describe the damage and what you need <Required />
            </label>
            <textarea
              className="input"
              rows={5}
              value={data.description}
              onChange={(e) => set({ description: e.target.value })}
              placeholder="e.g. Floodwater reached 1 metre inside the house. Thick mud in every room, damaged furniture needs removal. We have two elderly family members and cannot do the heavy cleanup ourselves."
            />
          </div>

          <div className="field">
            <label>
              How high did the floodwater reach inside your home? <Required />
            </label>
            <div className="depth-picker">
              <DepthHouse waterY={FLOOD_DEPTHS.find((o) => o.value === data.flood_depth)?.waterY ?? null} />
              <div className="depth-picker__options">
              {FLOOD_DEPTHS.map((option) => (
                <label
                  key={option.value}
                  className={`depth-option${data.flood_depth === option.value ? ' depth-option--selected' : ''}`}
                  style={{ cursor: 'pointer' }}
                >
                  <input
                    type="radio"
                    name="flood_depth"
                    checked={data.flood_depth === option.value}
                    onChange={() => set({ flood_depth: option.value })}
                  />
                  <span>
                    <span className="title">{option.label}</span> <span className="desc">— {option.desc}</span>
                  </span>
                </label>
              ))}
              </div>
            </div>
          </div>

          <div className="input-group">
            <div className="field">
              <label>
                Is your home currently liveable? <Required />
              </label>
              <select
                className="input"
                value={data.liveability}
                onChange={(e) => set({ liveability: e.target.value })}
              >
                {LIVEABILITY.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>
                Can vehicles currently reach your home? <Required />
              </label>
              <select
                className="input"
                value={data.access_level}
                onChange={(e) => set({ access_level: e.target.value })}
              >
                {ACCESS_LEVELS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

/* ---------------------------------------------------------------- step 3 */

function StepNeeds({ data, set }) {
  const toggle = (key, value) => {
    const current = data[key]
    set({ [key]: current.includes(value) ? current.filter((v) => v !== value) : [...current, value] })
  }

  return (
    <>
      <div className="banner banner--danger" style={{ marginBottom: '2.4rem' }}>
        <Icon path={PATHS.warning} />
        <span className="body text-sm">
          <span className="title">In danger right now? Call 999.</span>
          <br />
          HighGround coordinates recovery help — it is not an emergency rescue service. If anyone is
          in life-threatening danger, call 999 or the Civil Defence Force (APM) immediately.
        </span>
      </div>

      <div className="card" style={{ marginBottom: '2.4rem' }}>
        <h3 style={{ marginBottom: '0.4rem' }}>Safety and urgent needs</h3>
        <p className="text-sm text-muted" style={{ marginBottom: '2.4rem' }}>
          This is what decides how quickly your case is looked at.
        </p>

        <div className="stack" style={{ gap: '2.4rem' }}>
          <div className="field">
            <label>
              Is anyone&rsquo;s health or safety affected? <Required />
            </label>
            <div className="stack" style={{ gap: '1.2rem' }}>
              {URGENCY.map((option) => (
                <label
                  key={option.value}
                  className={`radio-card${data.urgency === option.value ? ' radio-card--selected' : ''}`}
                  style={{ alignItems: 'center', cursor: 'pointer' }}
                >
                  <input
                    type="radio"
                    name="urgency"
                    checked={data.urgency === option.value}
                    onChange={() => set({ urgency: option.value })}
                    style={{ width: '1.8rem', height: '1.8rem', accentColor: 'var(--teal-700)' }}
                  />
                  <div>
                    <div className="title">{option.label}</div>
                    <div className="desc">{option.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="field">
            <label>
              Household vulnerability{' '}
              <span className="text-muted" style={{ fontWeight: 400 }}>
                (tick all that apply — this helps us prioritise)
              </span>
            </label>
            <div className="stack" style={{ gap: '0.8rem' }}>
              {VULNERABILITY_FLAGS.map((option) => (
                <label key={option.value} className="check-row" style={{ cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={data.vulnerability_flags.includes(option.value)}
                    onChange={() => toggle('vulnerability_flags', option.value)}
                  />{' '}
                  {option.label}
                </label>
              ))}
            </div>
          </div>

          <div className="field">
            <label>
              Has your household run out of any essentials?{' '}
              <span className="text-muted" style={{ fontWeight: 400 }}>
                (tick anything you can&rsquo;t get right now)
              </span>
            </label>
            <div className="stack" style={{ gap: '0.8rem' }}>
              {NEEDS_FLAGS.map((option) => (
                <label key={option.value} className="check-row" style={{ cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={data.needs_flags.includes(option.value)}
                    onChange={() => toggle('needs_flags', option.value)}
                  />{' '}
                  {option.label}
                </label>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

/* ---------------------------------------------------------------- step 4 */

function StepPhotos({ data, set }) {
  function addFiles(event) {
    const chosen = Array.from(event.target.files || [])
    set({ photos: [...data.photos, ...chosen].slice(0, MAX_PHOTOS) })
    // Clear the input so picking the same file twice still fires a change.
    event.target.value = ''
  }

  return (
    <div className="card" style={{ marginBottom: '2.4rem' }}>
      <h3 style={{ marginBottom: '0.4rem' }}>Photos of the damage</h3>
      <p className="text-sm text-muted" style={{ marginBottom: '2.4rem' }}>
        Optional, but photos help an officer verify your case faster. Up to {MAX_PHOTOS}.
      </p>

      <div className="stack" style={{ gap: '2.4rem' }}>
        <div className="field">
          <label className="btn btn--secondary" style={{ cursor: 'pointer', alignSelf: 'flex-start' }}>
            <Icon path={PATHS.camera} />
            Choose photos
            <input
              type="file"
              accept="image/*"
              multiple
              onChange={addFiles}
              style={{ display: 'none' }}
              disabled={data.photos.length >= MAX_PHOTOS}
            />
          </label>
          <span className="help">
            {data.photos.length} of {MAX_PHOTOS} selected. JPEG, PNG or WebP, up to 5 MB each.
          </span>
        </div>

        {data.photos.length > 0 && (
          <div className="row" style={{ flexWrap: 'wrap', gap: '1.2rem' }}>
            {data.photos.map((file, index) => (
              <div
                key={`${file.name}-${index}`}
                style={{
                  width: '14rem',
                  border: '1px solid var(--grey-200)',
                  borderRadius: 'var(--radius-md)',
                  overflow: 'hidden',
                }}
              >
                <img
                  src={URL.createObjectURL(file)}
                  alt={file.name}
                  style={{ width: '100%', height: '10rem', objectFit: 'cover', display: 'block' }}
                />
                <button
                  className="btn btn--ghost btn--sm btn--full"
                  onClick={() => set({ photos: data.photos.filter((_, i) => i !== index) })}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- step 5 */

// The form lists villages under their district, as the location table does.
function byDistrict(rows) {
  const groups = new Map()
  rows.forEach((row) => {
    if (!groups.has(row.district)) groups.set(row.district, [])
    groups.get(row.district).push(row)
  })
  return [...groups.entries()]
}

function villageLabel(rows, code) {
  const village = rows.find((row) => row.code === code)
  return village ? `${village.name}, ${village.district}` : ''
}

function labelFor(list, value) {
  return list.find((o) => o.value === value)?.label ?? '—'
}

function StepReview({ data, goTo, villages }) {
  const flagLabels = (list, values) =>
    values.length ? values.map((v) => labelFor(list, v)).join(' · ') : 'None'

  const section = (title, step, rows) => (
    <div className="card" style={{ marginBottom: '2.4rem' }}>
      <div className="row--between" style={{ marginBottom: '1.6rem' }}>
        <h3>{title}</h3>
        <button className="btn btn--ghost btn--sm" onClick={() => goTo(step)}>
          Edit
        </button>
      </div>
      <dl className="kv">
        {rows.map(([term, value]) => (
          <Fragment key={term}>
            <dt>{term}</dt>
            <dd>{value || '—'}</dd>
          </Fragment>
        ))}
      </dl>
    </div>
  )

  return (
    <>
      {section('Household', 0, [
        ['Full name', data.full_name],
        ['Household members', `${data.household_size}`],
        ['Mobile number', data.phone],
        ['Alternative contact', data.alt_contact],
        ['Village / area', villageLabel(villages.rows, data.location_code)],
        ['Address or landmark', data.address],
      ])}

      {section('Home & damage', 1, [
        ['Type of help', labelFor(DAMAGE_CATEGORIES, data.damage_category)],
        ['Description', data.description],
        ['Floodwater depth', labelFor(FLOOD_DEPTHS, data.flood_depth)],
        ['Liveable', labelFor(LIVEABILITY, data.liveability)],
        ['Vehicle access', labelFor(ACCESS_LEVELS, data.access_level)],
      ])}

      {section('Safety & needs', 2, [
        ['Health or safety', labelFor(URGENCY, data.urgency)],
        ['Vulnerability', flagLabels(VULNERABILITY_FLAGS, data.vulnerability_flags)],
        ['Essentials needed', flagLabels(NEEDS_FLAGS, data.needs_flags)],
      ])}

      {section('Photos', 3, [['Selected', data.photos.length ? `${data.photos.length} photo(s)` : 'None']])}

      <div className="banner banner--info" style={{ marginBottom: '2.4rem' }}>
        <Icon path={PATHS.info} />
        <span className="body text-sm">
          <span className="title">What happens next.</span> An officer checks your request before it is
          scored and passed to relief organisations.
        </span>
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ shell */

// Each step names the fields it will not let you leave without. Kept beside
// the steps rather than inside them so "can I continue?" is answerable
// without rendering anything.
const REQUIRED_BY_STEP = [
  ['full_name', 'phone', 'location_code', 'address'],
  ['damage_category', 'description', 'flood_depth', 'liveability', 'access_level'],
  ['urgency'],
  [],
  [],
]

export default function SubmitRequest({ user, onLogout, onSubmitted, onCancel }) {
  useDocumentTitle('Submit a request')

  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [data, setData] = useState({
    full_name: user.full_name || '',
    phone: user.phone || '',
    alt_contact: '',
    household_size: 1,
    location_code: '',
    address: '',
    damage_category: '',
    description: '',
    flood_depth: '',
    liveability: 'liveable',
    access_level: 'normal',
    urgency: 'none',
    vulnerability_flags: [],
    needs_flags: [],
    photos: [],
  })

  const set = (patch) => setData((current) => ({ ...current, ...patch }))

  // Villages come from the controlled location table, not a list in this file.
  const [villages, setVillages] = useState({ rows: [], loading: true, error: null })
  const [villagesAttempt, setVillagesAttempt] = useState(0)
  useEffect(() => {
    let cancelled = false
    api
      .locations()
      .then((rows) => !cancelled && setVillages({ rows, loading: false, error: null }))
      .catch((err) => !cancelled && setVillages({ rows: [], loading: false, error: err.message }))
    return () => {
      cancelled = true
    }
  }, [villagesAttempt])
  function retryVillages() {
    setVillages({ rows: [], loading: true, error: null })
    setVillagesAttempt((n) => n + 1)
  }

  const missing = REQUIRED_BY_STEP[step].filter((field) => {
    const value = data[field]
    return typeof value === 'string' ? value.trim() === '' : value == null
  })
  const canContinue = missing.length === 0

  async function submit() {
    setError(null)
    setBusy(true)
    try {
      await api.primeCsrf()
      // Only the fields the case record owns. full_name, phone and alt_contact
      // are collected by the design but live on the user account, not the case.
      // Photos go as a second argument: they cannot travel inside JSON, so the
      // client switches the whole request to multipart when any are attached.
      const created = await api.createCase({
        location_code: data.location_code,
        address: data.address,
        household_size: data.household_size,
        damage_category: data.damage_category,
        description: data.description,
        flood_depth: data.flood_depth,
        liveability: data.liveability,
        access_level: data.access_level,
        urgency: data.urgency,
        vulnerability_flags: data.vulnerability_flags,
        needs_flags: data.needs_flags,
      }, data.photos)
      onSubmitted(created)
    } catch (err) {
      // DRF answers a refused field with {field: [message]}; show that message
      // (e.g. a village retired while the form was open), not a generic one.
      setError(Object.values(err.fields || {}).flat()[0] || err.message)
      setBusy(false)
    }
  }

  const initials = (user.full_name || '?')
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')

  return (
    <div className="app">
      <aside className="sidebar">
        <a className="logo" href="#recovery" onClick={(e) => e.preventDefault()}>
          <span className="logo__mark">
            <Icon path={PATHS.logo} strokeWidth={2} />
          </span>
          <span>
            <span className="logo__name">HighGround</span>
            <br />
            <span className="logo__role">Resident</span>
          </span>
        </a>

        <nav className="side-nav">
          <a href="#recovery" onClick={(e) => { e.preventDefault(); onCancel() }}>
            <Icon path={PATHS.home} />
            My Recovery
          </a>
          <a href="#submit" className="active" onClick={(e) => e.preventDefault()}>
            <Icon path={PATHS.plus} />
            Submit a request
          </a>
          <a href="#cases" onClick={(e) => e.preventDefault()}>
            <Icon path={PATHS.folder} />
            My cases
          </a>
          <a href="#notifications" onClick={(e) => e.preventDefault()}>
            <Icon path={PATHS.bell} />
            Notifications
          </a>

          <span className="side-nav__label">Community</span>
          <span className="side-nav__item side-nav__item--soon" aria-disabled="true">
            <Icon path={PATHS.heart} />
            Pledge supplies <span className="side-nav__soon-tag">Coming soon</span>
          </span>

          <span className="side-nav__label">Account</span>
          <a href="#profile" onClick={(e) => e.preventDefault()}>
            <Icon path={PATHS.user} />
            My profile
          </a>
        </nav>

        <div className="sidebar__user">
          <span className="avatar">{initials}</span>
          <div>
            <div className="text-sm text-strong">{user.full_name}</div>
            <button
              className="text-xs text-muted"
              onClick={onLogout}
              style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer', font: 'inherit' }}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <main className="main" style={{ maxWidth: '92rem' }}>
        <div className="page-header">
          <div>
            <h1>Submit an aid request</h1>
            <p>
              Tell us who needs help and where to find you. Fields marked <Required /> are required.
            </p>
          </div>
        </div>

        <Stepper current={step} />

        {step === 0 && (
          <StepHousehold data={data} set={set} villages={villages} onRetryVillages={retryVillages} />
        )}
        {step === 1 && <StepDamage data={data} set={set} />}
        {step === 2 && <StepNeeds data={data} set={set} />}
        {step === 3 && <StepPhotos data={data} set={set} />}
        {step === 4 && <StepReview data={data} goTo={setStep} villages={villages} />}

        {error && (
          <div
            role="alert"
            style={{
              background: 'var(--danger-100)',
              color: 'var(--danger-600)',
              padding: '1.0rem 1.2rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: 'var(--fs-14)',
              fontWeight: 600,
              marginBottom: '2.4rem',
            }}
          >
            {error}
          </div>
        )}

        <div className="row--between">
          <button className="btn btn--secondary" onClick={step === 0 ? onCancel : () => setStep(step - 1)}>
            {step === 0 ? '← Cancel' : '← Back'}
          </button>

          <div className="row" style={{ gap: '1.6rem', alignItems: 'center' }}>
            <span className="text-sm text-muted">
              Step {step + 1} of {STEPS.length}
            </span>
            {step < STEPS.length - 1 ? (
              <button
                className="btn btn--primary"
                onClick={() => setStep(step + 1)}
                disabled={!canContinue}
                style={canContinue ? undefined : { opacity: 0.5, cursor: 'not-allowed' }}
                title={canContinue ? undefined : 'Fill in the required fields to continue'}
              >
                Continue
                <Icon path={PATHS.arrow} strokeWidth={2} />
              </button>
            ) : (
              <button
                className="btn btn--primary"
                onClick={submit}
                disabled={busy}
                style={busy ? { opacity: 0.5, cursor: 'not-allowed' } : undefined}
              >
                {busy ? 'Submitting…' : 'Submit request'}
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}

/**
 * Screen 18 — "How scoring works", read-only.
 *
 * Per GAPS C2 this is a T3 item: the rubric *editor* is designed but not built,
 * so this renders the published version rather than pretending to edit it. That
 * distinction is deliberate and stated on the page — a screen that looks
 * editable but silently does nothing is worse than one that says what it is.
 *
 * Criteria, weights and thresholds belong to the published rubric version.
 * Point bands remain explicit rules in scoring/engine.py; the API applies the
 * published weight before returning the values shown here.
 */

import { useEffect, useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'

// The stored keys are enum members ("medical_disrupted"); a page explaining the
// rules to a person should read as English.
const READABLE = {
  none: 'No safety concern',
  health_risk: 'Health risk present',
  medical_disrupted: 'Medical needs disrupted',
  urgent: 'Urgent medical or safety threat',
  elderly: 'Elderly member (60+)',
  child_under_5: 'Child under 5',
  disability: 'Member with a disability or medical need',
  single_parent: 'Single-parent household',
  normal: 'Normal vehicle access',
  four_wd: 'High vehicles or 4x4 only',
  foot: 'Reachable on foot only',
  cut_off: 'Completely cut off',
}

const humanise = (text) =>
  READABLE[text] || text.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())

export default function ScoringRules() {
  useDocumentTitle('How scoring works')
  const [rubric, setRubric] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    api
      .rubric()
      .then((data) => !cancelled && setRubric(data))
      .catch((err) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [])

  if (error) return <p className="text-sm text-muted">{error}</p>
  if (!rubric) return <p className="text-sm text-muted">Loading scoring rules…</p>

  const total = rubric.criteria.reduce((sum, c) => sum + c.weight, 0)
  const { high, medium } = rubric.thresholds
  const bands = [
    { key: 'high', chip: high, name: 'High priority', range: `Score ${high} and above` },
    { key: 'medium', chip: medium, name: 'Medium priority', range: `Score ${medium} to ${high - 1}` },
    { key: 'low', chip: medium - 1, name: 'Low priority', range: `Score ${medium - 1} and below` },
  ]

  return (
    <>
      <div className="page-header">
        <div>
          <h1>How scoring works</h1>
          <p>
            Rubric {rubric.label} — the rules every verified case is scored against. The six
            criteria total {total} points, so a score reads out of {total}.
          </p>
        </div>
      </div>

      {/* The score chip is a fixed-size circle, so it carries only the number;
          the band's name and range sit beside it, as on the design contract. */}
      <div className="row" style={{ gap: '3.2rem', flexWrap: 'wrap', marginBottom: '2.4rem' }}>
        {bands.map((band) => (
          <div className="row" key={band.key}>
            <span className={`score score--sm score--${band.key}`}>{band.chip}</span>
            <div>
              <div className="text-sm text-strong">{band.name}</div>
              <div className="text-xs text-muted">{band.range}</div>
            </div>
          </div>
        ))}
      </div>

      {rubric.criteria.map((criterion) => (
        <div className="card" style={{ marginBottom: '2.4rem' }} key={criterion.key}>
          <div className="row--between" style={{ marginBottom: '0.6rem' }}>
            <h3>{criterion.name}</h3>
            <span className="badge badge--new">up to {criterion.weight} points</span>
          </div>
          {criterion.rule_text && (
            <p className="text-sm text-muted" style={{ marginBottom: '1.6rem' }}>
              {criterion.rule_text}
            </p>
          )}
          {criterion.weight !== criterion.max_points && (
            <p className="text-xs text-muted" style={{ marginBottom: '1.2rem' }}>
              Severity values are capped at {criterion.max_points}, then scaled to this
              criterion&apos;s {criterion.weight}-point weight.
            </p>
          )}

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>What the household reported</th>
                  <th style={{ textAlign: 'right' }}>Severity value</th>
                </tr>
              </thead>
              <tbody>
                {criterion.bands.map((band) => (
                  <tr key={band.when}>
                    <td className="text-sm">{humanise(band.when)}</td>
                    <td className="text-sm text-strong" style={{ textAlign: 'right' }}>
                      {band.points}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      <div className="banner banner--info">
        <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z"
          />
        </svg>
        <span className="body text-sm">
          <span className="title">This page is read-only.</span> The criteria, weights and
          thresholds are stored as a versioned rubric, and every score records which version
          produced it. The engine adds each criterion&apos;s applicable severity values, caps them
          at the criterion scale, and scales that proportion to its weight. The point-band rules
          remain in the scoring engine. An editor is designed but not built.
        </span>
      </div>
    </>
  )
}

/** Screen 18 uses server classes-1.0 rules: first matching class, then submission order, without weights or points. */

import { useEffect, useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'

// Same tones as the queue's priority chips.
const CHIP = { 1: 'score--high', 2: 'score--medium', 3: 'score--low' }

export default function PriorityRules() {
  useDocumentTitle('How priority works')
  const [rules, setRules] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    api
      .priorityRules()
      .then((data) => !cancelled && setRules(data))
      .catch((err) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [])

  if (error) return <p className="text-sm text-muted">{error}</p>
  if (!rules) return <p className="text-sm text-muted">Loading priority rules…</p>

  return (
    <>
      <div className="page-header">
        <div>
          <h1>How priority works</h1>
          <p>
            Rules {rules.version}. {rules.order} Cases awaiting verification have no class yet and
            appear after every classified case.
          </p>
        </div>
      </div>

      {rules.classes.map((item) => (
        <div className="card mb-24" key={item.priority_class}>
          <div className="row" style={{ marginBottom: '0.8rem' }}>
            <span className={`score score--sm ${CHIP[item.priority_class]}`}>{item.priority_class}</span>
            <h3>{item.label}</h3>
          </div>
          <p className="text-sm" style={{ marginBottom: item.sources.length ? '1.2rem' : 0 }}>
            {item.rule}
          </p>
          {item.sources.length > 0 && (
            <>
              <div className="text-xs text-muted">Based on</div>
              <ul className="text-sm text-muted" style={{ margin: '0.4rem 0 0', paddingLeft: '1.6rem' }}>
                {item.sources.map((source) => (
                  <li key={source}>{source}</li>
                ))}
              </ul>
            </>
          )}
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
          <span className="title">This page is read-only.</span> The class is assigned once, when
          a district officer verifies the request, from the answers the household gave. Every case
          records the reasons for its class and the rules version that produced it. Emergencies go
          to 999 first; Health-critical means ongoing health needs the flood has put at risk.
        </span>
      </div>
    </>
  )
}

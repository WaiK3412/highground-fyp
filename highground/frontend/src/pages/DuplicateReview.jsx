/** Officer review of possible duplicate pairs (prototype screen 12). */
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'
import ResponderShell from './ResponderShell'

const PAGE_SIZE = 50 // Matches the API's configured pagination size.

function dateTime(value) {
  return value ? new Date(value).toLocaleString() : 'Unknown'
}

function classification(value) {
  return ({ match: 'Match signal', possible: 'Possible match', non_match: 'Below review threshold' })[value] || value
}

// rules-1.0 flags list the rules that fired; flags raised by the retired
// weighted engine (dup-1.1) still show the score they were raised with.
function flagSummary(flag) {
  if (flag.method === 'rules-1.0') return flag.matched_rules.map((rule) => rule.text).join(' · ')
  return `${flag.similarity_score}/100 · ${classification(flag.classification)} (retired weighted method)`
}

const CONFIRM_BLOCK = {
  active_case: 'An organisation is working on the newer case.',
  duplicate_chain: 'Other cases are already linked to the newer case.',
  stale_pair: 'The cases changed after this flag was created.',
  match_not_open: 'This flag has already been resolved.',
}

function accessMessage(error) {
  return error.status === 401 || error.status === 403
    ? 'Your officer access is unavailable. Sign in again or contact the district office.'
    : error.message
}

function CaseComparison({ item, older }) {
  return (
    <section className={`card duplicate-case ${older ? 'duplicate-case--older' : 'duplicate-case--newer'}`}>
      <div className="row--between">
        <span className={`badge ${older ? 'badge--verified' : 'badge--duplicate'}`}>
          {older ? 'Earlier case' : 'Newer case'}
        </span>
        <span className="text-xs text-muted">{item.status_display}</span>
      </div>
      <h3>#{item.reference}</h3>
      <p className="text-sm text-muted">{item.submitter_name} · submitted {dateTime(item.created_at)}</p>
      <p className="duplicate-case__description">{item.description}</p>
      <dl className="kv">
        <dt>Address</dt><dd>{item.address || 'Not provided'}</dd>
        <dt>Village</dt><dd>{item.village || 'Not recorded'}</dd>
        <dt>Contact</dt><dd>{item.submitter_phone || 'Not provided'}</dd>
        <dt>Damage</dt><dd>{item.damage_category_display}</dd>
        <dt>Help asked for</dt><dd>{item.jobs?.length ? item.jobs.map((job) => `${job.help_type_display} (${job.status_display.toLowerCase()})`).join(', ') : 'None recorded'}</dd>
        <dt>Household</dt><dd>{item.household_size} members</dd>
        <dt>Needs</dt><dd>{item.needs_flags?.join(', ') || 'None recorded'}</dd>
        <dt>Photos</dt><dd>{item.photo_count}</dd>
      </dl>
    </section>
  )
}

export default function DuplicateReview({ user, initialId, duplicateCount, onCountChange, onNavigate, onLogout }) {
  useDocumentTitle('Duplicate review')
  const [list, setList] = useState(null)
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState(null)
  const [selectedId, setSelectedId] = useState(initialId)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(Boolean(initialId))
  const [detailError, setDetailError] = useState(null)
  const [note, setNote] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)

  // A link from verification can name a pair beyond the first page.
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        let page = 1
        let data = await api.duplicates({ page })
        while (initialId && !data.results.some((row) => row.id === initialId) && data.next) {
          page += 1
          data = await api.duplicates({ page })
        }
        if (cancelled) return
        setList({ ...data, page })
        onCountChange(data.count)
        if (!initialId && data.results[0]) setDetailLoading(true)
        setSelectedId((id) => id || data.results[0]?.id || null)
      } catch (error) {
        if (!cancelled) {
          if (error.status === 401 || error.status === 403) {
            setList(null)
            setDetail(null)
            setSelectedId(null)
          }
          setListError(accessMessage(error))
        }
      } finally {
        if (!cancelled) setListLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [initialId, onCountChange, reloadKey])

  useEffect(() => {
    if (!selectedId) return undefined
    let cancelled = false
    api.duplicate(selectedId).then((data) => {
      if (!cancelled) setDetail(data)
    }).catch((error) => {
      if (!cancelled) {
        setDetail(null)
        if (error.status === 401 || error.status === 403) {
          setList(null)
          setSelectedId(null)
          onCountChange(null)
        }
        setDetailError(accessMessage(error))
      }
    }).finally(() => {
      if (!cancelled) setDetailLoading(false)
    })
    return () => { cancelled = true }
  }, [selectedId, reloadKey, onCountChange])

  async function changePage(page, select) {
    setListLoading(true)
    setListError(null)
    try {
      const data = await api.duplicates({ page })
      setList({ ...data, page })
      onCountChange(data.count)
      const row = select === 'last' ? data.results.at(-1) : data.results[0]
      setDetail(null)
      setDetailLoading(Boolean(row))
      setDetailError(null)
      setSelectedId(row?.id || null)
      setNote('')
      setConfirmOpen(false)
      setActionError(null)
      setNotice(null)
    } catch (error) {
      if (error.status === 401 || error.status === 403) {
        setList(null)
        setDetail(null)
        setSelectedId(null)
      }
      setListError(accessMessage(error))
    } finally {
      setListLoading(false)
    }
  }

  function selectPair(id) {
    if (id === selectedId) return
    setDetail(null)
    setDetailLoading(true)
    setDetailError(null)
    setSelectedId(id)
    setNote('')
    setConfirmOpen(false)
    setActionError(null)
    setNotice(null)
  }

  async function decide(decision) {
    if (!detail || busy) return
    setBusy(true)
    setActionError(null)
    setNotice(null)
    try {
      const result = await api.decideDuplicate(detail.id, decision, note.trim())
      setConfirmOpen(false)
      setDetail((current) => current && ({
        ...current, status: result.status, can_confirm: false,
        decided_by: result.decided_by, decided_at: result.decided_at,
      }))
      setNotice(
        result.status === 'confirmed'
          ? `#${result.newer_case.reference} was closed as a duplicate. The earlier case remains active.`
          : 'Flag dismissed. Refresh the newer case before verifying; another flag may still block it.',
      )
      setListLoading(true)
      setReloadKey((key) => key + 1)
    } catch (error) {
      setActionError(accessMessage(error))
      if (error.status === 401 || error.status === 403) {
        setList(null)
        setDetail(null)
        setSelectedId(null)
      }
      if (error.status === 409 || error.status === 404) {
        setListLoading(true)
        setReloadKey((key) => key + 1)
      }
    } finally {
      setBusy(false)
    }
  }

  const rows = list?.results || []
  const index = rows.findIndex((row) => row.id === selectedId)
  const hasPrevious = index > 0 || (index === 0 && !!list?.previous)
  const hasNext = (index >= 0 && index < rows.length - 1) || (index === rows.length - 1 && !!list?.next)
  function retry() {
    setListLoading(true)
    setListError(null)
    setDetailError(null)
    if (selectedId) setDetailLoading(true)
    setReloadKey((key) => key + 1)
  }
  function move(direction) {
    if (index < 0 || !list) return
    if (direction < 0 && index > 0) selectPair(rows[index - 1].id)
    else if (direction > 0 && index < rows.length - 1) selectPair(rows[index + 1].id)
    else if (direction < 0 && list.previous) changePage(list.page - 1, 'last')
    else if (direction > 0 && list.next) changePage(list.page + 1, 'first')
  }

  return (
    <ResponderShell user={user} active="duplicates" counts={{ duplicates: duplicateCount }} onNavigate={onNavigate} onLogout={onLogout}>
      <div className="page-header duplicate-review__header">
        <div>
          <h1>Duplicate review</h1>
          <p>
            {list ? `${list.count} open ${list.count === 1 ? 'pair' : 'pairs'}` : 'Loading possible duplicates'}
            {index >= 0 && list ? ` · reviewing pair ${(list.page - 1) * PAGE_SIZE + index + 1} of ${list.count}` : ''}
          </p>
        </div>
        <div className="row">
          <button className="btn btn--secondary btn--sm" disabled={!hasPrevious || listLoading} onClick={() => move(-1)}>← Previous pair</button>
          <button className="btn btn--secondary btn--sm" disabled={!hasNext || listLoading} onClick={() => move(1)}>Next pair →</button>
        </div>
      </div>

      <p className="text-sm text-muted duplicate-review__principle">A flag never closes a case automatically — an officer decides.</p>

      {listLoading && <p role="status">Loading possible duplicates…</p>}
      {listError && <div className="banner banner--warning" role="alert"><span className="body">{listError} <button className="btn btn--ghost btn--sm" onClick={retry}>Retry</button></span></div>}
      {!listLoading && !listError && list?.count === 0 && !selectedId && <p role="status">No possible duplicates awaiting review.</p>}

      {rows.length > 0 && (
        <div className="duplicate-review__pairs" aria-label="Open possible duplicate pairs">
          {rows.map((row) => (
            <button key={row.id} className={`duplicate-review__pair${row.id === selectedId ? ' duplicate-review__pair--selected' : ''}`} onClick={() => selectPair(row.id)}>
              #{row.case_a.reference} / #{row.case_b.reference} · {flagSummary(row)}
            </button>
          ))}
        </div>
      )}

      {detailLoading && <p role="status">Loading pair comparison…</p>}
      {detailError && <div className="banner banner--warning" role="alert"><span className="body">{detailError} <button className="btn btn--ghost btn--sm" onClick={retry}>Retry</button>{rows.length > 0 && <button className="btn btn--ghost btn--sm" onClick={() => selectPair(rows[0].id)}>Open first available pair</button>}</span></div>}
      {detail && !detailLoading && (
        <>
          {notice && <div className="banner banner--info" role="status"><span className="body">{notice}</span></div>}
          <div className="banner banner--warning duplicate-review__evidence">
            <span className="body">
              <span className="title">Flagged because: {flagSummary(detail)}</span>
              <br />Stored when the flag was raised. The current check below re-runs the same rules on today&apos;s case details, so it can differ.
            </span>
          </div>
          <section className="card duplicate-review__reasons">
            <h2>Current check · {detail.current_comparison.method}</h2>
            {detail.current_comparison.matched ? (
              <ul>
                {detail.current_comparison.reasons.map((reason) => (
                  <li key={reason.rule} className="text-sm">{reason.text}</li>
                ))}
              </ul>
            ) : (
              <p className="text-sm">No rule matches on the current details.</p>
            )}
            {/* What disagrees is shown beside what matches; it never decides the flag. */}
            {detail.current_comparison.contradictions.length > 0 && (
              <>
                <h3 className="text-sm text-strong">But these differ</h3>
                <ul>
                  {detail.current_comparison.contradictions.map((item) => (
                    <li key={item.rule} className="text-sm">{item.text}</li>
                  ))}
                </ul>
              </>
            )}
            <p className="text-xs text-muted">
              {detail.current_comparison.pin_distance_metres == null
                ? 'Pin distance: not available (one or both cases have no household pin).'
                : `Household pins are ${detail.current_comparison.pin_distance_metres} m apart.`}
            </p>
          </section>
          <div className="grid-2 duplicate-review__cases">
            <CaseComparison item={detail.case_a} older />
            <CaseComparison item={detail.case_b} older={false} />
          </div>
          <section className="card duplicate-review__decision">
            <h2>Officer decision</h2>
            {detail.status === 'open' ? (
              <>
                <p className="text-sm text-muted">Confirming closes #{detail.case_b.reference} as a duplicate of #{detail.case_a.reference}; any type of help only the newer request asked for is added to #{detail.case_a.reference}, and both records and their history remain. Dismissing keeps the cases separate. If the older request already finished a type of help and the household needs it again, dismiss instead.</p>
                <label className="field" htmlFor="duplicate-note">Optional internal note
                  <textarea id="duplicate-note" className="input" maxLength={1000} rows={3} value={note} onChange={(event) => setNote(event.target.value)} disabled={busy} />
                </label>
                {actionError && <p role="alert" className="duplicate-review__error">{actionError}</p>}
                {!detail.can_confirm && <p className="text-sm duplicate-review__error">Confirmation is unavailable: {CONFIRM_BLOCK[detail.confirm_block_reason] || 'the pair changed'} You may dismiss this flag.</p>}
                {confirmOpen ? (
                  <div className="banner banner--warning" role="group" aria-label="Confirm duplicate decision">
                    <span className="body">
                      <span className="title">Close #{detail.case_b.reference} as a duplicate?</span>
                      <br />#{detail.case_a.reference} stays active. This decision is recorded in the audit trail.
                      <span className="row duplicate-review__buttons">
                        <button className="btn btn--primary btn--sm" onClick={() => decide('confirm')} disabled={busy}>{busy ? 'Saving…' : 'Confirm and close newer case'}</button>
                        <button className="btn btn--secondary btn--sm" onClick={() => setConfirmOpen(false)} disabled={busy}>Cancel</button>
                      </span>
                    </span>
                  </div>
                ) : (
                  <div className="row duplicate-review__buttons">
                    <button className="btn btn--secondary" onClick={() => decide('dismiss')} disabled={busy}>{busy ? 'Saving…' : 'Not a duplicate'}</button>
                    <button className="btn btn--primary" onClick={() => setConfirmOpen(true)} disabled={busy || !detail.can_confirm}>Confirm duplicate</button>
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm">This flag was {detail.status} by {detail.decided_by || 'an officer'} on {dateTime(detail.decided_at)}.</p>
            )}
          </section>
        </>
      )}
    </ResponderShell>
  )
}

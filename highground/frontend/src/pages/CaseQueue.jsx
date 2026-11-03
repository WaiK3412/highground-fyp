/** Screen 07: /api/cases/ enforces role visibility before the queue renders. */

import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import ResponderShell from './ResponderShell'
import { useDocumentTitle } from '../useDocumentTitle'
import { CASE_NOT_FOUND, useCaseFromAddress } from '../useCaseFromAddress'
import CaseMap from './CaseMap'
import CaseCard from '../components/queue/CaseCard'
import CasePanel from '../components/queue/CasePanel'
import MapCaseCard from '../components/queue/MapCaseCard'
import QueueFilters from '../components/queue/QueueFilters'
import QueueSummary from '../components/queue/QueueSummary'

// The list and map share one set of filters, as the API's query parameters.
function queueParams(status, priority, help, scope, search) {
  return {
    status, priority, help, q: search,
    open_help: scope === 'open_help' ? '1' : '',
    mine: scope === 'mine' ? '1' : '',
  }
}

export default function CaseQueue({ user, onLogout, onNavigate, onOpenDuplicate, duplicateCount, caseRoute }) {
  useDocumentTitle('Case queue')
  const [cases, setCases] = useState([])
  // Counts over the whole visible queue; `shown` is how many the current filters leave.
  const [overview, setOverview] = useState(null)
  const [shown, setShown] = useState(null)
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [help, setHelp] = useState('')
  // An overview count's own filter: help no one has taken, or the organisation's own work.
  const [scope, setScope] = useState('')
  const [unmet, setUnmet] = useState(null)
  const [search, setSearch] = useState('')
  const [listError, setListError] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailError, setDetailError] = useState(null)
  const [detailLoadingId, setDetailLoadingId] = useState(null)
  const [loading, setLoading] = useState(true)

  const [reloadKey, setReloadKey] = useState(0)
  // List stays the default: it works without map tiles and holds every case.
  const [view, setView] = useState('list')
  const [mapData, setMapData] = useState(null)
  const [mapError, setMapError] = useState(null)
  const [mapLoading, setMapLoading] = useState(false)
  // The case whose card is open over the map (a full detail response).
  const [mapCase, setMapCase] = useState(null)
  const selectionVersion = useRef(0)

  // Set every list filter at once (absent means All); the search box is kept.
  function apply(filters) {
    invalidateQueue()
    setStatus(filters.status || '')
    setPriority(filters.priority || '')
    setHelp(filters.help || '')
    setScope(filters.scope || '')
  }

  function changeSearch(value) {
    invalidateQueue()
    setSearch(value)
  }

  function invalidateQueue({ keepDetail = false } = {}) {
    selectionVersion.current += 1
    setMapCase(null)
    if (!keepDetail) {
      setDetail(null)
      if (caseRoute.id != null) caseRoute.clear()
    }
    setDetailError(null)
    setDetailLoadingId(null)
    setLoading(true)
    setListError(null)
    setShown(null)
    setCases([])
    setMapLoading(view === 'map')
    setMapData(null)
    setMapError(null)
  }

  useEffect(() => {
    let cancelled = false
    api
      .cases(queueParams(status, priority, help, scope, search))
      .then((list) => {
        if (cancelled) return
        setCases(list.results)
        setShown(list.count)
      })
      .catch((err) => !cancelled && setListError(err.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [status, priority, help, scope, search, reloadKey])

  useEffect(() => {
    api.stats().then(setOverview).catch(() => setOverview(null))
  }, [reloadKey])

  // Officers: which types of help no organisation has taken (ADR-020).
  useEffect(() => {
    if (user.role !== 'disaster_officer') return
    api.unmetHelp().then(setUnmet).catch(() => setUnmet(null))
  }, [user.role, reloadKey])

  // The map is fetched only when shown, with the same filters as the list.
  useEffect(() => {
    if (view !== 'map') return undefined
    let cancelled = false
    api
      .caseMap(queueParams(status, priority, help, scope, search))
      .then((data) => {
        if (cancelled) return
        setMapData(data)
        setMapError(null)
      })
      .catch((err) => !cancelled && setMapError(err.message))
      .finally(() => !cancelled && setMapLoading(false))
    return () => {
      cancelled = true
    }
  }, [view, status, priority, help, scope, search, reloadKey])

  const openCase = async (id) => {
    const version = ++selectionVersion.current
    setDetailError(null)
    setDetailLoadingId(id)
    try {
      const result = await api.caseDetail(id)
      if (selectionVersion.current === version) setDetail(result)
    } catch (err) {
      if (selectionVersion.current !== version) return
      setDetailError({ message: err.status === 404 ? CASE_NOT_FOUND : err.message, id })
      // A bookmarked case that is gone or out of scope: keep the message, drop it from the address.
      if (err.status === 404) caseRoute.clear()
    } finally {
      if (selectionVersion.current === version) setDetailLoadingId(null)
    }
  }

  function clearCase() {
    selectionVersion.current += 1
    setDetail(null)
    setDetailLoadingId(null)
  }

  // The open case is part of the address (/queue/42), so Back closes it.
  useCaseFromAddress(caseRoute.id, detail?.id ?? null, openCase, clearCase)
  // On the map, a pin opens a card over the map; the side panel is one click on.
  const openMapCase = (id) => {
    const version = selectionVersion.current
    return api
      .caseDetail(id)
      .then((result) => {
        if (selectionVersion.current === version) setMapCase(result)
      })
      .catch((err) => {
        if (selectionVersion.current === version) setMapError(err.message)
      })
  }
  const closeMapCase = () => setMapCase(null)
  // A village marker stands for cases the list can show; go there.
  const showVillage = (name) => {
    invalidateQueue()
    setSearch(name)
    setReloadKey((n) => n + 1)
    setView('list')
  }

  // Escape closes the map card, as it would any dialog.
  useEffect(() => {
    if (!mapCase) return undefined
    const onKey = (event) => event.key === 'Escape' && setMapCase(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mapCase])

  // Refresh from the server after actions so the UI reflects recorded outcomes.
  async function refresh() {
    invalidateQueue({ keepDetail: true })
    const version = selectionVersion.current
    setReloadKey((n) => n + 1)
    if (detail) {
      const current = await api.caseDetail(detail.id)
      if (selectionVersion.current === version) setDetail(current)
    }
  }

  const [claimingId, setClaimingId] = useState(null)
  const [claimError, setClaimError] = useState(null)
  const [notice, setNotice] = useState(null)

  async function claimFromCard(jobId) {
    setClaimError(null)
    setNotice(null)
    setClaimingId(jobId)
    try {
      const claimed = await api.claimJob(jobId)
      const job = claimed.jobs.find((item) => item.id === jobId)
      // Show claim confirmation because removing the claim button alone looks like no change.
      setNotice(
        `The ${job.help_type_display.toLowerCase()} job on #${claimed.reference} is now your organisation's. ` +
          `It is locked to other organisations and the change is in the audit log.`,
      )
      await refresh()
    } catch (err) {
      setClaimError(err.message)
    } finally {
      setClaimingId(null)
    }
  }

  return (
    <ResponderShell
      user={user} active="queue"
      counts={{ queue: overview?.total, duplicates: duplicateCount }}
      onNavigate={onNavigate} onLogout={onLogout}
      mainClassName="main main--vp" mainStyle={null}
    >
        <div className="page-header">
          <div>
            <h1>Case queue</h1>
            <p>
              {user.role === 'disaster_officer'
                ? `Requests in ${user.district || 'your district'}`
                : "Verified requests, and your organisation's own"}
              , in priority-class order, then by submission time.
            </p>
          </div>
          <div className="view-toggle" role="group" aria-label="Queue view">
            {[['list', 'List'], ['map', 'Map']].map(([key, label]) => (
              <button
                type="button"
                key={key}
                className={view === key ? 'active' : undefined}
                aria-pressed={view === key}
                onClick={() => {
                  if (view === key) return
                  selectionVersion.current += 1
                  setMapCase(null)
                  if (key === 'map') {
                    setMapLoading(true)
                    setMapData(null)
                    setMapError(null)
                  }
                  setView(key)
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <QueueSummary
          user={user} overview={overview} unmet={unmet} apply={apply}
          current={{ status, priority, help, scope }}
        />

        <QueueFilters
          user={user} current={{ status, priority, help, scope, search }} apply={apply}
          setSearch={changeSearch} shown={shown} total={overview?.total}
        />

        {/* Keep header/filters pinned while queue/detail columns scroll independently. */}
        <div
          // Split as soon as a case is being opened, so the list does not narrow (and its
          // cards reflow) only when the detail arrives.
          className={`vp-fill case-queue__workspace${detail || detailLoadingId ? ' case-queue__workspace--split' : ''}`}
          style={{
            display: 'grid',
            gap: 'var(--sp-16)',
          }}
        >
          {view === 'map' ? (
            <div className="stack" style={{ gap: 'var(--sp-12)', minHeight: 0 }}>
              {mapLoading && <p role="status" className="text-sm text-muted">Updating map…</p>}
              {mapError && (
                <p role="alert" className="text-sm text-danger">
                  {mapError}
                </p>
              )}
              {mapData?.unmapped > 0 &&
                (mapData.points.length > 0 || mapData.areas.length > 0) && (
                <p className="text-sm text-muted">
                  {mapData.unmapped} {mapData.unmapped === 1 ? 'case has' : 'cases have'} no mapped
                  location yet — the list shows {mapData.unmapped === 1 ? 'it' : 'them'}.
                </p>
              )}
              {!mapLoading && !mapError && mapData &&
                mapData.points.length === 0 && mapData.areas.length === 0 && (
                  <p role="status" className="text-sm text-muted">
                    {mapData.unmapped > 0
                      ? `${mapData.unmapped} matching ${mapData.unmapped === 1 ? 'case has' : 'cases have'} no mapped location. ${mapData.unmapped === 1 ? 'It is' : 'They are'} in List view.`
                      : 'No cases match this filter.'}
                  </p>
                )}
              <CaseMap
                points={mapData?.points || []}
                areas={mapData?.areas || []}
                isOfficer={user.role === 'disaster_officer'}
                selectedId={mapCase?.id}
                onOpenCase={openMapCase}
                onOpenArea={showVillage}
                onMapClick={closeMapCase}
              >
                {mapCase && (
                  <MapCaseCard
                    detail={mapCase}
                    user={user}
                    onOpenDuplicate={onOpenDuplicate}
                    onClose={closeMapCase}
                    onOpen={() => {
                      setDetail(mapCase)
                      setMapCase(null)
                      caseRoute.open(mapCase.id)
                    }}
                  />
                )}
              </CaseMap>
              {mapData?.areas?.length > 0 && (
                <p className="text-xs text-muted">
                  Pins are cases whose location you may see. Numbered circles count the other cases
                  by village; exact locations stay with the district office and the claiming
                  organisation.
                </p>
              )}
            </div>
          ) : (
          <div className="stack vp-scroll scroll-pane gap-12">
            {notice && (
              <div className="banner banner--info">
                <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span className="body">
                  <span className="title">Case claimed.</span>
                  <br />
                  {notice}
                </span>
              </div>
            )}
            {claimError && (
              <div
                role="alert"
                style={{
                  background: 'var(--danger-100)',
                  color: 'var(--danger-600)',
                  padding: '1rem 1.2rem',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 'var(--fs-14)',
                  fontWeight: 600,
                }}
              >
                {claimError}
              </div>
            )}
            {loading && <p className="text-muted">Loading cases…</p>}
            {listError && <p role="alert" className="text-sm text-danger">Could not load the queue: {listError} <button className="btn btn--ghost btn--sm" onClick={() => { invalidateQueue(); setReloadKey((n) => n + 1) }}>Retry</button></p>}
            {detailError && <p role="alert" className="text-sm">Could not open case: {detailError.message} <button className="btn btn--ghost btn--sm" onClick={() => openCase(detailError.id)}>Retry</button></p>}
            {!loading && !listError && cases.length === 0 && (
              <p className="text-muted">No cases match this filter.</p>
            )}
            {cases.map((item) => (
              <CaseCard
                key={item.id}
                item={item}
                user={user}
                busy={(item.jobs || []).some((job) => job.id === claimingId)}
                selected={detail?.id === item.id}
                onClaim={claimFromCard}
                onOpen={caseRoute.open}
              />
            ))}
          </div>
          )}

          {!detail && detailLoadingId && (
            <div className="stack vp-scroll scroll-pane gap-12">
              <p role="status" className="text-sm text-muted">Loading case detail…</p>
            </div>
          )}
          {detail && (
            <div className="stack vp-scroll scroll-pane gap-12">
              <CasePanel
                detail={detail}
                user={user}
                onOpenDuplicate={onOpenDuplicate}
                onDone={refresh}
                onClose={caseRoute.close}
              />
            </div>
          )}
        </div>
    </ResponderShell>
  )
}

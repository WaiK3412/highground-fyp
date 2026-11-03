/** Screen 04: visible_cases() enforces household privacy; role decisions follow ADR-012 section 2. */

import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Icon, PATHS } from '../icons'
import ResidentShell from './ResidentShell'
import { useDocumentTitle } from '../useDocumentTitle'
import { useLoad } from '../useLoad'
import { CASE_NOT_FOUND, useCaseFromAddress } from '../useCaseFromAddress'
import CaseCard from '../components/resident/CaseCard'
import CaseStatusBanner, { ApplicationBanner } from '../components/resident/CaseStatusBanner'
import CaseDetailPanel from '../components/resident/CaseDetailPanel'

export default function ResidentDashboard({ user, onLogout, onSubmitRequest, onNavigate, caseRoute }) {
  useDocumentTitle('My Recovery')
  const [detail, setDetail] = useState(null)
  const [detailError, setDetailError] = useState(null)
  const [detailLoadingId, setDetailLoadingId] = useState(null)
  const detailVersion = useRef(0)
  const backButton = useRef(null)
  const caseList = useRef(null)
  const lastSelectedId = useRef(null)

  useEffect(() => {
    if (window.matchMedia('(max-width: 600px)').matches) {
      if (detail && detail.id !== lastSelectedId.current) backButton.current?.focus()
      else if (!detail && lastSelectedId.current != null) {
        caseList.current?.querySelector(`[data-case-id="${lastSelectedId.current}"]`)?.focus()
      }
    }
    lastSelectedId.current = detail?.id ?? null
  }, [detail])

  // Fetch private detail separately because summary lists omit reasons, needs and location.
  async function loadCase(id) {
    const version = ++detailVersion.current
    setDetailError(null)
    setDetail(null)
    setDetailLoadingId(id)
    try {
      const result = await api.caseDetail(id)
      if (version === detailVersion.current) setDetail(result)
    } catch (err) {
      if (version !== detailVersion.current) return
      setDetailError({ message: err.status === 404 ? CASE_NOT_FOUND : err.message, id })
      // A bookmarked case that is gone or not theirs: keep the message, drop it from the address.
      if (err.status === 404) caseRoute.clear()
    } finally {
      if (version === detailVersion.current) setDetailLoadingId(null)
    }
  }

  function clearCase() {
    detailVersion.current += 1
    setDetail(null)
    setDetailLoadingId(null)
  }

  // The open case is part of the address, so opening and closing go through it.
  useCaseFromAddress(caseRoute.id, detail?.id ?? null, loadCase, clearCase)
  const toggleCase = (id) => (caseRoute.id === id ? caseRoute.close() : caseRoute.open(id))

  async function replyToCase(payload) {
    await api.replyToCase(detail.id, payload)
    const [updatedDetail, updatedCases] = await Promise.all([api.caseDetail(detail.id), api.cases()])
    setDetail(updatedDetail)
    setCases(updatedCases.results)
  }

  async function decideCompletion(jobId, decision, note) {
    await api.confirmJob(jobId, decision, note)
    const [updatedDetail, updatedCases] = await Promise.all([
      api.caseDetail(detail.id),
      api.cases(),
    ])
    setDetail(updatedDetail)
    setCases(updatedCases.results)
  }

  const { data: cases, setData: setCases, loading, error: loadError, reload } = useLoad(
    () => api.cases().then((list) => list.results), [], [],
  )

  const firstName = user.full_name.split(' ')[0]
  return (
    <ResidentShell
      user={user} active="recovery"
      onNavigate={(screen) => screen === 'submit' ? onSubmitRequest() : onNavigate(screen)}
      onLogout={onLogout} mainClassName="main main--vp" mainStyle={null}
    >
        <div className="page-header resident-home-header">
          <div>
            <h1>Selamat datang, {firstName}</h1>
            <p>Here is the latest on your household&apos;s recovery.</p>
          </div>
          <button className="btn btn--primary" onClick={onSubmitRequest}>
            <Icon path={PATHS.plus} strokeWidth={2} />
            Submit a request
          </button>
        </div>

        <div className="stack" style={{ gap: 'var(--sp-12)', marginBottom: '1.6rem' }}>
          <ApplicationBanner user={user} />
          {!loading && (
            <CaseStatusBanner cases={cases} openCaseId={detail?.id ?? null} onOpen={caseRoute.open} />
          )}
        </div>

        {/* Banner and lists appear together once the cases arrive: drawing the lists first
            and the banner above them later pushed the page down (layout shift on phones). */}
        {loading ? (
          <p role="status" className="text-sm text-muted">Loading your cases…</p>
        ) : (
        /* Scroll case/detail columns independently so long panels do not stretch the page. */
        <div
          className={`grid-2 vp-fill resident-workspace${detail ? ' resident-workspace--selected' : ''}`}
          style={{
            gridTemplateColumns: detail ? '1.5fr 1fr' : '1fr',
            gap: '1.6rem',
          }}
        >
          <div ref={caseList} className="stack vp-scroll scroll-pane resident-case-list" style={{ gap: '1.6rem' }}>
          <div className="card">
            <div className="card__header">
              <h2 className="h3">My cases</h2>
              {cases.length > 0 && (
                <span className="text-xs text-muted">Select a case to see its detail</span>
              )}
            </div>

            {detailError && (
              <div
                role="alert"
                className="text-sm"
                style={{ color: 'var(--danger-600)', fontWeight: 600, marginBottom: '1.2rem' }}
              >
                {detailError.message} <button className="btn btn--ghost btn--sm" onClick={() => loadCase(detailError.id)}>Retry</button>
              </div>
            )}
            {detailLoadingId && <p role="status" className="text-sm text-muted">Loading case detail…</p>}

            {loadError ? (
              <p role="alert" className="text-sm">Could not load your cases. <button className="btn btn--ghost btn--sm" onClick={reload}>Retry</button></p>
            ) : cases.length === 0 ? (
              <p className="text-sm text-muted">
                You have not submitted a request yet. When you do, it will appear here with its
                priority and progress.
              </p>
            ) : (
              <div className="stack" style={{ gap: '1.6rem' }}>
                {cases.map((item) => (
                  <CaseCard
                    key={item.id}
                    item={item}
                    onOpen={toggleCase}
                    isOpen={detail?.id === item.id}
                  />
                ))}
              </div>
            )}
          </div>

            <div className="card" style={{ background: 'var(--sand-100)' }}>
              <div className="row--between" style={{ gap: '1.6rem', flexWrap: 'wrap' }}>
                <div>
                  <h2 className="h3 mb-4">
                    Not affected this season? Your neighbours could use a hand.
                  </h2>
                  <p className="text-sm text-muted">
                    Relief organisations post the supplies they need and where to drop them
                    off. Goods only, never money.
                  </p>
                </div>
                <button className="btn btn--secondary btn--sm" onClick={() => onNavigate('appeals')}>
                  See supplies needed
                </button>
              </div>
            </div>
          </div>

          {detail && (
            <div className="stack vp-scroll scroll-pane" style={{ gap: '1.6rem' }}>
              <CaseDetailPanel
                backButtonRef={backButton}
                detail={detail}
                onClose={caseRoute.close}
                onCompletionDecision={decideCompletion}
                onReply={replyToCase}
              />
            </div>
          )}
        </div>
        )}
    </ResidentShell>
  )
}

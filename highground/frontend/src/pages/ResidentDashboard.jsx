/** Screen 04: visible_cases() enforces household privacy; role decisions follow ADR-012 section 2. */

import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Icon, PATHS } from '../icons'
import ResidentShell from './ResidentShell'
import { useDocumentTitle } from '../useDocumentTitle'
import { useLoad } from '../useLoad'
import CaseCard from '../components/resident/CaseCard'
import CaseStatusBanner, { ApplicationBanner } from '../components/resident/CaseStatusBanner'
import CaseDetailPanel from '../components/resident/CaseDetailPanel'

export default function ResidentDashboard({ user, onLogout, onSubmitRequest, onNavigate }) {
  useDocumentTitle('My Recovery')
  const [detail, setDetail] = useState(null)
  const [detailError, setDetailError] = useState(null)
  const [detailLoadingId, setDetailLoadingId] = useState(null)
  const detailVersion = useRef(0)
  const [unread, setUnread] = useState(0)

  // Fetch private detail separately because summary lists omit reasons, needs and location.
  async function openCase(id) {
    const version = ++detailVersion.current
    setDetailError(null)
    if (detail?.id === id) {
      setDetail(null)
      return
    }
    setDetail(null)
    setDetailLoadingId(id)
    try {
      const result = await api.caseDetail(id)
      if (version === detailVersion.current) setDetail(result)
    } catch (err) {
      if (version === detailVersion.current) setDetailError({ message: err.message, id })
    } finally {
      if (version === detailVersion.current) setDetailLoadingId(null)
    }
  }

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

  useEffect(() => {
    api
      .notifications()
      .then((data) => setUnread(data.unread))
      .catch(() => setUnread(0))
  }, [])

  const { data: cases, setData: setCases, loading, error: loadError, reload } = useLoad(
    () => api.cases().then((list) => list.results), [], [],
  )

  const firstName = user.full_name.split(' ')[0]
  return (
    <ResidentShell
      user={user} active="recovery" unread={unread} casesCount={cases.length}
      onNavigate={(screen) => screen === 'submit' ? onSubmitRequest() : onNavigate(screen)}
      onLogout={onLogout} mainClassName="main main--vp" mainStyle={null}
    >
        <div className="page-header">
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
          {!loading && <CaseStatusBanner cases={cases} />}
        </div>

        {/* Scroll case/detail columns independently so long panels do not stretch the page. */}
        <div
          className="grid-2 vp-fill"
          style={{
            gridTemplateColumns: detail ? '1.5fr 1fr' : '1fr',
            gap: '1.6rem',
          }}
        >
          <div className="stack vp-scroll scroll-pane" style={{ gap: '1.6rem' }}>
          <div className="card">
            <div className="card__header">
              <h3>My cases</h3>
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
                {detailError.message} <button className="btn btn--ghost btn--sm" onClick={() => openCase(detailError.id)}>Retry</button>
              </div>
            )}
            {detailLoadingId && <p role="status" className="text-sm text-muted">Loading case detail…</p>}

            {loading ? (
              <p className="text-sm text-muted">Loading your cases…</p>
            ) : loadError ? (
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
                    onOpen={openCase}
                    isOpen={detail?.id === item.id}
                  />
                ))}
              </div>
            )}
          </div>

            <div className="card" style={{ background: 'var(--sand-100)' }}>
              <div className="row--between" style={{ gap: '1.6rem', flexWrap: 'wrap' }}>
                <div>
                  <h3 className="mb-4">
                    Not affected this season? Your neighbours could use a hand.
                  </h3>
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
                detail={detail}
                onClose={() => setDetail(null)}
                onCompletionDecision={decideCompletion}
                onReply={replyToCase}
              />
            </div>
          )}
        </div>
    </ResidentShell>
  )
}

/**
 * The ten backup codes, shown once when they are made (ADR-028). The server
 * keeps only hashes, so this is the person's only chance to save them.
 */

import { useState } from 'react'

export default function BackupCodes({ codes, onDone, doneLabel = 'I have saved my codes' }) {
  const [copied, setCopied] = useState(false)
  const text = codes.join('\n')

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
    } catch {
      setCopied(false)  // clipboard blocked: the codes are still on screen to write down
    }
  }

  function download() {
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([`HighGround backup codes\n\n${text}\n`], { type: 'text/plain' }))
    link.download = 'highground-backup-codes.txt'
    link.click()
    setTimeout(() => URL.revokeObjectURL(link.href), 0)
  }

  return (
    <div className="stack" style={{ gap: '1.6rem' }}>
      <p className="text-sm" style={{ margin: 0 }}>
        Save these backup codes somewhere safe, away from your phone. If you lose your phone,
        each code signs you in once. <strong>They will not be shown again.</strong>
      </p>
      <ul
        aria-label="Backup codes"
        style={{
          listStyle: 'none', margin: 0, padding: '1.2rem', display: 'grid',
          gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '0.8rem',
          fontFamily: 'monospace', fontSize: 'var(--fs-16)', fontWeight: 700,
          background: 'var(--teal-50)', borderRadius: 'var(--radius-sm)', textAlign: 'center',
        }}
      >
        {codes.map((code) => <li key={code}>{code}</li>)}
      </ul>
      <div className="row" style={{ gap: 'var(--sp-12)', flexWrap: 'wrap' }}>
        <button type="button" className="btn btn--ghost btn--sm" onClick={copy}>
          {copied ? 'Copied' : 'Copy'}
        </button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={download}>
          Download
        </button>
      </div>
      <button type="button" className="btn btn--primary btn--full" onClick={onDone}>
        {doneLabel}
      </button>
    </div>
  )
}

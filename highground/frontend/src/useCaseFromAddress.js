import { useEffect } from 'react'

// Shown when an address names a case that is gone or not this person's to see.
export const CASE_NOT_FOUND = 'That case could not be found. It may have been removed, or it is not yours to view.'

/**
 * Keep the open case in step with the address (/my-cases/42, /queue/42).
 * When the address names a case that is not shown, load it; when the address
 * no longer names one (Back, or "Back to my cases"), clear the panel.
 */
export function useCaseFromAddress(caseId, shownId, load, clear) {
  /* oxlint-disable react-hooks/exhaustive-deps -- only an address change should load or clear; the callbacks are recreated every render. */
  useEffect(() => {
    if (caseId == null) clear()
    else if (caseId !== shownId) load(caseId)
  }, [caseId])
  /* oxlint-enable react-hooks/exhaustive-deps */
}

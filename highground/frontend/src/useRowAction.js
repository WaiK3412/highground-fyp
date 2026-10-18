import { useState } from 'react'

/**
 * Run one action on a row in a list (close, cancel, receive…) and swap in the
 * updated row the server returns. One action at a time; the error stays shown
 * until the next attempt.
 */
export function useRowAction(setRows) {
  const [busyId, setBusyId] = useState(null)
  const [error, setError] = useState(null)

  async function run(id, request) {
    setBusyId(id)
    setError(null)
    try {
      const updated = await request()
      setRows((rows) => rows.map((row) => (row.id === id ? updated : row)))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  return { busyId, error, run }
}

import { useCallback, useEffect, useRef, useState } from 'react'

/** Load on dependency changes; retain data and ignore obsolete responses. */
export function useLoad(loader, deps, initialData = null) {
  const [data, setData] = useState(initialData)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const version = useRef(0)

  /* oxlint-disable react-hooks/exhaustive-deps -- deps control fetching; inline loaders must not reload on every render. */
  useEffect(() => {
    const current = ++version.current
    loader()
      .then((result) => { if (current === version.current) setData(result) })
      .catch((err) => { if (current === version.current) setError(err.message) })
      .finally(() => { if (current === version.current) setLoading(false) })
    return () => { version.current += 1 }
  }, [...deps, attempt])
  /* oxlint-enable react-hooks/exhaustive-deps */

  const reload = useCallback(() => {
    version.current += 1
    setError(null)
    setLoading(true)
    setAttempt((n) => n + 1)
  }, [])

  return { data, setData, loading, error, reload }
}

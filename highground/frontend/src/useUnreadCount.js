import { useEffect, useState } from 'react'
import { api } from './api'

/**
 * The unread notification count for the sidebar badge, refreshed every minute
 * while the tab is visible and as soon as it becomes visible again, so new
 * notifications show without a reload. `enabled: false` skips it when the page
 * already has a live count (the notifications screen).
 */
export function useUnreadCount({ enabled = true, intervalMs = 60000 } = {}) {
  const [count, setCount] = useState(0)

  useEffect(() => {
    if (!enabled) return undefined
    let cancelled = false
    const load = () => {
      if (document.visibilityState !== 'visible') return
      api.notifications()
        .then((data) => { if (!cancelled) setCount(data.unread) })
        .catch(() => {})  // the badge is a hint; a failed refresh keeps the last count
    }
    load()
    const timer = setInterval(load, intervalMs)
    document.addEventListener('visibilitychange', load)
    return () => {
      cancelled = true
      clearInterval(timer)
      document.removeEventListener('visibilitychange', load)
    }
  }, [enabled, intervalMs])

  return count
}

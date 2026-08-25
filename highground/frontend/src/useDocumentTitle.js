import { useEffect } from 'react'

/**
 * Set the browser tab title for a screen.
 *
 * index.html can only carry one static title, but the design contract gives
 * every screen its own ("My Recovery — HighGround", "Log in — HighGround").
 * A single-page app has to set it per screen or every tab reads the same.
 */
export function useDocumentTitle(title) {
  useEffect(() => {
    document.title = `${title} — HighGround`
  }, [title])
}

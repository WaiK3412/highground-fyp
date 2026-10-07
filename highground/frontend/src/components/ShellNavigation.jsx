import { useEffect, useRef } from 'react'

export default function ShellNavigation({ active, children }) {
  const nav = useRef(null)

  useEffect(() => {
    function showActive() {
      if (!window.matchMedia('(max-width: 600px)').matches) return
      const current = nav.current.querySelector('[aria-current="page"]')
      if (!current) return
      // Move only the nav row; changing screens must not scroll the page vertically.
      const row = nav.current.getBoundingClientRect()
      const item = current.getBoundingClientRect()
      nav.current.scrollLeft += item.left - row.left
    }
    showActive()
    window.addEventListener('resize', showActive)
    return () => window.removeEventListener('resize', showActive)
  }, [active])

  return <nav ref={nav} className="side-nav" aria-label="Main navigation">{children}</nav>
}

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type AnchorHTMLAttributes,
  type ReactNode,
} from 'react'

/*
  A tiny router (no extra library needed).
  - Keeps the current URL in React state.
  - `navigate('/diagnose')` changes the URL without reloading the page.
  - `navigate('/#safety')` goes to the homepage and scrolls to the Safety section.
  - `replace(...)` changes the URL without adding a Back-button entry.
  - `goBack('/')` goes to the previous screen in this app, or to the fallback
    if the visitor opened this page directly (so Back never leaves the app or dead-ends).
  If the app grows to many pages, this can be swapped for React Router later.
*/

export interface RouteLocation {
  pathname: string
  search: string
  hash: string
}

interface RouterValue {
  location: RouteLocation
  navigate: (to: string) => void
  replace: (to: string) => void
  goBack: (fallback: string) => void
}

/** Each history entry we create remembers how deep into the app it is. */
interface HistoryState {
  idx: number
}

const RouterContext = createContext<RouterValue | null>(null)

function readLocation(): RouteLocation {
  const { pathname, search, hash } = window.location
  return { pathname, search, hash }
}

function currentIndex(): number {
  const state = window.history.state as HistoryState | null
  return typeof state?.idx === 'number' ? state.idx : 0
}

function scrollToHash(hash: string, smooth: boolean) {
  const id = decodeURIComponent(hash.replace(/^#/, ''))
  const target = id ? document.getElementById(id) : null
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (target) {
    target.scrollIntoView({ behavior: smooth && !reduceMotion ? 'smooth' : 'instant', block: 'start' })
  } else {
    window.scrollTo({ top: 0 })
  }
}

export function RouterProvider({ children }: { children: ReactNode }) {
  const [location, setLocation] = useState<RouteLocation>(readLocation)
  // A new object is stored on every navigation, so the scroll effect below runs
  // AFTER the new page has rendered. `smooth` is false for page loads and Back/Forward.
  const [scrollRequest, setScrollRequest] = useState<{ smooth: boolean } | null>(() =>
    window.location.hash ? { smooth: false } : null,
  )

  useEffect(() => {
    // Mark the first page the visitor landed on as depth 0.
    if (typeof (window.history.state as HistoryState | null)?.idx !== 'number') {
      window.history.replaceState({ idx: 0 } satisfies HistoryState, '')
    }
    const onPopState = () => {
      setLocation(readLocation())
      // Back/Forward to a section link (e.g. /#safety): jump to that section.
      // Without a #section, let the browser restore the previous scroll position.
      if (window.location.hash) setScrollRequest({ smooth: false })
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const navigate = useCallback((to: string) => {
    const url = new URL(to, window.location.href)
    const next = url.pathname + url.search + url.hash
    const current = window.location.pathname + window.location.search + window.location.hash
    if (next !== current) {
      window.history.pushState({ idx: currentIndex() + 1 } satisfies HistoryState, '', next)
    }
    setLocation({ pathname: url.pathname, search: url.search, hash: url.hash })
    setScrollRequest({ smooth: true })
  }, [])

  const replace = useCallback((to: string) => {
    const url = new URL(to, window.location.href)
    window.history.replaceState({ idx: currentIndex() } satisfies HistoryState, '', url.pathname + url.search + url.hash)
    setLocation({ pathname: url.pathname, search: url.search, hash: url.hash })
  }, [])

  const goBack = useCallback(
    (fallback: string) => {
      if (currentIndex() > 0) window.history.back()
      else navigate(fallback)
    },
    [navigate],
  )

  useEffect(() => {
    if (!scrollRequest) return
    // Wait one frame so the browser has laid out the new content before scrolling.
    const frame = requestAnimationFrame(() => scrollToHash(window.location.hash, scrollRequest.smooth))
    return () => cancelAnimationFrame(frame)
  }, [scrollRequest])

  const value = useMemo(() => ({ location, navigate, replace, goBack }), [location, navigate, replace, goBack])
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
}

export function useRouter(): RouterValue {
  const ctx = useContext(RouterContext)
  if (!ctx) throw new Error('useRouter must be used inside <RouterProvider>')
  return ctx
}

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & { to: string }

/** A normal <a> tag that navigates inside the app instead of reloading the page. */
export function Link({ to, onClick, ...rest }: LinkProps) {
  const { navigate } = useRouter()
  return (
    <a
      href={to}
      {...rest}
      onClick={(event) => {
        onClick?.(event)
        // Let the browser handle ctrl/cmd-click (open in new tab) etc.
        if (
          event.defaultPrevented ||
          event.button !== 0 ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey
        ) {
          return
        }
        event.preventDefault()
        navigate(to)
      }}
    />
  )
}

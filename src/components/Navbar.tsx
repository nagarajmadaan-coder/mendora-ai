import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import Logo from './Logo'
import Button from './Button'
import Icon from './Icon'
import { Link, useRouter } from '../lib/router'
import { NAV_ITEMS, ROUTES } from '../data/content'
import { useAuth } from '../state/AuthContext'

// Sticky top bar. On small screens the links collapse into a menu button.
export default function Navbar() {
  const [open, setOpen] = useState(false)
  const { location, navigate } = useRouter()
  const { status, user, logout } = useAuth()
  const signedIn = status === 'signedIn'
  const [unread, setUnread] = useState(0)

  // Unread in-app notifications: refreshed on every screen change, every minute, and when a screen marks some read.
  useEffect(() => {
    if (!signedIn) {
      setUnread(0)
      return
    }
    let cancelled = false
    const refresh = () =>
      api
        .listNotifications()
        .then((n) => !cancelled && setUnread(n.unread_count))
        .catch(() => undefined)
    void refresh()
    const timer = window.setInterval(refresh, 60_000)
    window.addEventListener('mendora:notifications', refresh)
    return () => {
      cancelled = true
      window.clearInterval(timer)
      window.removeEventListener('mendora:notifications', refresh)
    }
  }, [signedIn, location.pathname])

  const accountLinks = signedIn
    ? [
        user?.role === 'technician'
          ? { to: ROUTES.technicianProfile, label: 'My profile' }
          : user?.role === 'admin'
            ? { to: ROUTES.admin, label: 'Admin' }
            : { to: ROUTES.account, label: 'My requests' },
        { to: ROUTES.bookings, label: 'Bookings' },
      ]
    : []
  const unreadBadge = unread > 0 && (
    <span className="ml-1.5 inline-flex min-w-5 items-center justify-center rounded-full bg-teal-700 px-1.5 text-xs font-semibold text-white">
      {unread}
      <span className="sr-only"> unread notifications</span>
    </span>
  )
  const signOut = () => {
    logout()
    navigate(ROUTES.home)
  }

  // Close the mobile menu whenever the screen changes, or when Escape is pressed.
  useEffect(() => setOpen(false), [location])
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  /** A link is "current" when it points to the screen we are on (section links like /#services are never current). */
  const isCurrent = (to: string) => !to.includes('#') && location.pathname === to

  const linkClass = (to: string) =>
    'rounded-md px-2.5 py-2 text-sm font-medium whitespace-nowrap transition-colors ' +
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 ' +
    (isCurrent(to)
      ? 'bg-teal-50 text-teal-800'
      : 'text-navy-700 hover:bg-navy-50 hover:text-navy-900')

  return (
    <header className="sticky top-0 z-40 border-b border-navy-900/10 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/85">
      <nav aria-label="Main" className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Logo />

        <div className="hidden items-center gap-0.5 xl:flex">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={linkClass(item.to)}
              aria-current={isCurrent(item.to) ? 'page' : undefined}
            >
              {item.label}
            </Link>
          ))}
        </div>

        <div className="hidden items-center gap-1 xl:flex">
          {signedIn ? (
            <>
              {accountLinks.map((l) => (
                <Link key={l.to} to={l.to} className={linkClass(l.to)} aria-current={isCurrent(l.to) ? 'page' : undefined}>
                  {l.label}
                  {l.to === ROUTES.bookings && unreadBadge}
                </Link>
              ))}
              <button type="button" onClick={signOut} className={linkClass('#signout')}>
                Sign out
              </button>
            </>
          ) : (
            status === 'signedOut' && (
              <Link to={ROUTES.login} className={linkClass(ROUTES.login)} aria-current={isCurrent(ROUTES.login) ? 'page' : undefined}>
                Sign in
              </Link>
            )
          )}
          <Button to={ROUTES.diagnose}>Diagnose a Problem</Button>
        </div>

        <button
          type="button"
          className="inline-flex size-11 items-center justify-center rounded-lg text-navy-900 hover:bg-navy-50 focus-visible:outline-2 focus-visible:outline-teal-600 xl:hidden"
          aria-expanded={open}
          aria-controls="mobile-menu"
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpen((v) => !v)}
        >
          <Icon name={open ? 'close' : 'menu'} className="size-6" />
        </button>
      </nav>

      {open && (
        <div id="mobile-menu" className="border-t border-navy-900/10 bg-white shadow-sm xl:hidden">
          <div className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-3 sm:px-6">
            <Link
              to={ROUTES.home}
              className={`${linkClass(ROUTES.home)} py-3 text-base`}
              aria-current={isCurrent(ROUTES.home) ? 'page' : undefined}
            >
              Home
            </Link>
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className={`${linkClass(item.to)} py-3 text-base`}
                aria-current={isCurrent(item.to) ? 'page' : undefined}
              >
                {item.label}
              </Link>
            ))}
            {signedIn ? (
              <>
                {accountLinks.map((l) => (
                  <Link key={l.to} to={l.to} className={`${linkClass(l.to)} py-3 text-base`} aria-current={isCurrent(l.to) ? 'page' : undefined}>
                    {l.label}
                    {l.to === ROUTES.bookings && unreadBadge}
                  </Link>
                ))}
                <button type="button" onClick={signOut} className={`${linkClass('#signout')} py-3 text-left text-base`}>
                  Sign out
                </button>
              </>
            ) : (
              <Link to={ROUTES.login} className={`${linkClass(ROUTES.login)} py-3 text-base`} aria-current={isCurrent(ROUTES.login) ? 'page' : undefined}>
                Sign in
              </Link>
            )}
            <Button to={ROUTES.diagnose} className="mt-2 w-full">
              Diagnose a Problem
            </Button>
          </div>
        </div>
      )}
    </header>
  )
}

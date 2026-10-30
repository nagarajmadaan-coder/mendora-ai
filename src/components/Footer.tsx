import Logo from './Logo'
import { Link } from '../lib/router'
import { NAV_ITEMS, ROUTES, TRADES, diagnoseUrl } from '../data/content'

export default function Footer() {
  const linkClass =
    'rounded text-sm text-navy-100 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-300'

  const columns = [
    { heading: 'Explore', links: [{ label: 'Home', to: ROUTES.home }, ...NAV_ITEMS] },
    {
      heading: 'Start a request',
      links: [
        { label: 'Diagnose a problem', to: ROUTES.diagnose },
        ...TRADES.map((t) => ({ label: t.name, to: diagnoseUrl(t.id) })),
      ],
    },
  ]

  return (
    <footer className="border-t border-white/10 bg-navy-950 text-white">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:grid-cols-2 sm:px-6 md:grid-cols-[2fr_1fr_1fr] lg:px-8">
        <div className="max-w-sm sm:col-span-2 md:col-span-1">
          <Logo tone="light" />
          <p className="mt-4 text-sm leading-relaxed text-navy-100">
            An AI-powered home repair assistant for plumbing, electrical and carpentry problems.
          </p>
          <p className="mt-4 text-sm leading-relaxed text-navy-100">
            <strong className="font-semibold text-white">Emergency?</strong> Move away from the danger and call your
            local emergency service.{' '}
            <Link to={`${ROUTES.about}#emergency`} className={`${linkClass} underline underline-offset-2`}>
              What to do
            </Link>
          </p>
        </div>

        {columns.map((column) => (
          <nav key={column.heading} aria-label={column.heading}>
            <h2 className="text-sm font-semibold text-white">{column.heading}</h2>
            <ul className="mt-4 space-y-3">
              {column.links.map((link) => (
                <li key={link.to}>
                  <Link to={link.to} className={linkClass}>
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <div className="border-t border-white/10">
        <p className="mx-auto max-w-6xl px-4 py-6 text-xs leading-relaxed text-navy-100/80 sm:px-6 lg:px-8">
          © {new Date().getFullYear()} MENDORA AI. Prototype — AI assessments list possibilities, not confirmed
          diagnoses. Payments are a sandbox demo (no real money); no live calls yet.
        </p>
      </div>
    </footer>
  )
}

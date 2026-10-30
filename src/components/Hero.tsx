import Button from './Button'
import Icon from './Icon'
import { Link } from '../lib/router'
import { ROUTES, TRADES, diagnoseUrl } from '../data/content'

export default function Hero() {
  return (
    <section aria-labelledby="hero-heading" className="border-b border-navy-900/10 bg-white">
      <div className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-12 px-4 py-16 sm:px-6 sm:py-20 lg:grid-cols-[1.15fr_1fr] lg:gap-16 lg:px-8 lg:py-24">
        {/* Left: headline + main actions */}
        <div>
          <p className="inline-flex items-center gap-2 rounded-full bg-teal-50 px-3 py-1 text-sm font-medium text-teal-800 ring-1 ring-inset ring-teal-700/15">
            <Icon name="shield" className="size-4" />
            Plumbing · Electrical · Carpentry
          </p>

          <h1
            id="hero-heading"
            className="mt-6 text-4xl leading-[1.1] font-bold tracking-tight text-navy-900 sm:text-5xl lg:text-[3.4rem]"
          >
            Try to fix it with AI.{' '}
            <span className="block text-teal-700">Need a human? Get the nearest expert.</span>
          </h1>

          <p className="mt-6 max-w-xl text-lg leading-relaxed text-navy-600">
            MENDORA is a home repair assistant. Describe what’s wrong, get a clear assessment of the problem,
            then decide whether to fix it yourself or bring in a professional.
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Button to={ROUTES.diagnose} size="lg">
              Diagnose a Problem
              <Icon name="arrowRight" className="size-5" />
            </Button>
            <Button to="/#how-it-works" size="lg" variant="secondary">
              See how it works
            </Button>
          </div>
        </div>

        {/* Right: quick start by trade */}
        <div className="rounded-2xl border border-navy-900/10 bg-canvas p-5 shadow-sm sm:p-6">
          <h2 className="text-base font-semibold text-navy-900">What needs fixing?</h2>
          <p className="mt-1 text-sm text-navy-600">Pick a trade to start a repair request.</p>

          <ul className="mt-5 space-y-3">
            {TRADES.map((trade) => (
              <li key={trade.id}>
                <Link
                  to={diagnoseUrl(trade.id)}
                  className="group flex items-center gap-4 rounded-xl border border-navy-900/10 bg-white p-4 transition-colors hover:border-teal-600/50 hover:bg-teal-50/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
                >
                  <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-navy-900 text-teal-300">
                    <Icon name={trade.icon} className="size-5" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold text-navy-900">{trade.name}</span>
                    <span className="block truncate text-sm text-navy-600">
                      {trade.examples.slice(0, 2).join(', ')}
                    </span>
                  </span>
                  <Icon
                    name="arrowRight"
                    className="size-5 shrink-0 text-navy-600 transition-colors group-hover:text-teal-700"
                  />
                </Link>
              </li>
            ))}
          </ul>

          <p className="mt-5 flex items-start gap-2 text-sm text-navy-600">
            <Icon name="shield" className="mt-0.5 size-4 shrink-0 text-teal-700" />
            <span>
              Dangerous problems need a qualified professional.{' '}
              <Link
                to={`${ROUTES.about}#emergency`}
                className="rounded font-medium text-teal-800 underline underline-offset-2 hover:text-teal-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
              >
                Safety guidance
              </Link>
            </span>
          </p>
        </div>
      </div>
    </section>
  )
}

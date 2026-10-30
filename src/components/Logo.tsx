import { Link } from '../lib/router'

interface LogoProps {
  /** 'dark' = navy text (for light backgrounds), 'light' = white text (for the navy footer) */
  tone?: 'dark' | 'light'
}

export default function Logo({ tone = 'dark' }: LogoProps) {
  const text = tone === 'dark' ? 'text-navy-900' : 'text-white'
  return (
    <Link
      to="/"
      className={`inline-flex shrink-0 items-center gap-2.5 rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-teal-600 ${text}`}
      aria-label="MENDORA AI — home"
    >
      <svg viewBox="0 0 32 32" className="size-8 shrink-0" aria-hidden="true">
        <rect width="32" height="32" rx="8" className="fill-navy-900" />
        <path
          d="M8 22V10l8 7 8-7v12"
          fill="none"
          className="stroke-teal-400"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="text-lg font-bold tracking-[0.12em] whitespace-nowrap">
        MENDORA
        <span className={tone === 'dark' ? 'text-teal-700' : 'text-teal-300'}> AI</span>
      </span>
    </Link>
  )
}

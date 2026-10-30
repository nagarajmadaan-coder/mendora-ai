import { useEffect, useRef, type ReactNode } from 'react'
import BackButton from './BackButton'

/*
  The top of every inner screen: Back button, page title and intro.
  It also sets the browser-tab title and moves keyboard/screen-reader
  focus to the heading when the screen opens.
*/

interface PageHeaderProps {
  title: string
  intro?: ReactNode
  /** Text for the browser tab */
  documentTitle: string
  backFallback?: string
  /** Optional extra content to the right of / under the title (e.g. a badge) */
  aside?: ReactNode
}

export default function PageHeader({ title, intro, documentTitle, backFallback = '/', aside }: PageHeaderProps) {
  const headingRef = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    document.title = `${documentTitle} — MENDORA AI`
    headingRef.current?.focus({ preventScroll: true })
  }, [documentTitle])

  return (
    <div>
      <BackButton fallback={backFallback} />
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1
          ref={headingRef}
          tabIndex={-1}
          className="text-3xl font-bold tracking-tight text-navy-900 focus:outline-none sm:text-4xl"
        >
          {title}
        </h1>
        {aside}
      </div>
      {intro && <div className="mt-3 max-w-2xl text-lg leading-relaxed text-navy-600">{intro}</div>}
    </div>
  )
}

/** Shared width + padding wrapper for inner screens. */
export function PageContainer({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12 lg:px-8">{children}</div>
}

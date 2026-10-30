import type { ReactNode } from 'react'

/*
  A wrapper that gives every homepage section the same spacing,
  max width and heading style. `id` is what the navbar links jump to.
*/

interface SectionProps {
  id?: string
  eyebrow?: string
  title: string
  intro?: string
  tone?: 'canvas' | 'white'
  children: ReactNode
}

export default function Section({ id, eyebrow, title, intro, tone = 'canvas', children }: SectionProps) {
  const headingId = id ? `${id}-heading` : undefined
  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className={`py-16 sm:py-20 lg:py-24 ${tone === 'white' ? 'bg-white' : 'bg-canvas'}`}
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <div className="max-w-2xl">
          {eyebrow && (
            <p className="text-sm font-semibold tracking-wide text-teal-700 uppercase">{eyebrow}</p>
          )}
          <h2 id={headingId} className="mt-2 text-3xl font-bold tracking-tight text-navy-900 sm:text-4xl">
            {title}
          </h2>
          {intro && <p className="mt-4 text-lg leading-relaxed text-navy-600">{intro}</p>}
        </div>
        <div className="mt-10 sm:mt-12">{children}</div>
      </div>
    </section>
  )
}

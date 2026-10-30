import Section from './Section'
import Icon from './Icon'
import { PROCESS_STEPS } from '../data/content'

export default function HowItWorks() {
  return (
    <Section
      id="how-it-works"
      tone="white"
      eyebrow="How it works"
      title="From “something’s wrong” to a clear next step"
      intro="Every request follows the same three stages, so you always know what happens next."
    >
      <ol className="grid gap-5 md:grid-cols-3">
        {PROCESS_STEPS.map((step, index) => (
          <li key={step.title} className="relative rounded-2xl border border-navy-900/10 bg-canvas p-6">
            <div className="flex items-center gap-3">
              <span className="flex size-9 items-center justify-center rounded-full bg-navy-900 text-sm font-bold text-white">
                {index + 1}
              </span>
              <span className="flex size-9 items-center justify-center rounded-lg bg-teal-50 text-teal-700 ring-1 ring-inset ring-teal-700/15">
                <Icon name={step.icon} className="size-5" />
              </span>
            </div>
            <h3 className="mt-5 text-lg font-semibold text-navy-900">{step.title}</h3>
            <p className="mt-2 leading-relaxed text-navy-600">{step.description}</p>
          </li>
        ))}
      </ol>
    </Section>
  )
}

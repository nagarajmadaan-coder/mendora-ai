import type { ReactNode } from 'react'
import PageHeader, { PageContainer } from '../components/PageHeader'
import DangerSignList from '../components/DangerSignList'
import Button from '../components/Button'
import Icon, { type IconName } from '../components/Icon'
import { EMERGENCY_STEPS, PROCESS_STEPS, ROUTES } from '../data/content'

/* A white rounded panel with an icon heading — used for each block on this screen. */
function Panel({ id, icon, title, children }: { id?: string; icon: IconName; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={id ? `${id}-heading` : undefined} className="rounded-2xl border border-navy-900/10 bg-white p-5 sm:p-8">
      <h2 id={id ? `${id}-heading` : undefined} className="flex items-center gap-3 text-xl font-semibold text-navy-900">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-teal-50 text-teal-700 ring-1 ring-inset ring-teal-700/15">
          <Icon name={icon} className="size-5" />
        </span>
        {title}
      </h2>
      <div className="mt-5">{children}</div>
    </section>
  )
}

/* About & Safety screen (URL: /about). Sections can be linked directly: /about#never-diy, /about#emergency */
export default function AboutPage() {
  return (
    <PageContainer>
      <PageHeader
        title="About MENDORA & Safety"
        documentTitle="About & Safety"
        intro="Why MENDORA exists, how it is meant to work, and the safety rules it will always follow."
      />

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_22rem] lg:items-start">
        <div className="space-y-6">
          <Panel id="purpose" icon="home" title="Our purpose">
            <div className="space-y-4 leading-relaxed text-navy-700">
              <p>
                Small problems at home — a dripping tap, a dead socket, a door that won’t close — are stressful when
                you don’t know how serious they are or who to call. MENDORA is being built to help you understand the
                problem first, then choose the right way to fix it.
              </p>
              <p>
                The idea is simple: <strong className="text-navy-900">try to fix it with AI, and get a human
                when you need one.</strong> Simple, low-risk jobs can be guided step by step. Anything beyond that is
                passed to a qualified person.
              </p>
            </div>
            <ol className="mt-6 grid gap-3 sm:grid-cols-3">
              {PROCESS_STEPS.map((step, index) => (
                <li key={step.title} className="rounded-xl bg-canvas p-4">
                  <span className="flex size-7 items-center justify-center rounded-full bg-navy-900 text-xs font-bold text-white">
                    {index + 1}
                  </span>
                  <p className="mt-3 text-sm font-semibold text-navy-900">{step.title}</p>
                </li>
              ))}
            </ol>
          </Panel>

          <Panel id="never-diy" icon="shield" title="Our safety-first approach">
            <p className="leading-relaxed text-navy-700">
              Safety is checked before anything else. The following situations must <strong className="text-navy-900">never</strong>{' '}
              be handled with do-it-yourself instructions — from MENDORA or anywhere else. MENDORA is designed to stop,
              warn you, and direct you to emergency services or a qualified professional instead.
            </p>
            <div className="mt-6">
              <DangerSignList />
            </div>
          </Panel>

          <Panel id="status" icon="info" title="What MENDORA is — and isn’t — today">
            <ul className="space-y-3 text-navy-700">
              {[
                'AI assessments are generated from your description only. They list possible causes, not confirmed facts.',
                'Every report goes through a rule-based safety check before any AI. High-risk problems never get AI diagnosis or DIY steps; uncertain ones get safety questions and a professional recommendation.',
                'You can request a technician visit or an expert consultation and try a SANDBOX payment — no real money is taken, no card details are collected, and no live calls are connected yet. Technicians appear only after an admin verifies them; demo sample technicians are clearly labelled and are not real people.',
                'Repair guides are written by the MENDORA team and have not been reviewed by licensed professionals yet. Their causes are possibilities only.',
                'Your requests are private to your account. Only the trade, description and follow-up answers are sent to the AI provider — with emails and phone numbers removed. Photos are stored privately with your request (location data removed), shown to a technician only after they accept your booking, and never sent to the AI.',
                'MENDORA will never replace a licensed electrician, plumber, gas engineer or structural professional.',
              ].map((item) => (
                <li key={item} className="flex items-start gap-2 leading-relaxed">
                  <Icon name="check" className="mt-1 size-4 shrink-0 text-teal-700" />
                  {item}
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        {/* Emergency box — sticky on large screens so it stays visible */}
        <section
          id="emergency"
          aria-labelledby="emergency-heading"
          className="rounded-2xl bg-navy-900 p-5 text-white sm:p-6 lg:sticky lg:top-24"
        >
          <h2 id="emergency-heading" className="flex items-center gap-2 text-lg font-semibold">
            <Icon name="alert" className="size-5 text-amber-300" />
            In an emergency
          </h2>
          <ol className="mt-4 space-y-4">
            {EMERGENCY_STEPS.map((step, index) => (
              <li key={step} className="flex gap-3 text-sm leading-relaxed text-navy-100">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-amber-300 text-xs font-bold text-navy-950">
                  {index + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
          <p className="mt-5 rounded-lg bg-white/5 p-3 text-xs leading-relaxed text-navy-100 ring-1 ring-inset ring-white/15">
            MENDORA cannot contact emergency services for you. Always call them directly.
          </p>
        </section>
      </div>

      <div className="mt-10 flex flex-col items-start gap-4 rounded-2xl border border-navy-900/10 bg-white p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <p className="font-medium text-navy-900">Not an emergency? Describe the problem to get started.</p>
        <Button to={ROUTES.diagnose}>
          Diagnose a Problem
          <Icon name="arrowRight" className="size-4" />
        </Button>
      </div>
    </PageContainer>
  )
}

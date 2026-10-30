import Icon from './Icon'
import Button from './Button'
import DangerSignList from './DangerSignList'
import { ROUTES } from '../data/content'

export default function SafetySection() {
  return (
    <section id="safety" aria-labelledby="safety-heading" className="bg-navy-900 py-16 text-white sm:py-20 lg:py-24">
      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-10 px-4 sm:px-6 lg:grid-cols-[1fr_1.15fr] lg:gap-16 lg:px-8">
        <div>
          <p className="text-sm font-semibold tracking-wide text-teal-300 uppercase">Safety first</p>
          <h2 id="safety-heading" className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
            Some problems are not DIY jobs
          </h2>
          <p className="mt-4 text-lg leading-relaxed text-navy-100">
            Electricity, gas and structural failures can cause serious injury. MENDORA is designed never to give
            do-it-yourself instructions for dangerous situations. Instead, it tells you to get to safety and contact a
            qualified professional or emergency service.
          </p>
          <div className="mt-8 flex items-start gap-3 rounded-xl bg-white/5 p-4 ring-1 ring-inset ring-white/15">
            <Icon name="alert" className="mt-0.5 size-5 shrink-0 text-amber-300" />
            <p className="text-sm leading-relaxed text-navy-100">
              <strong className="font-semibold text-white">In an emergency,</strong> move away from the danger first,
              then call your local emergency service or a qualified professional.
            </p>
          </div>
          <div className="mt-8">
            <Button to={`${ROUTES.about}#emergency`} variant="inverse">
              Read our safety guidance
              <Icon name="arrowRight" className="size-4" />
            </Button>
          </div>
        </div>

        <div className="rounded-2xl bg-white p-6 text-navy-900 sm:p-8">
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <Icon name="shield" className="size-5 text-teal-700" />
            Always get professional help for:
          </h3>
          <div className="mt-6">
            <DangerSignList />
          </div>
        </div>
      </div>
    </section>
  )
}

import { useRef, useState, type FormEvent, type ReactNode } from 'react'
import Button from '../Button'
import Icon from '../Icon'
import Spinner from '../Spinner'
import PhotoUpload from './PhotoUpload'
import { TRADES } from '../../data/content'
import { useIntake } from '../../state/IntakeContext'
import {
  DESCRIPTION_MAX,
  DESCRIPTION_MIN,
  validateIntake,
  type IntakeValues,
} from '../../lib/validateIntake'
import type { TradeId } from '../../types'

interface IntakeFormProps {
  /** Called with the cleaned-up values once everything required is valid */
  onValidSubmit: (values: IntakeValues & { trade: TradeId }) => void
  /** True while the request is being processed — the button shows a spinner and can't be pressed twice */
  submitting?: boolean
  /** Text shown on the button while submitting */
  submittingLabel?: string
  /** Shown just above the Continue button (e.g. a server error, or "you'll be asked to sign in") */
  footer?: ReactNode
}

/*
  The repair-intake form.
  - Values live in the shared intake store, so they survive moving between screens
    (including going to sign in and coming back).
  - Errors appear after a field is left (blur) or after a submit attempt.
  - On a failed submit, focus jumps to the first field with a problem.
*/
export default function IntakeForm({ onValidSubmit, submitting = false, submittingLabel = 'Saving…', footer }: IntakeFormProps) {
  const { values, setValues: onChange } = useIntake()
  const [touched, setTouched] = useState<Record<keyof IntakeValues, boolean>>({
    trade: false,
    description: false,
  })
  const [submitAttempted, setSubmitAttempted] = useState(false)
  const firstTradeRef = useRef<HTMLInputElement>(null)
  const descriptionRef = useRef<HTMLTextAreaElement>(null)

  const errors = validateIntake(values)
  const showTradeError = Boolean(errors.trade) && (touched.trade || submitAttempted)
  const showDescriptionError = Boolean(errors.description) && (touched.description || submitAttempted)
  const length = values.description.trim().length

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault() // stop the browser from reloading the page
    if (submitting) return
    setSubmitAttempted(true)

    if (errors.trade) {
      firstTradeRef.current?.focus()
      return
    }
    if (errors.description) {
      descriptionRef.current?.focus()
      return
    }
    onValidSubmit({ trade: values.trade as TradeId, description: values.description.trim() })
  }

  return (
    <form noValidate onSubmit={handleSubmit} className="space-y-8">
      {/* ---------- Trade ---------- */}
      <fieldset aria-describedby={showTradeError ? 'trade-error' : undefined}>
        <legend className="text-base font-semibold text-navy-900">
          1. What kind of problem is it? <span className="text-red-700" aria-hidden="true">*</span>
          <span className="sr-only">(required)</span>
        </legend>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {TRADES.map((trade, index) => {
            const checked = values.trade === trade.id
            return (
              <label
                key={trade.id}
                className={`flex cursor-pointer items-center gap-3 rounded-xl border bg-white p-4 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-teal-600 ${
                  checked
                    ? 'border-teal-600 ring-2 ring-teal-600/25'
                    : showTradeError
                      ? 'border-red-600/60 hover:border-red-600'
                      : 'border-navy-900/15 hover:border-navy-900/30'
                }`}
              >
                <input
                  ref={index === 0 ? firstTradeRef : undefined}
                  type="radio"
                  name="trade"
                  value={trade.id}
                  checked={checked}
                  onChange={() => onChange({ ...values, trade: trade.id as TradeId })}
                  onBlur={() => setTouched((t) => ({ ...t, trade: true }))}
                  aria-invalid={showTradeError || undefined}
                  className="sr-only"
                />
                <span
                  className={`flex size-10 shrink-0 items-center justify-center rounded-lg ${
                    checked ? 'bg-teal-700 text-white' : 'bg-navy-900 text-teal-300'
                  }`}
                >
                  <Icon name={trade.icon} className="size-5" />
                </span>
                <span className="flex-1 font-semibold text-navy-900">{trade.name}</span>
                <span
                  aria-hidden="true"
                  className={`flex size-5 items-center justify-center rounded-full border-2 ${
                    checked ? 'border-teal-700 bg-teal-700 text-white' : 'border-navy-900/25'
                  }`}
                >
                  {checked && <Icon name="check" className="size-3" />}
                </span>
              </label>
            )
          })}
        </div>
        {showTradeError && (
          <p id="trade-error" className="mt-2 flex items-start gap-1.5 text-sm text-red-700">
            <Icon name="alert" className="mt-0.5 size-4 shrink-0" />
            {errors.trade}
          </p>
        )}
      </fieldset>

      {/* ---------- Description ---------- */}
      <div>
        <label htmlFor="description" className="text-base font-semibold text-navy-900">
          2. Describe the problem <span className="text-red-700" aria-hidden="true">*</span>
          <span className="sr-only">(required)</span>
        </label>
        <p id="description-hint" className="mt-1 text-sm text-navy-600">
          Where is it, what do you see, hear or smell, and when did it start? Example: “The kitchen sink drains
          very slowly and gurgles. It started two days ago.”
        </p>
        <textarea
          ref={descriptionRef}
          id="description"
          name="description"
          rows={6}
          maxLength={DESCRIPTION_MAX}
          value={values.description}
          onChange={(e) => onChange({ ...values, description: e.target.value })}
          onBlur={() => setTouched((t) => ({ ...t, description: true }))}
          aria-invalid={showDescriptionError || undefined}
          aria-describedby={`description-hint description-count${showDescriptionError ? ' description-error' : ''}`}
          className={`mt-3 block w-full resize-y rounded-xl border bg-white px-4 py-3 text-base text-navy-900 placeholder:text-navy-600/70 focus:outline-2 focus:outline-offset-0 ${
            showDescriptionError
              ? 'border-red-600 focus:outline-red-600'
              : 'border-navy-900/20 focus:border-teal-600 focus:outline-teal-600'
          }`}
          placeholder="Describe what’s going wrong…"
        />
        <div className="mt-2 flex flex-wrap items-start justify-between gap-x-4 gap-y-1 text-sm">
          {showDescriptionError ? (
            <p id="description-error" className="flex items-start gap-1.5 text-red-700">
              <Icon name="alert" className="mt-0.5 size-4 shrink-0" />
              {errors.description}
            </p>
          ) : (
            <span />
          )}
          <p id="description-count" className="text-navy-600">
            {length < DESCRIPTION_MIN
              ? `${length}/${DESCRIPTION_MIN} characters minimum`
              : `${values.description.length}/${DESCRIPTION_MAX} characters`}
          </p>
        </div>
      </div>

      {/* ---------- Photos (optional) ---------- */}
      <PhotoUpload />

      {/* ---------- Submit ---------- */}
      {footer}
      <div className="flex flex-col-reverse gap-3 border-t border-navy-900/10 pt-6 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-navy-600">
          <span className="text-red-700" aria-hidden="true">*</span> Required fields
        </p>
        <Button type="submit" size="lg" disabled={submitting} aria-busy={submitting || undefined}>
          {submitting ? (
            <>
              <Spinner className="size-5" label={submittingLabel} />
              {submittingLabel}
            </>
          ) : (
            <>
              Continue
              <Icon name="arrowRight" className="size-5" />
            </>
          )}
        </Button>
      </div>
    </form>
  )
}

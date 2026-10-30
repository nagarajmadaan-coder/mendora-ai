import { forwardRef, type InputHTMLAttributes } from 'react'
import Icon from './Icon'

/* A labelled text input with optional hint and error message, wired up for screen readers. */

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  id: string
  label: string
  hint?: string
  error?: string | null
}

const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { id, label, hint, error, className = '', ...inputProps },
  ref,
) {
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ') || undefined
  return (
    <div className={className}>
      <label htmlFor={id} className="block text-sm font-semibold text-navy-900">
        {label}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="mt-1 text-sm text-navy-600">
          {hint}
        </p>
      )}
      <input
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={`mt-2 block h-12 w-full rounded-xl border bg-white px-4 text-base text-navy-900 placeholder:text-navy-600/70 focus:outline-2 focus:outline-offset-0 ${
          error ? 'border-red-600 focus:outline-red-600' : 'border-navy-900/20 focus:border-teal-600 focus:outline-teal-600'
        }`}
        {...inputProps}
      />
      {error && (
        <p id={`${id}-error`} className="mt-2 flex items-start gap-1.5 text-sm text-red-700">
          <Icon name="alert" className="mt-0.5 size-4 shrink-0" />
          {error}
        </p>
      )}
    </div>
  )
})

export default TextField

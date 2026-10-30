/* Star rating: display (value) or input (onChange). Ratings come only from completed bookings. */

interface Props {
  value: number
  label?: string
  onChange?: (value: number) => void
  size?: string
}

export default function Stars({ value, label, onChange, size = 'size-4' }: Props) {
  const star = (i: number) => {
    const filled = value >= i - 0.25
    const half = !filled && value >= i - 0.75
    const path = 'M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3l-5.9 3.3 1.3-6.6-4.9-4.6 6.6-.8z'
    return (
      <svg viewBox="0 0 24 24" className={`${size} ${filled || half ? 'text-amber-500' : 'text-navy-900/20'}`} aria-hidden="true">
        {half && (
          <defs>
            <linearGradient id={`half-${i}`}>
              <stop offset="50%" stopColor="currentColor" />
              <stop offset="50%" stopColor="rgb(11 27 51 / 0.2)" />
            </linearGradient>
          </defs>
        )}
        <path d={path} fill={half ? `url(#half-${i})` : 'currentColor'} />
      </svg>
    )
  }

  if (!onChange) {
    return (
      <span className="inline-flex items-center gap-0.5" role="img" aria-label={label ?? `${value} out of 5 stars`}>
        {[1, 2, 3, 4, 5].map((i) => (
          <span key={i}>{star(i)}</span>
        ))}
        <span className="ml-1 text-sm font-semibold text-navy-900">{value.toFixed(1)}</span>
      </span>
    )
  }

  return (
    <div className="flex items-center gap-1" role="radiogroup" aria-label="Rating">
      {[1, 2, 3, 4, 5].map((i) => (
        <button
          key={i}
          type="button"
          role="radio"
          aria-checked={value === i}
          aria-label={`${i} star${i > 1 ? 's' : ''}`}
          onClick={() => onChange(i)}
          className="rounded p-0.5 focus-visible:outline-2 focus-visible:outline-teal-600"
        >
          {star(i)}
        </button>
      ))}
    </div>
  )
}

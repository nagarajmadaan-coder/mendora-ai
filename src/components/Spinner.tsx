/* A small loading spinner. Screen readers hear the label instead. */
export default function Spinner({ className = 'size-5', label = 'Loading' }: { className?: string; label?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`${className} motion-safe:animate-spin`} role="img" aria-label={label}>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

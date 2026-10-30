import Icon from './Icon'
import { useRouter } from '../lib/router'

interface BackButtonProps {
  /** Where to go if there is no previous screen in this app (e.g. the page was opened directly). */
  fallback?: string
  label?: string
}

/* Goes to the previous screen, like the browser's Back button — but never leaves the app. */
export default function BackButton({ fallback = '/', label = 'Back' }: BackButtonProps) {
  const { goBack } = useRouter()
  return (
    <button
      type="button"
      onClick={() => goBack(fallback)}
      className="-ml-2 inline-flex h-11 items-center gap-1.5 rounded-lg px-2 text-sm font-medium text-navy-700 hover:bg-navy-50 hover:text-navy-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
    >
      <Icon name="arrowLeft" className="size-4" />
      {label}
    </button>
  )
}

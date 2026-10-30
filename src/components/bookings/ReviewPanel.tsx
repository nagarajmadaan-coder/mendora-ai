import { useState } from 'react'
import Alert from '../Alert'
import Button from '../Button'
import Spinner from '../Spinner'
import Stars from '../reviews/Stars'
import { ApiError, api, type Booking } from '../../lib/api'

/* Review the technician — only for your own COMPLETED booking, once (the server enforces it). */

export default function ReviewPanel({ booking, onReviewed }: { booking: Booking; onReviewed: () => void }) {
  const [rating, setRating] = useState(0)
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (booking.review) {
    return (
      <section className="rounded-2xl border border-navy-900/10 bg-white p-5 sm:p-6" aria-labelledby="review-heading">
        <h2 id="review-heading" className="font-semibold text-navy-900">
          Your review
        </h2>
        <div className="mt-2">
          <Stars value={booking.review.rating} />
        </div>
        {booking.review.comment && <p className="mt-2 text-sm text-navy-800">“{booking.review.comment}”</p>}
        <p className="mt-2 text-xs text-navy-600">Shown publicly as “A MENDORA customer”. Contact details are removed.</p>
      </section>
    )
  }
  if (!booking.can_review) return null

  const submit = async () => {
    if (!rating) {
      setError('Please choose a star rating.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await api.reviewBooking(booking.id, { rating, comment: comment.trim() || undefined })
      onReviewed()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-2xl border border-teal-600/40 bg-white p-5 sm:p-6" aria-labelledby="review-heading">
      <h2 id="review-heading" className="font-semibold text-navy-900">
        How did it go?
      </h2>
      <p className="mt-1 text-sm text-navy-700">Rate {booking.technician.display_name}. Reviews only come from completed bookings like this one.</p>
      <div className="mt-3">
        <Stars value={rating} onChange={setRating} size="size-7" />
      </div>
      <label className="mt-3 block text-sm font-medium text-navy-900">
        Comment <span className="font-normal text-navy-600">(optional)</span>
        <textarea
          value={comment}
          maxLength={500}
          rows={2}
          onChange={(e) => setComment(e.target.value)}
          className="mt-1 block w-full rounded-lg border border-navy-900/20 bg-white px-3 py-2 text-base text-navy-900 focus:border-teal-600 focus:outline-2 focus:outline-teal-600"
        />
      </label>
      {error && (
        <div className="mt-3">
          <Alert tone="error" announce title={error} />
        </div>
      )}
      <Button className="mt-3" onClick={() => void submit()} disabled={busy}>
        {busy && <Spinner />} Submit review
      </Button>
    </section>
  )
}

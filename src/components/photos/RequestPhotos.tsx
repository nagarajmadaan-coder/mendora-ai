import { useEffect, useRef, useState } from 'react'
import Alert from '../Alert'
import Button from '../Button'
import Icon from '../Icon'
import Spinner from '../Spinner'
import { ApiError, api, type RequestPhoto } from '../../lib/api'
import { PHOTO_MAX_MB, PHOTO_TYPES } from '../../lib/validateIntake'

/*
  Photos saved with a repair request (merged feature).
  Visible to the owner, admins, and a technician only after they accept a booking. Never sent to the AI.
  Location data inside photos is removed by the server.
*/

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1] ?? '')
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

function PhotoThumb({ photo, canDelete, onDelete }: { photo: RequestPhoto; canDelete: boolean; onDelete: () => void }) {
  const [src, setSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let url: string | null = null
    let cancelled = false
    api
      .photoBlob(photo.url)
      .then((blob) => {
        if (cancelled) return
        url = URL.createObjectURL(blob)
        setSrc(url)
      })
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [photo.url])
  return (
    <li className="relative overflow-hidden rounded-xl border border-navy-900/10 bg-navy-50">
      {src ? (
        <a href={src} target="_blank" rel="noopener noreferrer">
          <img src={src} alt="Photo of the problem" className="aspect-square w-full object-cover" />
        </a>
      ) : (
        <div className="flex aspect-square items-center justify-center text-navy-600">{failed ? <Icon name="imageOff" className="size-6" /> : <Spinner />}</div>
      )}
      {canDelete && (
        <button
          type="button"
          onClick={onDelete}
          className="absolute top-1.5 right-1.5 rounded-full bg-white/90 p-1.5 text-navy-900 shadow hover:bg-white focus-visible:outline-2 focus-visible:outline-teal-600"
          aria-label="Remove photo"
        >
          <Icon name="trash" className="size-4" />
        </button>
      )}
    </li>
  )
}

export default function RequestPhotos({ requestId, canEdit }: { requestId: string; canEdit: boolean }) {
  const [photos, setPhotos] = useState<RequestPhoto[] | null>(null)
  const [max, setMax] = useState(3)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)

  const load = () =>
    api
      .listPhotos(requestId)
      .then((r) => {
        setPhotos(r.photos)
        setMax(r.max_photos)
        setNote(r.note)
      })
      .catch(() => setPhotos([]))

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestId])

  const add = async (files: FileList | null) => {
    if (!files?.length) return
    setBusy(true)
    setError(null)
    try {
      for (const file of Array.from(files)) {
        if (!(PHOTO_TYPES as readonly string[]).includes(file.type)) throw new ApiError(415, 'type', `“${file.name}” isn’t a JPEG, PNG or WebP photo.`)
        if (file.size > PHOTO_MAX_MB * 1024 * 1024) throw new ApiError(413, 'size', `“${file.name}” is larger than ${PHOTO_MAX_MB} MB.`)
        await api.uploadPhoto(requestId, await fileToBase64(file))
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'The photo couldn’t be added.')
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
      void load()
    }
  }

  const remove = async (photo: RequestPhoto) => {
    try {
      await api.deletePhoto(photo.url)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'The photo couldn’t be removed.')
    }
    void load()
  }

  if (photos === null) return null
  if (!canEdit && photos.length === 0) return null

  return (
    <section aria-labelledby="photos-heading" className="rounded-2xl border border-navy-900/10 bg-white p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="photos-heading" className="font-semibold text-navy-900">
          Photos {photos.length > 0 && <span className="font-normal text-navy-600">({photos.length}/{max})</span>}
        </h2>
        {canEdit && photos.length < max && (
          <>
            <input ref={input} type="file" accept={PHOTO_TYPES.join(',')} multiple className="sr-only" id={`photo-input-${requestId}`} onChange={(e) => void add(e.target.files)} />
            <Button variant="secondary" onClick={() => input.current?.click()} disabled={busy}>
              {busy ? <Spinner /> : <Icon name="camera" className="size-4" />}
              {busy ? 'Uploading…' : 'Add photos'}
            </Button>
          </>
        )}
      </div>
      {error && (
        <div className="mt-3">
          <Alert tone="error" announce title={error} />
        </div>
      )}
      {photos.length > 0 ? (
        <ul className="mt-4 grid grid-cols-3 gap-3">
          {photos.map((p) => (
            <PhotoThumb key={p.id} photo={p} canDelete={canEdit} onDelete={() => void remove(p)} />
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-navy-600">No photos yet. A clear photo helps a technician prepare.</p>
      )}
      <p className="mt-3 flex items-start gap-1.5 text-xs text-navy-600">
        <Icon name="lock" className="mt-px size-3.5 shrink-0" />
        {note} Location data inside photos is removed.
      </p>
    </section>
  )
}

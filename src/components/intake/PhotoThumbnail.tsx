import { useState } from 'react'
import Icon from '../Icon'
import type { PhotoItem } from '../../state/IntakeContext'

interface PhotoThumbnailProps {
  photo: PhotoItem
  /** When given, a remove (×) button is shown */
  onRemove?: () => void
}

/*
  A square photo preview with three states:
  - loading: grey shimmer until the browser has decoded the image
  - loaded:  the photo
  - error:   a clear "can't preview" message (e.g. a damaged file)
*/
export default function PhotoThumbnail({ photo, onRemove }: PhotoThumbnailProps) {
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading')
  const sizeKb = Math.max(1, Math.round(photo.file.size / 1024))
  const sizeLabel = sizeKb >= 1024 ? `${(sizeKb / 1024).toFixed(1)} MB` : `${sizeKb} KB`

  return (
    <figure className="group relative overflow-hidden rounded-xl border border-navy-900/10 bg-white">
      <div className="relative aspect-square bg-navy-50">
        {status === 'loading' && (
          <div className="absolute inset-0 flex items-center justify-center motion-safe:animate-pulse" aria-hidden="true">
            <Icon name="image" className="size-8 text-navy-600/40" />
          </div>
        )}
        {status === 'error' ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 p-2 text-center text-red-700">
            <Icon name="imageOff" className="size-7" />
            <span className="text-xs font-medium">Can’t preview this image</span>
          </div>
        ) : (
          <img
            src={photo.url}
            alt={`Preview of ${photo.file.name}`}
            onLoad={() => setStatus('loaded')}
            onError={() => setStatus('error')}
            className={`size-full object-cover transition-opacity ${status === 'loaded' ? 'opacity-100' : 'opacity-0'}`}
          />
        )}
      </div>
      <figcaption className="flex items-center justify-between gap-2 px-2.5 py-2 text-xs">
        <span className="min-w-0 truncate font-medium text-navy-800" title={photo.file.name}>
          {photo.file.name}
        </span>
        <span className="shrink-0 text-navy-600">{sizeLabel}</span>
      </figcaption>

      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${photo.file.name}`}
          className="absolute top-2 right-2 flex size-9 items-center justify-center rounded-full bg-white/95 text-navy-900 shadow-sm ring-1 ring-navy-900/10 hover:bg-red-50 hover:text-red-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
        >
          <Icon name="trash" className="size-4" />
        </button>
      )}
    </figure>
  )
}

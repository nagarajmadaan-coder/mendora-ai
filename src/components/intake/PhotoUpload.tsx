import { useRef, useState, type DragEvent } from 'react'
import Icon from '../Icon'
import PhotoThumbnail from './PhotoThumbnail'
import { useIntake } from '../../state/IntakeContext'
import { PHOTO_MAX_COUNT, PHOTO_MAX_MB, PHOTO_TYPES, checkPhotos } from '../../lib/validateIntake'

/*
  Optional photo picker with previews.
  - Click "Add photos" (opens the file picker / camera on phones) or drag files onto the box.
  - Files are checked for type, size and count; problems are listed clearly.
  - Photos are previewed here, and uploaded only when a signed-in person saves the request.
*/
export default function PhotoUpload() {
  const { photos, addPhotos, removePhoto } = useIntake()
  const [problems, setProblems] = useState<string[]>([])
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const full = photos.length >= PHOTO_MAX_COUNT

  function handleFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return
    const { accepted, problems } = checkPhotos(Array.from(fileList), photos.length)
    if (accepted.length) addPhotos(accepted)
    setProblems(problems)
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    if (!full) handleFiles(event.dataTransfer.files)
  }

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p id="photos-label" className="text-base font-semibold text-navy-900">
          3. Add photos <span className="font-normal text-navy-600">(optional)</span>
        </p>
        <p className="text-sm text-navy-600" aria-live="polite">
          {photos.length}/{PHOTO_MAX_COUNT} added
        </p>
      </div>
      <p id="photos-hint" className="mt-1 text-sm text-navy-600">
        A clear photo of the problem area helps. JPG, PNG or WebP, up to {PHOTO_MAX_MB} MB each.
      </p>

      {/* Drop zone. The real control is the visually-hidden file input + the visible button that opens it. */}
      {!full && (
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`mt-3 flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-4 py-7 text-center transition-colors ${
            dragging ? 'border-teal-600 bg-teal-50' : 'border-navy-900/20 bg-canvas'
          }`}
        >
          <span className="flex size-12 items-center justify-center rounded-full bg-white text-teal-700 ring-1 ring-navy-900/10">
            <Icon name="camera" className="size-6" />
          </span>
          <div>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              aria-describedby="photos-hint photos-privacy"
              className="inline-flex h-11 items-center gap-2 rounded-lg bg-white px-4 text-sm font-semibold text-navy-900 ring-1 ring-inset ring-navy-900/15 hover:bg-navy-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
            >
              <Icon name="upload" className="size-4" />
              Add photos
            </button>
            <p className="mt-2 hidden text-sm text-navy-600 sm:block">or drag and drop them here</p>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept={PHOTO_TYPES.join(',')}
            multiple
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
            data-testid="photo-input"
            onChange={(e) => {
              handleFiles(e.target.files)
              e.target.value = '' // allow picking the same file again after removing it
            }}
          />
        </div>
      )}

      {problems.length > 0 && (
        <div role="alert" className="mt-3 rounded-lg border border-red-700/20 bg-red-50 p-3 text-sm text-red-800">
          <ul className="space-y-1">
            {problems.map((problem) => (
              <li key={problem} className="flex items-start gap-1.5">
                <Icon name="alert" className="mt-0.5 size-4 shrink-0" />
                {problem}
              </li>
            ))}
          </ul>
        </div>
      )}

      {photos.length > 0 && (
        <ul aria-label="Photos added" className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {photos.map((photo) => (
            <li key={photo.id}>
              <PhotoThumbnail
                photo={photo}
                onRemove={() => {
                  removePhoto(photo.id)
                  setProblems([])
                }}
              />
            </li>
          ))}
        </ul>
      )}

      <p id="photos-privacy" className="mt-3 flex items-start gap-1.5 text-xs text-navy-600">
        <Icon name="lock" className="mt-px size-3.5 shrink-0" />
        Photos are saved with your request only if you’re signed in. Location data is removed, they’re never sent to the AI, and a technician sees them only after accepting your booking.
      </p>
    </div>
  )
}

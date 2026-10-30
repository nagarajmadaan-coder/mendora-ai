import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { EMPTY_INTAKE, type IntakeValues } from '../lib/validateIntake'
import type { ClarifyingAnswer, RepairRequest } from '../lib/api'
import type { TradeId } from '../types'

/*
  Shared memory for the repair-request DRAFT (what's being typed on the Diagnose screen).
  It lives above all pages, so the draft survives moving between screens — including
  going to sign in and coming back.

  Photos stay in the browser only (File objects + temporary "blob:" preview URLs).
  They are NOT uploaded or sent to the AI yet.

  `safetyAnswers` are the draft's answers to safety questions, kept so they aren't lost when
  the user signs in halfway through. The server always re-checks them.

  `lastRequest` is the most recent request saved on the server, so other screens
  (e.g. Resolution options) can link back to it.
*/

export interface PhotoItem {
  id: string
  file: File
  /** Temporary local preview URL (URL.createObjectURL) */
  url: string
}

interface IntakeStore {
  values: IntakeValues
  photos: PhotoItem[]
  lastRequest: RepairRequest | null
  safetyAnswers: ClarifyingAnswer[]
  /** Which trade + description the answers were given for (answers only apply to that exact text). */
  safetyAnswersKey: string
  setSafetyAnswers: (answers: ClarifyingAnswer[], key?: string) => void
  setValues: (values: IntakeValues) => void
  setTrade: (trade: TradeId) => void
  addPhotos: (files: File[]) => void
  removePhoto: (id: string) => void
  setLastRequest: (request: RepairRequest | null) => void
  /** Clears the draft and photos (after a successful save, or "start over"). */
  reset: () => void
}

const IntakeContext = createContext<IntakeStore | null>(null)

export function IntakeProvider({ children }: { children: ReactNode }) {
  const [values, setValues] = useState<IntakeValues>(EMPTY_INTAKE)
  const [photos, setPhotos] = useState<PhotoItem[]>([])
  const [lastRequest, setLastRequest] = useState<RepairRequest | null>(null)
  const [safety, setSafety] = useState<{ answers: ClarifyingAnswer[]; key: string }>({ answers: [], key: '' })
  const setSafetyAnswers = useCallback((answers: ClarifyingAnswer[], key = '') => setSafety({ answers, key }), [])
  const nextId = useRef(0)

  const setTrade = useCallback((trade: TradeId) => setValues((v) => ({ ...v, trade })), [])

  const addPhotos = useCallback((files: File[]) => {
    const items = files.map((file) => ({
      id: `photo-${++nextId.current}`,
      file,
      url: URL.createObjectURL(file),
    }))
    setPhotos((current) => [...current, ...items])
  }, [])

  const removePhoto = useCallback((id: string) => {
    setPhotos((current) => {
      const photo = current.find((p) => p.id === id)
      if (photo) URL.revokeObjectURL(photo.url) // free the browser memory used by the preview
      return current.filter((p) => p.id !== id)
    })
  }, [])

  const reset = useCallback(() => {
    setPhotos((current) => {
      current.forEach((p) => URL.revokeObjectURL(p.url))
      return []
    })
    setValues(EMPTY_INTAKE)
    setSafety({ answers: [], key: '' })
  }, [])

  const value = useMemo<IntakeStore>(
    () => ({
      values,
      photos,
      lastRequest,
      safetyAnswers: safety.answers,
      safetyAnswersKey: safety.key,
      setSafetyAnswers,
      setValues,
      setTrade,
      addPhotos,
      removePhoto,
      setLastRequest,
      reset,
    }),
    [values, photos, lastRequest, safety, setSafetyAnswers, setTrade, addPhotos, removePhoto, reset],
  )

  return <IntakeContext.Provider value={value}>{children}</IntakeContext.Provider>
}

export function useIntake(): IntakeStore {
  const ctx = useContext(IntakeContext)
  if (!ctx) throw new Error('useIntake must be used inside <IntakeProvider>')
  return ctx
}

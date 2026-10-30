import { isTradeId } from '../data/content'
import type { TradeId } from '../types'

/*
  Rules for the repair-intake form, kept separate from the form's layout
  so they are easy to read, test, and reuse later (e.g. on a backend).
*/

export const DESCRIPTION_MIN = 20
export const DESCRIPTION_MAX = 1000

export interface IntakeValues {
  trade: TradeId | ''
  description: string
}

export type IntakeErrors = Partial<Record<keyof IntakeValues, string>>

export const EMPTY_INTAKE: IntakeValues = { trade: '', description: '' }

export function validateIntake(values: IntakeValues): IntakeErrors {
  const errors: IntakeErrors = {}

  if (!isTradeId(values.trade)) {
    errors.trade = 'Please choose the type of problem: plumbing, electrical or carpentry.'
  }

  const description = values.description.trim()
  if (description.length === 0) {
    errors.description = 'Please describe the problem.'
  } else if (description.length < DESCRIPTION_MIN) {
    errors.description = `Please add a little more detail — at least ${DESCRIPTION_MIN} characters (you have ${description.length}).`
  } else if (description.length > DESCRIPTION_MAX) {
    errors.description = `Please keep the description under ${DESCRIPTION_MAX} characters.`
  }

  return errors
}

/* ---------- Photos (optional) ---------- */

export const PHOTO_MAX_COUNT = 3
export const PHOTO_MAX_MB = 10
export const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const

/**
 * Splits the files a person picked into the ones we can accept and
 * friendly messages for the ones we can't.
 */
export function checkPhotos(files: File[], alreadyAdded: number): { accepted: File[]; problems: string[] } {
  const accepted: File[] = []
  const problems: string[] = []

  for (const file of files) {
    if (!(PHOTO_TYPES as readonly string[]).includes(file.type)) {
      problems.push(`“${file.name}” isn’t a supported image. Please use JPG, PNG or WebP.`)
    } else if (file.size > PHOTO_MAX_MB * 1024 * 1024) {
      problems.push(`“${file.name}” is larger than ${PHOTO_MAX_MB} MB. Please choose a smaller photo.`)
    } else if (alreadyAdded + accepted.length >= PHOTO_MAX_COUNT) {
      problems.push(`You can add up to ${PHOTO_MAX_COUNT} photos, so “${file.name}” was not added.`)
    } else {
      accepted.push(file)
    }
  }
  return { accepted, problems }
}

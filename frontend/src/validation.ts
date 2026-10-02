// Mirrors the backend's checks so most mistakes are caught before a round trip.
import { sortKeyDates } from './conflicts'
import { SECTORS, STAGES, type EditableProject } from './types'

/** Keys: "name", "country", "sector", "stage", "key_dates", "key_dates.<i>.label", "key_dates.<i>.date". */
export type ValidationErrors = Record<string, string>

const DATE = /^\d{4}-\d{2}-\d{2}$/

export function validate(draft: EditableProject, base: EditableProject): ValidationErrors {
  const errors: ValidationErrors = {}
  if (!draft.name.trim()) errors.name = 'Name is required'
  if (!draft.country.trim()) errors.country = 'Country is required'
  if (!SECTORS.includes(draft.sector)) errors.sector = 'Choose a sector'
  if (!STAGES.includes(draft.stage)) errors.stage = 'Choose a stage'

  const seen = new Map<string, number>()
  draft.key_dates.forEach((kd, i) => {
    const label = kd.label.trim()
    if (!label) errors[`key_dates.${i}.label`] = 'Label is required'
    if (!DATE.test(kd.date)) errors[`key_dates.${i}.date`] = 'Date is required'
    if (label && seen.has(label)) errors[`key_dates.${i}.label`] = 'This label is already used'
    seen.set(label, i)
  })

  // Duplicates already stored (e.g. by the nightly import) are tolerated while the list is untouched.
  const hasDuplicateError = Object.values(errors).includes('This label is already used')
  if (hasDuplicateError && sameKeyDates(draft, base)) {
    for (const [key, message] of Object.entries(errors)) {
      if (message === 'This label is already used') delete errors[key]
    }
  }
  return errors
}

function sameKeyDates(a: EditableProject, b: EditableProject): boolean {
  const normalized = (p: EditableProject) =>
    JSON.stringify(sortKeyDates(p.key_dates.map((kd) => ({ label: kd.label.trim(), date: kd.date }))))
  return normalized(a) === normalized(b)
}

// Mirrors the backend's checks so most mistakes are caught before a round trip.
import { sortCompanies, sortKeyDates } from './conflicts'
import { COMPANY_ROLES, SECTORS, STAGES, type EditableProject } from './types'

/**
 * Keys: "name", "country", "sector", "stage", "key_dates.<i>.label", "key_dates.<i>.date",
 * "linked_companies.<i>.name", "linked_companies.<i>.role".
 */
export type ValidationErrors = Record<string, string>

const DATE = /^\d{4}-\d{2}-\d{2}$/
const DUPLICATE_LABEL = 'This label is already used'
const DUPLICATE_COMPANY = 'This company is already linked'

export function validate(draft: EditableProject, base: EditableProject): ValidationErrors {
  const errors: ValidationErrors = {}
  if (!draft.name.trim()) errors.name = 'Name is required'
  if (!draft.country.trim()) errors.country = 'Country is required'
  if (!SECTORS.includes(draft.sector)) errors.sector = 'Choose a sector'
  if (!STAGES.includes(draft.stage)) errors.stage = 'Choose a stage'

  const labels = new Set<string>()
  draft.key_dates.forEach((kd, i) => {
    const label = kd.label.trim()
    if (!label) errors[`key_dates.${i}.label`] = 'Label is required'
    if (!DATE.test(kd.date)) errors[`key_dates.${i}.date`] = 'Date is required'
    if (label && labels.has(label)) errors[`key_dates.${i}.label`] = DUPLICATE_LABEL
    labels.add(label)
  })

  const names = new Set<string>()
  draft.linked_companies.forEach((c, i) => {
    const name = c.name.trim()
    if (!name) errors[`linked_companies.${i}.name`] = 'Company name is required'
    if (!COMPANY_ROLES.includes(c.role)) errors[`linked_companies.${i}.role`] = 'Choose a role'
    if (name && names.has(name)) errors[`linked_companies.${i}.name`] = DUPLICATE_COMPANY
    names.add(name)
  })

  // Duplicates already stored (e.g. by the nightly import) are tolerated while the list is untouched.
  if (same(sortKeyDates, draft.key_dates.map((kd) => ({ ...kd, label: kd.label.trim() })), base.key_dates)) {
    dropErrors(errors, DUPLICATE_LABEL)
  }
  if (same(sortCompanies, draft.linked_companies.map((c) => ({ ...c, name: c.name.trim() })), base.linked_companies)) {
    dropErrors(errors, DUPLICATE_COMPANY)
  }
  return errors
}

function same<T>(sort: (items: T[]) => T[], a: T[], b: T[]): boolean {
  return JSON.stringify(sort(a)) === JSON.stringify(sort(b))
}

function dropErrors(errors: ValidationErrors, message: string) {
  for (const [key, value] of Object.entries(errors)) {
    if (value === message) delete errors[key]
  }
}

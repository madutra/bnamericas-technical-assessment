import {
  humanize,
  type Conflict,
  type EditableProject,
  type KeyDate,
  type LinkedCompany,
  type ListFieldName,
  type SlotValue,
} from './types'

export type Choice = 'mine' | 'theirs'

export function sortKeyDates(keyDates: KeyDate[]): KeyDate[] {
  return [...keyDates].sort((a, b) => a.date.localeCompare(b.date) || a.label.localeCompare(b.label))
}

export function sortCompanies(companies: LinkedCompany[]): LinkedCompany[] {
  return [...companies].sort((a, b) => a.name.localeCompare(b.name) || a.role.localeCompare(b.role))
}

type Item = KeyDate | LinkedCompany

/** What identifies an item in each list (mirrors backend/app/merge.py). */
function identity(field: ListFieldName, item: Item): string {
  return field === 'key_dates' ? (item as KeyDate).label : (item as LinkedCompany).name
}

/**
 * What to resend after a 409. `merged` already holds theirs for every conflicting slot and mine for
 * everything else, so only the slots where the user picked "mine" need changing.
 */
export function applyChoices(merged: EditableProject, conflicts: Conflict[], choices: Record<string, Choice>): EditableProject {
  const result: EditableProject = {
    ...merged,
    key_dates: [...merged.key_dates],
    linked_companies: [...merged.linked_companies],
  }
  for (const conflict of conflicts) {
    const choice = choices[conflict.slot]
    if (!choice) throw new Error(`No choice for ${conflict.slot}`)
    if (choice === 'theirs') continue

    const field = conflict.field
    if (field !== 'key_dates' && field !== 'linked_companies') {
      Object.assign(result, { [field]: conflict.mine })
    } else if (conflict.key === null) {
      Object.assign(result, { [field]: [...((conflict.mine as Item[] | null) ?? [])] })
    } else {
      // `merged` holds their version of this item (possibly renamed, or absent): swap it for mine.
      const theirs = conflict.theirs as Item | null
      const mine = conflict.mine as Item | null
      let items = result[field] as Item[]
      if (theirs) items = items.filter((item) => identity(field, item) !== identity(field, theirs))
      if (mine) items = [...items, { ...mine }]
      Object.assign(result, { [field]: items })
    }
  }
  result.key_dates = sortKeyDates(result.key_dates)
  result.linked_companies = sortCompanies(result.linked_companies)
  return result
}

function describeItem(item: Item): string {
  return 'date' in item ? `${item.label}: ${item.date}` : `${item.name} · ${humanize(item.role)}`
}

export function describeValue(field: Conflict['field'], value: SlotValue): string {
  if (value === null) return '(removed)'
  if (Array.isArray(value)) {
    const empty = field === 'key_dates' ? '(no dates)' : '(no companies)'
    return value.map(describeItem).join(', ') || empty
  }
  if (typeof value === 'object') return describeItem(value)
  return field === 'sector' || field === 'stage' ? humanize(value) : value
}

export function conflictTitle(conflict: Conflict): string {
  if (conflict.field === 'key_dates') {
    return conflict.key === null ? 'Key dates (whole list)' : `Key date "${conflict.key}"`
  }
  if (conflict.field === 'linked_companies') {
    return conflict.key === null ? 'Linked companies (whole list)' : `Company "${conflict.key}"`
  }
  return humanize(conflict.field)
}

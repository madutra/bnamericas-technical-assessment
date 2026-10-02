import { humanize, type Conflict, type EditableProject, type KeyDate, type SlotValue } from './types'

export type Choice = 'mine' | 'theirs'

export function sortKeyDates(keyDates: KeyDate[]): KeyDate[] {
  return [...keyDates].sort((a, b) => a.date.localeCompare(b.date) || a.label.localeCompare(b.label))
}

/**
 * What to resend after a 409. `merged` already holds theirs for every conflicting slot and mine for
 * everything else, so only the slots where the user picked "mine" need changing.
 */
export function applyChoices(merged: EditableProject, conflicts: Conflict[], choices: Record<string, Choice>): EditableProject {
  const result: EditableProject = { ...merged, key_dates: [...merged.key_dates] }
  for (const conflict of conflicts) {
    const choice = choices[conflict.slot]
    if (!choice) throw new Error(`No choice for ${conflict.slot}`)
    if (choice === 'theirs') continue

    if (conflict.field !== 'key_dates') {
      Object.assign(result, { [conflict.field]: conflict.mine })
    } else if (conflict.label === null) {
      result.key_dates = [...((conflict.mine as KeyDate[] | null) ?? [])]
    } else {
      const label = conflict.label
      result.key_dates = result.key_dates.filter((kd) => kd.label !== label)
      if (conflict.mine !== null) result.key_dates.push({ label, date: conflict.mine as string })
    }
  }
  result.key_dates = sortKeyDates(result.key_dates)
  return result
}

export function describeValue(field: Conflict['field'], value: SlotValue): string {
  if (value === null) return '(removed)'
  if (Array.isArray(value)) return value.map((kd) => `${kd.label}: ${kd.date}`).join(', ') || '(no dates)'
  return field === 'sector' || field === 'stage' ? humanize(value) : value
}

export function conflictTitle(conflict: Conflict): string {
  if (conflict.field !== 'key_dates') return humanize(conflict.field)
  return conflict.label === null ? 'Key dates (whole list)' : `Key date "${conflict.label}"`
}

import { applyChoices, conflictTitle, describeValue } from './conflicts'
import type { Conflict, EditableProject } from './types'

const merged: EditableProject = {
  name: 'Theirs',
  sector: 'energy',
  country: 'Peru',
  stage: 'financing',
  key_dates: [
    { label: 'Tender launch', date: '2026-03-01' },
    { label: 'Financial close', date: '2026-07-01' },
  ],
}

const nameConflict: Conflict = { slot: 'name', field: 'name', label: null, base: 'Base', mine: 'Mine', theirs: 'Theirs' }
const dateConflict: Conflict = {
  slot: 'key_dates[Tender launch]', field: 'key_dates', label: 'Tender launch',
  base: '2026-01-10', mine: '2026-02-01', theirs: '2026-03-01',
}

test('choosing theirs keeps merged as it is', () => {
  expect(applyChoices(merged, [nameConflict], { name: 'theirs' })).toEqual(merged)
})

test('choosing mine on a scalar field', () => {
  expect(applyChoices(merged, [nameConflict], { name: 'mine' }).name).toBe('Mine')
})

test('choosing mine on a key date re-dates only that label', () => {
  const result = applyChoices(merged, [dateConflict], { [dateConflict.slot]: 'mine' })
  expect(result.key_dates).toEqual([
    { label: 'Tender launch', date: '2026-02-01' },
    { label: 'Financial close', date: '2026-07-01' },
  ])
})

test('choosing mine when I deleted the date removes it', () => {
  const deleted = { ...dateConflict, mine: null }
  const result = applyChoices(merged, [deleted], { [deleted.slot]: 'mine' })
  expect(result.key_dates.map((kd) => kd.label)).toEqual(['Financial close'])
})

test('choosing mine when they deleted the date brings it back, sorted by date', () => {
  const theirsDeleted = { ...dateConflict, theirs: null }
  const withoutIt = { ...merged, key_dates: [merged.key_dates[1]] }
  const result = applyChoices(withoutIt, [theirsDeleted], { [theirsDeleted.slot]: 'mine' })
  expect(result.key_dates[0]).toEqual({ label: 'Tender launch', date: '2026-02-01' })
})

test('choosing mine on the whole-list fallback replaces the list', () => {
  const mine = [{ label: 'Only', date: '2027-01-01' }]
  const whole: Conflict = { slot: 'key_dates', field: 'key_dates', label: null, base: [], mine, theirs: merged.key_dates }
  expect(applyChoices(merged, [whole], { key_dates: 'mine' }).key_dates).toEqual(mine)
})

test('a missing choice is an error, never a silent default', () => {
  expect(() => applyChoices(merged, [nameConflict], {})).toThrow('No choice for name')
})

test('describes values and titles for the dialog', () => {
  expect(describeValue('stage', 'oil_and_gas')).toBe('Oil and gas')
  expect(describeValue('name', 'my_project')).toBe('my_project')
  expect(describeValue('key_dates', null)).toBe('(removed)')
  expect(conflictTitle(dateConflict)).toBe('Key date "Tender launch"')
})

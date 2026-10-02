import type { EditableProject } from './types'
import { validate } from './validation'

const base: EditableProject = {
  name: 'Project',
  sector: 'energy',
  country: 'Chile',
  stage: 'idea',
  key_dates: [{ label: 'Tender launch', date: '2026-01-10' }],
}

test('a valid project has no errors', () => {
  expect(validate(base, base)).toEqual({})
})

test('required fields', () => {
  const errors = validate({ ...base, name: '  ', country: '' }, base)
  expect(errors).toEqual({ name: 'Name is required', country: 'Country is required' })
})

test('key date rows need a label and a date', () => {
  const errors = validate({ ...base, key_dates: [{ label: '', date: '' }] }, base)
  expect(errors).toEqual({ 'key_dates.0.label': 'Label is required', 'key_dates.0.date': 'Date is required' })
})

test('a new duplicate label is rejected, comparing trimmed labels', () => {
  const draft = { ...base, key_dates: [...base.key_dates, { label: ' Tender launch ', date: '2026-05-05' }] }
  expect(validate(draft, base)).toEqual({ 'key_dates.1.label': 'This label is already used' })
})

test('labels are case-sensitive', () => {
  const draft = { ...base, key_dates: [...base.key_dates, { label: 'tender launch', date: '2026-05-05' }] }
  expect(validate(draft, base)).toEqual({})
})

test('duplicates already stored are tolerated while the list is untouched', () => {
  const stored = { ...base, key_dates: [...base.key_dates, { label: 'Tender launch', date: '2026-05-05' }] }
  expect(validate({ ...stored, name: 'Renamed' }, stored)).toEqual({})
})

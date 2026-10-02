import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Conflict } from '../types'
import ConflictDialog from './ConflictDialog'

const conflicts: Conflict[] = [
  { slot: 'name', field: 'name', label: null, base: 'Base', mine: 'Mine', theirs: 'Theirs' },
  {
    slot: 'key_dates[Tender launch]', field: 'key_dates', label: 'Tender launch',
    base: '2026-01-10', mine: null, theirs: '2026-03-01',
  },
]

test('nothing is preselected and saving waits for every choice', async () => {
  const onResolve = jest.fn()
  render(<ConflictDialog conflicts={conflicts} onResolve={onResolve} onCancel={jest.fn()} />)

  expect(screen.getAllByRole('radio').every((r) => !(r as HTMLInputElement).checked)).toBe(true)
  const save = screen.getByRole('button', { name: 'Save with these choices' })
  expect(save).toBeDisabled()

  await userEvent.click(screen.getByLabelText('Mine: Mine'))
  expect(save).toBeDisabled()
  await userEvent.click(screen.getByLabelText('Theirs: 2026-03-01'))
  expect(save).toBeEnabled()

  await userEvent.click(save)
  expect(onResolve).toHaveBeenCalledWith({ name: 'mine', 'key_dates[Tender launch]': 'theirs' })
})

test('shows what each side has, including a removed date', () => {
  render(<ConflictDialog conflicts={conflicts} onResolve={jest.fn()} onCancel={jest.fn()} />)
  expect(screen.getByText('Key date "Tender launch"')).toBeInTheDocument()
  expect(screen.getByLabelText('Mine: (removed)')).toBeInTheDocument()
  expect(screen.getByText('When you opened it: Base')).toBeInTheDocument()
})

test('cancel', async () => {
  const onCancel = jest.fn()
  render(<ConflictDialog conflicts={conflicts} onResolve={jest.fn()} onCancel={onCancel} />)
  await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(onCancel).toHaveBeenCalled()
})

import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import * as api from '../api'
import type { Project } from '../types'
import ProjectEditPage from './ProjectEditPage'

jest.mock('../api', () => {
  const actual = jest.requireActual('../api')
  // Keep the real error classes so `instanceof` works in the page.
  return { ...actual, getProject: jest.fn(), saveProject: jest.fn() }
})

const getProject = api.getProject as jest.MockedFunction<typeof api.getProject>
const saveProject = api.saveProject as jest.MockedFunction<typeof api.saveProject>

const stored: Project = {
  id: 'P-1',
  name: 'Original',
  sector: 'energy',
  country: 'Chile',
  stage: 'idea',
  key_dates: [{ label: 'Tender launch', date: '2026-01-10' }],
  linked_companies: [{ name: 'Varelo Energia SA', role: 'owner' }],
}
const { id: _id, ...editable } = stored

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/projects/P-1']}>
      <Routes>
        <Route path="/projects/:id" element={<ProjectEditPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

async function rename(to: string) {
  const name = await screen.findByLabelText('Name')
  await userEvent.clear(name)
  await userEvent.type(name, to)
}

beforeEach(() => {
  jest.resetAllMocks()
  getProject.mockResolvedValue(stored)
})

test('shows the project with its linked companies, and Save is off until something changes', async () => {
  renderPage()
  expect(await screen.findByDisplayValue('Original')).toBeInTheDocument()
  expect(screen.getByDisplayValue('Varelo Energia SA')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
})

test('saves base and proposed', async () => {
  saveProject.mockResolvedValue({ ...stored, name: 'Renamed' })
  renderPage()
  await rename('Renamed')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(saveProject).toHaveBeenCalledWith('P-1', editable, { ...editable, name: 'Renamed' })
  expect(await screen.findByText('Saved')).toBeInTheDocument()
})

test('does not send an invalid form', async () => {
  renderPage()
  await rename(' ')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByText('Name is required')).toBeInTheDocument()
  expect(saveProject).not.toHaveBeenCalled()
})

test('on a conflict, choosing mine resends against the current version', async () => {
  const current = { ...stored, name: 'Theirs', country: 'Peru' }
  const { id: _i, ...currentEditable } = current
  saveProject
    .mockRejectedValueOnce(new api.SaveConflictError({
      current,
      merged: { ...currentEditable, name: 'Theirs' },
      conflicts: [{ slot: 'name', field: 'name', key: null, base: 'Original', mine: 'Mine', theirs: 'Theirs' }],
    }))
    .mockResolvedValueOnce({ ...current, name: 'Mine' })

  renderPage()
  await rename('Mine')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))
  await userEvent.click(await screen.findByLabelText('Mine: Mine'))
  await userEvent.click(screen.getByRole('button', { name: 'Save with these choices' }))

  await waitFor(() => expect(saveProject).toHaveBeenCalledTimes(2))
  expect(saveProject).toHaveBeenLastCalledWith('P-1', currentEditable, { ...currentEditable, name: 'Mine' })
  expect(await screen.findByDisplayValue('Mine')).toBeInTheDocument()
  expect(screen.getByDisplayValue('Peru')).toBeInTheDocument()
})

test('an unconfirmed save shows the message and offers a reload', async () => {
  saveProject.mockRejectedValue(new api.ApiError(504, 'The save could not be confirmed.'))
  renderPage()
  await rename('Renamed')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByText('The save could not be confirmed.')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Reload' }))
  expect(getProject).toHaveBeenCalledTimes(2)
})

test('a slow save says it is still confirming', async () => {
  jest.useFakeTimers()
  let finish: (p: Project) => void = () => {}
  saveProject.mockReturnValue(new Promise((resolve) => (finish = resolve)))
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
  renderPage()
  const name = await screen.findByLabelText('Name')
  await user.type(name, '!')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  act(() => jest.advanceTimersByTime(3000))
  expect(screen.getByText(/Still confirming/)).toBeInTheDocument()
  await act(async () => finish(stored))
  expect(screen.queryByText(/Still confirming/)).not.toBeInTheDocument()
  jest.useRealTimers()
})

test('adding a linked company sends it with the save', async () => {
  saveProject.mockResolvedValue(stored)
  renderPage()
  await screen.findByDisplayValue('Original')
  await userEvent.click(screen.getByRole('button', { name: 'Add company' }))
  const names = screen.getAllByLabelText('Company')
  await userEvent.type(names[names.length - 1], 'Nueva Ingenieria SAS')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(saveProject).toHaveBeenCalledWith('P-1', editable, {
    ...editable,
    linked_companies: [...editable.linked_companies, { name: 'Nueva Ingenieria SAS', role: 'owner' }],
  })
})

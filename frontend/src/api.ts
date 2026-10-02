// The only module that calls fetch. Always our own backend under /api, never the upstream.
import type { ConflictResponse, EditableProject, Project, ProjectSummary } from './types'

export class ApiError extends Error {
  status: number

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
  }
}

export class SaveConflictError extends Error {
  conflict: ConflictResponse

  constructor(conflict: ConflictResponse) {
    super('Someone else changed the same fields')
    this.conflict = conflict
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(0, 'Could not reach the server.')
  }
  const body = await response.json().catch(() => null)
  if (response.status === 409 && body) throw new SaveConflictError(body as ConflictResponse)
  if (!response.ok) throw new ApiError(response.status, body?.detail ?? `Request failed (${response.status})`)
  return body as T
}

export function listProjects(): Promise<ProjectSummary[]> {
  return request('/projects')
}

export function getProject(id: string): Promise<Project> {
  return request(`/projects/${encodeURIComponent(id)}`)
}

/** `base` is the version the editor loaded; the backend merges `proposed` onto what is stored now. */
export function saveProject(id: string, base: EditableProject, proposed: EditableProject): Promise<Project> {
  return request(`/projects/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify({ base, proposed }),
  })
}

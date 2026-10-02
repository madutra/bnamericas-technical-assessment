// Mirrors backend/app/schemas.py.

export const SECTORS = ['energy', 'mining', 'water', 'transport', 'oil_and_gas', 'ict'] as const
export const STAGES = ['idea', 'feasibility', 'tender', 'financing', 'construction', 'operation', 'cancelled'] as const

export type Sector = (typeof SECTORS)[number]
export type Stage = (typeof STAGES)[number]

export interface KeyDate {
  label: string
  date: string // YYYY-MM-DD
}

export interface LinkedCompany {
  name: string
  role: string
}

export interface EditableProject {
  name: string
  sector: Sector
  country: string
  stage: Stage
  key_dates: KeyDate[]
}

export interface Project extends EditableProject {
  id: string
  linked_companies: LinkedCompany[]
}

export interface ProjectSummary {
  id: string
  name: string
  sector: Sector
  country: string
  stage: Stage
}

export type SlotValue = string | KeyDate[] | null

export interface Conflict {
  slot: string
  field: 'name' | 'sector' | 'country' | 'stage' | 'key_dates'
  label: string | null // a single key date; null for scalars and the whole-list fallback
  base: SlotValue
  mine: SlotValue
  theirs: SlotValue
}

export interface ConflictResponse {
  current: Project
  merged: EditableProject
  conflicts: Conflict[]
}

export function editableOf(project: EditableProject): EditableProject {
  const { name, sector, country, stage, key_dates } = project
  return { name, sector, country, stage, key_dates: key_dates.map((kd) => ({ ...kd })) }
}

const SPECIAL_LABELS: Record<string, string> = { ict: 'ICT', oil_and_gas: 'Oil and gas' }

/** "epc_contractor" → "Epc contractor", with a few exceptions. */
export function humanize(value: string): string {
  if (SPECIAL_LABELS[value]) return SPECIAL_LABELS[value]
  const words = value.replaceAll('_', ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

// Mirrors backend/app/schemas.py.

export const SECTORS = ['energy', 'mining', 'water', 'transport', 'oil_and_gas', 'ict'] as const
export const STAGES = ['idea', 'feasibility', 'tender', 'financing', 'construction', 'operation', 'cancelled'] as const
export const COMPANY_ROLES = ['owner', 'developer', 'epc_contractor', 'financier', 'consultant'] as const

export type Sector = (typeof SECTORS)[number]
export type Stage = (typeof STAGES)[number]
export type CompanyRole = (typeof COMPANY_ROLES)[number]

export interface KeyDate {
  label: string
  date: string // YYYY-MM-DD
}

export interface LinkedCompany {
  name: string
  role: CompanyRole
}

export interface EditableProject {
  name: string
  sector: Sector
  country: string
  stage: Stage
  key_dates: KeyDate[]
  linked_companies: LinkedCompany[]
}

export interface Project extends EditableProject {
  id: string
}

export interface ProjectSummary {
  id: string
  name: string
  sector: Sector
  country: string
  stage: Stage
}

// A scalar's value, one list item, a whole list (fallback), or null = absent.
export type SlotValue = string | KeyDate | LinkedCompany | KeyDate[] | LinkedCompany[] | null

export type ListFieldName = 'key_dates' | 'linked_companies'

export interface Conflict {
  slot: string
  field: 'name' | 'sector' | 'country' | 'stage' | ListFieldName
  // A single list item: its identity in `base` (key-date label or company name). Each side's value may
  // carry a different label/name when that side renamed it. null for scalars and the whole-list fallback.
  key: string | null
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
  const { name, sector, country, stage, key_dates, linked_companies } = project
  return {
    name, sector, country, stage,
    key_dates: key_dates.map((kd) => ({ ...kd })),
    linked_companies: linked_companies.map((c) => ({ ...c })),
  }
}

const SPECIAL_LABELS: Record<string, string> = { ict: 'ICT', oil_and_gas: 'Oil and gas', epc_contractor: 'EPC contractor' }

/** "epc_contractor" → "Epc contractor", with a few exceptions. */
export function humanize(value: string): string {
  if (SPECIAL_LABELS[value]) return SPECIAL_LABELS[value]
  const words = value.replaceAll('_', ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import SaveIcon from '@mui/icons-material/Save'
import {
  Alert,
  Button,
  CircularProgress,
  Divider,
  MenuItem,
  Paper,
  Snackbar,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useCallback, useEffect, useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'
import { ApiError, SaveConflictError, getProject, saveProject } from '../api'
import ConflictDialog from '../components/ConflictDialog'
import KeyDatesEditor from '../components/KeyDatesEditor'
import LinkedCompaniesEditor from '../components/LinkedCompaniesEditor'
import { applyChoices, type Choice } from '../conflicts'
import { SECTORS, STAGES, editableOf, humanize, type ConflictResponse, type EditableProject, type Project } from '../types'
import { validate } from '../validation'

const SLOW_SAVE_MS = 3000

export default function ProjectEditPage() {
  const { id = '' } = useParams()
  const [project, setProject] = useState<Project | null>(null)
  // `base` is the last version loaded or saved; the backend merges `draft` onto what is stored now.
  const [base, setBase] = useState<EditableProject | null>(null)
  const [draft, setDraft] = useState<EditableProject | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [slowSave, setSlowSave] = useState(false)
  const [saveError, setSaveError] = useState<ApiError | null>(null)
  const [conflict, setConflict] = useState<ConflictResponse | null>(null)
  const [showErrors, setShowErrors] = useState(false)
  const [saved, setSaved] = useState(false)

  const showLoaded = (loaded: Project) => {
    setProject(loaded)
    setBase(editableOf(loaded))
    setDraft(editableOf(loaded))
  }

  const load = useCallback(
    () =>
      getProject(id)
        .then(showLoaded)
        .catch((e: Error) => setLoadError(e.message)),
    [id],
  )

  useEffect(() => {
    load()
  }, [load])

  function reload() {
    setSaveError(null)
    load()
  }

  if (loadError) return <Alert severity="error">{loadError}</Alert>
  if (!project || !base || !draft) return <CircularProgress aria-label="Loading project" />

  const errors = validate(draft, base)
  const visibleErrors = showErrors ? errors : {}
  const dirty = JSON.stringify(draft) !== JSON.stringify(base)

  async function submit(baseToSend: EditableProject, proposed: EditableProject) {
    setSaving(true)
    setSaveError(null)
    const timer = setTimeout(() => setSlowSave(true), SLOW_SAVE_MS)
    try {
      showLoaded(await saveProject(id, baseToSend, proposed))
      setShowErrors(false)
      setSaved(true)
    } catch (e) {
      if (e instanceof SaveConflictError) setConflict(e.conflict)
      else setSaveError(e instanceof ApiError ? e : new ApiError(0, String(e)))
    } finally {
      clearTimeout(timer)
      setSaving(false)
      setSlowSave(false)
    }
  }

  function onSave() {
    setShowErrors(true)
    if (Object.keys(errors).length === 0) submit(base!, draft!)
  }

  function onResolve(choices: Record<string, Choice>) {
    const { current, merged, conflicts } = conflict!
    const proposed = applyChoices(merged, conflicts, choices)
    setConflict(null)
    // From now on we edit on top of what is stored.
    setProject(current)
    setBase(editableOf(current))
    setDraft(proposed)
    submit(editableOf(current), proposed)
  }

  const set = (patch: Partial<EditableProject>) => setDraft({ ...draft, ...patch })

  return (
    <Stack spacing={2}>
      <div>
        <Button component={RouterLink} to="/" startIcon={<ArrowBackIcon />}>
          All projects
        </Button>
      </div>
      <Typography variant="h5" component="h1">
        {project.name} <Typography component="span" color="text.secondary">{project.id}</Typography>
      </Typography>

      <Paper sx={{ p: 3 }}>
        <Stack spacing={2}>
          <TextField label="Name" value={draft.name} disabled={saving} onChange={(e) => set({ name: e.target.value })}
            error={Boolean(visibleErrors.name)} helperText={visibleErrors.name} />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField select label="Sector" value={draft.sector} disabled={saving} sx={{ flex: 1 }}
              onChange={(e) => set({ sector: e.target.value as EditableProject['sector'] })}>
              {SECTORS.map((s) => <MenuItem key={s} value={s}>{humanize(s)}</MenuItem>)}
            </TextField>
            <TextField select label="Stage" value={draft.stage} disabled={saving} sx={{ flex: 1 }}
              onChange={(e) => set({ stage: e.target.value as EditableProject['stage'] })}>
              {STAGES.map((s) => <MenuItem key={s} value={s}>{humanize(s)}</MenuItem>)}
            </TextField>
            <TextField label="Country" value={draft.country} disabled={saving} sx={{ flex: 1 }}
              onChange={(e) => set({ country: e.target.value })}
              error={Boolean(visibleErrors.country)} helperText={visibleErrors.country} />
          </Stack>

          <Divider />
          <KeyDatesEditor keyDates={draft.key_dates} errors={visibleErrors} disabled={saving}
            onChange={(key_dates) => set({ key_dates })} />

          <Divider />
          <LinkedCompaniesEditor companies={draft.linked_companies} errors={visibleErrors} disabled={saving}
            onChange={(linked_companies) => set({ linked_companies })} />

          {saveError && (
            <Alert severity="error" action={saveError.status === 504 ? <Button color="inherit" onClick={reload}>Reload</Button> : undefined}>
              {saveError.message}
            </Alert>
          )}
          {slowSave && <Alert severity="info">Still confirming the save with the records service…</Alert>}

          <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
            <Button variant="contained" startIcon={saving ? <CircularProgress size={18} /> : <SaveIcon />}
              disabled={saving || !dirty} onClick={onSave}>
              {saving ? 'Saving…' : 'Save'}
            </Button>
            <Button disabled={saving || !dirty} onClick={() => setDraft(editableOf(base))}>Discard changes</Button>
          </Stack>
        </Stack>
      </Paper>

      {conflict && (
        <ConflictDialog conflicts={conflict.conflicts} onResolve={onResolve} onCancel={() => setConflict(null)} />
      )}
      <Snackbar open={saved} autoHideDuration={3000} onClose={() => setSaved(false)} message="Saved" />
    </Stack>
  )
}

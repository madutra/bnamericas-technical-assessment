import AddIcon from '@mui/icons-material/Add'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import { Button, IconButton, Stack, TextField, Typography } from '@mui/material'
import type { KeyDate } from '../types'
import type { ValidationErrors } from '../validation'

interface Props {
  keyDates: KeyDate[]
  errors: ValidationErrors
  disabled?: boolean
  onChange: (keyDates: KeyDate[]) => void
}

export default function KeyDatesEditor({ keyDates, errors, disabled, onChange }: Props) {
  const update = (index: number, patch: Partial<KeyDate>) =>
    onChange(keyDates.map((kd, i) => (i === index ? { ...kd, ...patch } : kd)))

  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle1">Key dates</Typography>
      {keyDates.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          No key dates.
        </Typography>
      )}
      {keyDates.map((kd, i) => (
        <Stack key={i} direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
          <TextField
            label="Label"
            size="small"
            value={kd.label}
            disabled={disabled}
            onChange={(e) => update(i, { label: e.target.value })}
            error={Boolean(errors[`key_dates.${i}.label`])}
            helperText={errors[`key_dates.${i}.label`]}
            sx={{ flex: 1 }}
          />
          <TextField
            label="Date"
            type="date"
            size="small"
            value={kd.date}
            disabled={disabled}
            onChange={(e) => update(i, { date: e.target.value })}
            error={Boolean(errors[`key_dates.${i}.date`])}
            helperText={errors[`key_dates.${i}.date`]}
            slotProps={{ inputLabel: { shrink: true } }}
            sx={{ width: 180 }}
          />
          <IconButton
            aria-label={`Remove ${kd.label || 'key date'}`}
            disabled={disabled}
            onClick={() => onChange(keyDates.filter((_, j) => j !== i))}
          >
            <DeleteOutlineIcon />
          </IconButton>
        </Stack>
      ))}
      <div>
        <Button
          startIcon={<AddIcon />}
          disabled={disabled}
          onClick={() => onChange([...keyDates, { label: '', date: '' }])}
        >
          Add key date
        </Button>
      </div>
    </Stack>
  )
}

import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  Typography,
} from '@mui/material'
import { useState } from 'react'
import { conflictTitle, describeValue, type Choice } from '../conflicts'
import type { Conflict } from '../types'

interface Props {
  conflicts: Conflict[]
  onResolve: (choices: Record<string, Choice>) => void
  onCancel: () => void
}

/** One row per conflict. Nothing is preselected, so the person saving second has to decide. */
export default function ConflictDialog({ conflicts, onResolve, onCancel }: Props) {
  const [choices, setChoices] = useState<Record<string, Choice>>({})
  const allChosen = conflicts.every((c) => choices[c.slot])

  return (
    <Dialog open onClose={onCancel} maxWidth="sm" fullWidth>
      <DialogTitle>Someone else changed the same fields</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 2 }}>
          Your other changes are kept. For each field below, choose which value to save.
        </Typography>
        <Stack spacing={2}>
          {conflicts.map((conflict) => (
            <div key={conflict.slot}>
              <Typography variant="subtitle2">{conflictTitle(conflict)}</Typography>
              <Typography variant="caption" color="text.secondary">
                When you opened it: {describeValue(conflict.field, conflict.base)}
              </Typography>
              <RadioGroup
                aria-label={conflictTitle(conflict)}
                value={choices[conflict.slot] ?? ''}
                onChange={(e) => setChoices({ ...choices, [conflict.slot]: e.target.value as Choice })}
              >
                <FormControlLabel value="theirs" control={<Radio />} label={`Theirs: ${describeValue(conflict.field, conflict.theirs)}`} />
                <FormControlLabel value="mine" control={<Radio />} label={`Mine: ${describeValue(conflict.field, conflict.mine)}`} />
              </RadioGroup>
            </div>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel}>Cancel</Button>
        <Button variant="contained" disabled={!allChosen} onClick={() => onResolve(choices)}>
          Save with these choices
        </Button>
      </DialogActions>
    </Dialog>
  )
}

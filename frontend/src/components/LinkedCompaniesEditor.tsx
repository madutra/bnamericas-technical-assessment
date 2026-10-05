import AddIcon from '@mui/icons-material/Add'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import { Button, IconButton, MenuItem, Stack, TextField, Typography } from '@mui/material'
import { COMPANY_ROLES, humanize, type CompanyRole, type LinkedCompany } from '../types'
import type { ValidationErrors } from '../validation'

interface Props {
  companies: LinkedCompany[]
  errors: ValidationErrors
  disabled?: boolean
  onChange: (companies: LinkedCompany[]) => void
}

export default function LinkedCompaniesEditor({ companies, errors, disabled, onChange }: Props) {
  const update = (index: number, patch: Partial<LinkedCompany>) =>
    onChange(companies.map((c, i) => (i === index ? { ...c, ...patch } : c)))

  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle1">Linked companies</Typography>
      {companies.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          No linked companies.
        </Typography>
      )}
      {companies.map((c, i) => (
        <Stack key={i} direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
          <TextField
            label="Company"
            size="small"
            value={c.name}
            disabled={disabled}
            onChange={(e) => update(i, { name: e.target.value })}
            error={Boolean(errors[`linked_companies.${i}.name`])}
            helperText={errors[`linked_companies.${i}.name`]}
            sx={{ flex: 1 }}
          />
          <TextField
            select
            label="Role"
            size="small"
            value={c.role}
            disabled={disabled}
            onChange={(e) => update(i, { role: e.target.value as CompanyRole })}
            error={Boolean(errors[`linked_companies.${i}.role`])}
            helperText={errors[`linked_companies.${i}.role`]}
            sx={{ width: 180 }}
          >
            {COMPANY_ROLES.map((role) => (
              <MenuItem key={role} value={role}>
                {humanize(role)}
              </MenuItem>
            ))}
          </TextField>
          <IconButton
            aria-label={`Remove ${c.name || 'company'}`}
            disabled={disabled}
            onClick={() => onChange(companies.filter((_, j) => j !== i))}
          >
            <DeleteOutlineIcon />
          </IconButton>
        </Stack>
      ))}
      <div>
        <Button
          startIcon={<AddIcon />}
          disabled={disabled}
          onClick={() => onChange([...companies, { name: '', role: 'owner' }])}
        >
          Add company
        </Button>
      </div>
    </Stack>
  )
}

import { AppBar, Container, CssBaseline, ThemeProvider, Toolbar, Typography, createTheme } from '@mui/material'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import ProjectEditPage from './pages/ProjectEditPage'
import ProjectListPage from './pages/ProjectListPage'

const theme = createTheme({ colorSchemes: { dark: true } })

export default function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <AppBar position="static">
          <Toolbar>
            <Typography variant="h6" component="div">
              Project editor
            </Typography>
          </Toolbar>
        </AppBar>
        <Container maxWidth="md" sx={{ py: 3 }}>
          <Routes>
            <Route path="/" element={<ProjectListPage />} />
            <Route path="/projects/:id" element={<ProjectEditPage />} />
          </Routes>
        </Container>
      </BrowserRouter>
    </ThemeProvider>
  )
}

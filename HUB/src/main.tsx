import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/global.css'
import { initTheme } from './lib/theme'
import App from './App.tsx'

// Aplica tema antes do render para evitar flash
initTheme()

const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('Elemento #root não encontrado no DOM')
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

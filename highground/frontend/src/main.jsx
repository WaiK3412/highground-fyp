import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'

// The frozen prototype's stylesheets, reused as-is (ADR-001: no Tailwind, no
// component library). Screens are ported HTML -> JSX, never redesigned.
import './styles/tokens.css'
import './styles/styles.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

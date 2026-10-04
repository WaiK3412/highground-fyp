import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'

// Reuse frozen prototype CSS without Tailwind or a component library (ADR-001).
import './styles/tokens.css'
import './styles/styles.css'
import './styles/app.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

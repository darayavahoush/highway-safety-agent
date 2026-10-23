import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles.css'
import './premium.css'
import './compact-console.css'
import './decision-first.css'
import './redesign.css'
import './violet-redesign.css'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

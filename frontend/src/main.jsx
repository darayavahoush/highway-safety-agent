import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import 'maplibre-gl/dist/maplibre-gl.css' // kept eager (and before app.css) so style order is unchanged
import './styles/app.css'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
